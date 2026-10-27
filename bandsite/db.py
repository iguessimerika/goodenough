"""All database access. Plain mysql.connector, no ORM.

get_connection() and test_connection() are the helpers from the project's original
connection file. Everything below them is built on top of get_connection().
"""
import os
from contextlib import contextmanager

import mysql.connector
from flask import g

PHASE = "Phase"
MOOD = "Mood"
INSTRUMENT = "Instrument"

DEFAULT_KEYWORDS = {
    PHASE: ["Idea", "Learning", "Almost ready", "Stage-ready"],
    MOOD: ["Calm", "Emotional", "Cheerful", "Energetic", "Dark"],
    INSTRUMENT: ["Gesang", "Gitarre", "Bass", "Schlagzeug", "Piano"],
}


# --------------------------------------------------------------------- connection

def get_connection():
    return mysql.connector.connect(
        host=os.environ["MYSQLHOST"],
        port=int(os.environ["MYSQLPORT"]),
        user=os.environ["MYSQLUSER"],
        password=os.environ["MYSQLPASSWORD"],
        database=os.environ["MYSQLDATABASE"],
        connection_timeout=10,
        charset="utf8mb4",
    )


def test_connection():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()

        print("Database reached successfully!")
        return True

    except KeyError as error:
        print(f"Missing environment variable: {error.args[0]}")
        return False

    except (mysql.connector.Error, ValueError) as error:
        print(f"Database connection failed: {error}")
        return False

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# One connection per web request, closed automatically when the request ends.

def get_db():
    conn = g.get("db")
    if conn is None or not conn.is_connected():
        conn = g.db = get_connection()
    return conn


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.close()
        except mysql.connector.Error:
            pass


def fetch_all(sql, params=()):
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()


def fetch_one(sql, params=()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


@contextmanager
def transaction():
    """Yields a cursor; commits when the block ends, rolls back on any error."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def execute(sql, params=()):
    """Runs one write statement. Returns the number of affected rows."""
    with transaction() as cursor:
        cursor.execute(sql, params)
        return cursor.rowcount


def insert(sql, params=()):
    """Runs one INSERT. Returns the new row's id."""
    with transaction() as cursor:
        cursor.execute(sql, params)
        return cursor.lastrowid


# --------------------------------------------------------------------- schema

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS members (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(80) NOT NULL,
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        is_admin TINYINT(1) NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS keywords (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(60) NOT NULL UNIQUE,
        is_fixed TINYINT(1) NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS keyword_values (
        id INT AUTO_INCREMENT PRIMARY KEY,
        keyword_id INT NOT NULL,
        label VARCHAR(60) NOT NULL,
        sort_order INT NOT NULL DEFAULT 0,
        UNIQUE KEY uq_keyword_label (keyword_id, label),
        CONSTRAINT fk_value_keyword FOREIGN KEY (keyword_id) REFERENCES keywords (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS member_instruments (
        member_id INT NOT NULL,
        value_id INT NOT NULL,
        PRIMARY KEY (member_id, value_id),
        CONSTRAINT fk_instrument_member FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE,
        CONSTRAINT fk_instrument_value FOREIGN KEY (value_id) REFERENCES keyword_values (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS songs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(200) NOT NULL,
        artist VARCHAR(200) NOT NULL,
        capo INT NOT NULL DEFAULT 0,
        information TEXT NULL,
        youtube_url VARCHAR(500) NULL,
        phase_id INT NULL,
        mood_id INT NULL,
        created_by INT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_song_phase FOREIGN KEY (phase_id) REFERENCES keyword_values (id) ON DELETE SET NULL,
        CONSTRAINT fk_song_mood FOREIGN KEY (mood_id) REFERENCES keyword_values (id) ON DELETE SET NULL,
        CONSTRAINT fk_song_creator FOREIGN KEY (created_by) REFERENCES members (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS song_singers (
        song_id INT NOT NULL,
        member_id INT NOT NULL,
        PRIMARY KEY (song_id, member_id),
        CONSTRAINT fk_singer_song FOREIGN KEY (song_id) REFERENCES songs (id) ON DELETE CASCADE,
        CONSTRAINT fk_singer_member FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS documents (
        id INT AUTO_INCREMENT PRIMARY KEY,
        song_id INT NOT NULL,
        filename VARCHAR(255) NOT NULL,
        size_bytes INT NOT NULL,
        file_data LONGBLOB NOT NULL,
        annotations LONGTEXT NULL,
        annotation_version INT NOT NULL DEFAULT 0,
        uploaded_by INT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_document_song FOREIGN KEY (song_id) REFERENCES songs (id) ON DELETE CASCADE,
        CONSTRAINT fk_document_uploader FOREIGN KEY (uploaded_by) REFERENCES members (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS setlists (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(120) NOT NULL,
        event_date DATE NULL,
        information TEXT NULL,
        created_by INT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_setlist_creator FOREIGN KEY (created_by) REFERENCES members (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS setlist_sets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        setlist_id INT NOT NULL,
        name VARCHAR(80) NOT NULL,
        position INT NOT NULL,
        mood_id INT NULL,
        CONSTRAINT fk_set_setlist FOREIGN KEY (setlist_id) REFERENCES setlists (id) ON DELETE CASCADE,
        CONSTRAINT fk_set_mood FOREIGN KEY (mood_id) REFERENCES keyword_values (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS set_songs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        set_id INT NOT NULL,
        song_id INT NOT NULL,
        position INT NOT NULL,
        UNIQUE KEY uq_song_in_set (set_id, song_id),
        CONSTRAINT fk_setsong_set FOREIGN KEY (set_id) REFERENCES setlist_sets (id) ON DELETE CASCADE,
        CONSTRAINT fk_setsong_song FOREIGN KEY (song_id) REFERENCES songs (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


def init_schema():
    """Creates missing tables and seeds the default keywords. Safe to run repeatedly.

    Uses its own connection, so it works outside a web request (see init_db.py).
    """
    connection = get_connection()
    cursor = connection.cursor()
    try:
        for statement in SCHEMA:
            cursor.execute(statement)
        for name, labels in DEFAULT_KEYWORDS.items():
            cursor.execute("SELECT id FROM keywords WHERE name = %s", (name,))
            if cursor.fetchall():
                continue
            cursor.execute("INSERT INTO keywords (name, is_fixed) VALUES (%s, 1)", (name,))
            keyword_id = cursor.lastrowid
            cursor.executemany(
                "INSERT INTO keyword_values (keyword_id, label, sort_order) VALUES (%s, %s, %s)",
                [(keyword_id, label, i) for i, label in enumerate(labels)],
            )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


# --------------------------------------------------------------------- members

def get_member(member_id):
    return fetch_one("SELECT * FROM members WHERE id = %s", (member_id,))


def get_member_by_email(email):
    return fetch_one("SELECT * FROM members WHERE email = %s", (email,))


def count_members():
    return fetch_one("SELECT COUNT(*) AS n FROM members")["n"]


def list_members():
    """All members, each with an 'instruments' list of labels."""
    members = fetch_all("SELECT id, name, is_admin FROM members ORDER BY name")
    rows = fetch_all(
        """SELECT mi.member_id, v.label
           FROM member_instruments mi JOIN keyword_values v ON v.id = mi.value_id
           ORDER BY v.sort_order, v.id"""
    )
    by_id = {m["id"]: m for m in members}
    for m in members:
        m["instruments"] = []
    for r in rows:
        by_id[r["member_id"]]["instruments"].append(r["label"])
    return members


def create_member(name, email, password_hash, is_admin, instrument_ids=()):
    """Creates a member and their instruments in one transaction. Returns the new id."""
    with transaction() as cursor:
        cursor.execute(
            "INSERT INTO members (name, email, password_hash, is_admin) VALUES (%s, %s, %s, %s)",
            (name, email, password_hash, 1 if is_admin else 0),
        )
        member_id = cursor.lastrowid
        if instrument_ids:
            cursor.executemany(
                "INSERT INTO member_instruments (member_id, value_id) VALUES (%s, %s)",
                [(member_id, value_id) for value_id in instrument_ids],
            )
        return member_id


# --------------------------------------------------------------------- keywords

def list_keywords():
    """All keywords, each with a 'values' list."""
    keywords = fetch_all("SELECT id, name, is_fixed FROM keywords ORDER BY name")
    values = fetch_all("SELECT id, keyword_id, label FROM keyword_values ORDER BY sort_order, id")
    by_keyword = {k["id"]: k for k in keywords}
    for k in keywords:
        k["values"] = []
    for v in values:
        by_keyword[v["keyword_id"]]["values"].append(v)
    return keywords


def list_values(keyword_name):
    return fetch_all(
        """SELECT v.id, v.label
           FROM keyword_values v JOIN keywords k ON k.id = v.keyword_id
           WHERE k.name = %s
           ORDER BY v.sort_order, v.id""",
        (keyword_name,),
    )


def get_keyword(keyword_id):
    return fetch_one("SELECT id, name, is_fixed FROM keywords WHERE id = %s", (keyword_id,))


def keyword_name_exists(name):
    return fetch_one("SELECT id FROM keywords WHERE LOWER(name) = LOWER(%s)", (name,)) is not None


def create_keyword(name):
    return insert("INSERT INTO keywords (name, is_fixed) VALUES (%s, 0)", (name,))


def delete_keyword(keyword_id):
    return execute("DELETE FROM keywords WHERE id = %s", (keyword_id,))


def get_keyword_value(value_id):
    return fetch_one("SELECT id, keyword_id, label FROM keyword_values WHERE id = %s", (value_id,))


def value_exists(keyword_id, label):
    return (
        fetch_one(
            "SELECT id FROM keyword_values WHERE keyword_id = %s AND LOWER(label) = LOWER(%s)",
            (keyword_id, label),
        )
        is not None
    )


def add_keyword_value(keyword_id, label):
    return insert(
        """INSERT INTO keyword_values (keyword_id, label, sort_order)
           SELECT %s, %s, COALESCE(MAX(sort_order), -1) + 1 FROM keyword_values WHERE keyword_id = %s""",
        (keyword_id, label, keyword_id),
    )


def delete_keyword_value(value_id):
    # Songs that use the value keep existing: their phase_id / mood_id is set to NULL by the foreign key.
    return execute("DELETE FROM keyword_values WHERE id = %s", (value_id,))


# --------------------------------------------------------------------- songs

_SONG_SELECT = """
    SELECT s.id, s.title, s.artist, s.capo, s.information, s.youtube_url,
           s.phase_id, s.mood_id, p.label AS phase, m.label AS mood,
           (SELECT COUNT(*) FROM documents d WHERE d.song_id = s.id) AS document_count
    FROM songs s
    LEFT JOIN keyword_values p ON p.id = s.phase_id
    LEFT JOIN keyword_values m ON m.id = s.mood_id
"""


def _attach_singers(songs):
    if not songs:
        return songs
    ids = [s["id"] for s in songs]
    placeholders = ", ".join(["%s"] * len(ids))
    rows = fetch_all(
        f"""SELECT ss.song_id, mb.id, mb.name
            FROM song_singers ss JOIN members mb ON mb.id = ss.member_id
            WHERE ss.song_id IN ({placeholders})
            ORDER BY mb.name""",
        tuple(ids),
    )
    by_song = {s["id"]: s for s in songs}
    for s in songs:
        s["singers"] = []
    for r in rows:
        by_song[r["song_id"]]["singers"].append({"id": r["id"], "name": r["name"]})
    return songs


def list_songs(search="", phase_id=None, mood_id=None):
    conditions, params = [], []
    if search:
        pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        conditions.append("(s.title LIKE %s OR s.artist LIKE %s)")
        params += [pattern, pattern]
    if phase_id:
        conditions.append("s.phase_id = %s")
        params.append(phase_id)
    if mood_id:
        conditions.append("s.mood_id = %s")
        params.append(mood_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    songs = fetch_all(f"{_SONG_SELECT} {where} ORDER BY s.title", tuple(params))
    return _attach_singers(songs)


def get_song(song_id):
    song = fetch_one(f"{_SONG_SELECT} WHERE s.id = %s", (song_id,))
    if song is None:
        return None
    _attach_singers([song])
    song["documents"] = list_documents(song_id)
    return song


def _replace_singers(cursor, song_id, member_ids):
    cursor.execute("DELETE FROM song_singers WHERE song_id = %s", (song_id,))
    if member_ids:
        cursor.executemany(
            "INSERT INTO song_singers (song_id, member_id) VALUES (%s, %s)",
            [(song_id, member_id) for member_id in member_ids],
        )


def create_song(data, created_by):
    with transaction() as cursor:
        cursor.execute(
            """INSERT INTO songs (title, artist, capo, information, youtube_url, phase_id, mood_id, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (data["title"], data["artist"], data["capo"], data["information"] or None,
             data["youtube_url"] or None, data["phase_id"], data["mood_id"], created_by),
        )
        song_id = cursor.lastrowid
        _replace_singers(cursor, song_id, data["singer_ids"])
        return song_id


def update_song(song_id, data):
    with transaction() as cursor:
        cursor.execute(
            """UPDATE songs SET title = %s, artist = %s, capo = %s, information = %s,
                      youtube_url = %s, phase_id = %s, mood_id = %s
               WHERE id = %s""",
            (data["title"], data["artist"], data["capo"], data["information"] or None,
             data["youtube_url"] or None, data["phase_id"], data["mood_id"], song_id),
        )
        _replace_singers(cursor, song_id, data["singer_ids"])


def delete_song(song_id):
    return execute("DELETE FROM songs WHERE id = %s", (song_id,))


# --------------------------------------------------------------------- documents (sheet music PDFs)

def list_documents(song_id):
    return fetch_all(
        "SELECT id, song_id, filename, size_bytes FROM documents WHERE song_id = %s ORDER BY created_at, id",
        (song_id,),
    )


def get_document(document_id):
    """Metadata incl. the song title, without the file itself."""
    return fetch_one(
        """SELECT d.id, d.song_id, d.filename, d.size_bytes, s.title AS song_title
           FROM documents d JOIN songs s ON s.id = d.song_id
           WHERE d.id = %s""",
        (document_id,),
    )


def get_document_file(document_id):
    row = fetch_one("SELECT filename, file_data FROM documents WHERE id = %s", (document_id,))
    if row is None:
        return None
    return {"filename": row["filename"], "data": bytes(row["file_data"])}


def create_document(song_id, filename, data, uploaded_by):
    return insert(
        "INSERT INTO documents (song_id, filename, size_bytes, file_data, uploaded_by) VALUES (%s, %s, %s, %s, %s)",
        (song_id, filename, len(data), data, uploaded_by),
    )


def delete_document(document_id):
    return execute("DELETE FROM documents WHERE id = %s", (document_id,))


def get_annotations(document_id):
    """Returns {'annotations': json-string-or-None, 'annotation_version': int} or None."""
    return fetch_one(
        "SELECT annotations, annotation_version FROM documents WHERE id = %s", (document_id,)
    )


def save_annotations(document_id, annotations_json, expected_version):
    """Saves only if nobody saved in between. Returns True on success, False on a version conflict."""
    changed = execute(
        """UPDATE documents SET annotations = %s, annotation_version = annotation_version + 1
           WHERE id = %s AND annotation_version = %s""",
        (annotations_json, document_id, expected_version),
    )
    return changed == 1


# --------------------------------------------------------------------- setlists

def list_setlists():
    return fetch_all(
        """SELECT l.id, l.name, l.event_date, l.information,
                  (SELECT COUNT(*) FROM setlist_sets s WHERE s.setlist_id = l.id) AS set_count,
                  (SELECT COUNT(*) FROM set_songs ss JOIN setlist_sets s ON s.id = ss.set_id
                    WHERE s.setlist_id = l.id) AS song_count
           FROM setlists l
           ORDER BY l.event_date IS NULL, l.event_date ASC, l.name"""
    )


def get_setlist(setlist_id):
    """A setlist with its 'sets' (ordered), each with a 'songs' list (ordered)."""
    setlist = fetch_one(
        "SELECT id, name, event_date, information FROM setlists WHERE id = %s", (setlist_id,)
    )
    if setlist is None:
        return None
    sets = fetch_all(
        """SELECT s.id, s.name, s.position, s.mood_id, m.label AS mood
           FROM setlist_sets s LEFT JOIN keyword_values m ON m.id = s.mood_id
           WHERE s.setlist_id = %s
           ORDER BY s.position, s.id""",
        (setlist_id,),
    )
    rows = fetch_all(
        """SELECT ss.id, ss.set_id, ss.song_id, so.title, so.artist, so.capo
           FROM set_songs ss
           JOIN setlist_sets s ON s.id = ss.set_id
           JOIN songs so ON so.id = ss.song_id
           WHERE s.setlist_id = %s
           ORDER BY ss.position, ss.id""",
        (setlist_id,),
    )
    by_set = {s["id"]: s for s in sets}
    for s in sets:
        s["songs"] = []
    for r in rows:
        by_set[r["set_id"]]["songs"].append(r)
    setlist["sets"] = sets
    return setlist


def create_setlist(name, event_date, information, created_by):
    return insert(
        "INSERT INTO setlists (name, event_date, information, created_by) VALUES (%s, %s, %s, %s)",
        (name, event_date, information or None, created_by),
    )


def update_setlist(setlist_id, name, event_date, information):
    return execute(
        "UPDATE setlists SET name = %s, event_date = %s, information = %s WHERE id = %s",
        (name, event_date, information or None, setlist_id),
    )


def delete_setlist(setlist_id):
    return execute("DELETE FROM setlists WHERE id = %s", (setlist_id,))


def get_set(set_id):
    return fetch_one(
        "SELECT id, setlist_id, name, position, mood_id FROM setlist_sets WHERE id = %s", (set_id,)
    )


def create_set(setlist_id, name, mood_id):
    """Adds a set at the end of the setlist."""
    return insert(
        """INSERT INTO setlist_sets (setlist_id, name, position, mood_id)
           SELECT %s, %s, COALESCE(MAX(position), 0) + 1, %s FROM setlist_sets WHERE setlist_id = %s""",
        (setlist_id, name, mood_id, setlist_id),
    )


def update_set(set_id, name, mood_id):
    return execute("UPDATE setlist_sets SET name = %s, mood_id = %s WHERE id = %s", (name, mood_id, set_id))


def delete_set(set_id):
    return execute("DELETE FROM setlist_sets WHERE id = %s", (set_id,))


def song_exists(song_id):
    return fetch_one("SELECT id FROM songs WHERE id = %s", (song_id,)) is not None


def list_song_choices():
    """All songs, slim, for the 'add a song' dropdowns."""
    return fetch_all("SELECT id, title, artist FROM songs ORDER BY title, artist")


def add_song_to_set(set_id, song_id):
    """Adds a song at the end of the set. Raises IntegrityError if it is already in the set."""
    return insert(
        """INSERT INTO set_songs (set_id, song_id, position)
           SELECT %s, %s, COALESCE(MAX(position), 0) + 1 FROM set_songs WHERE set_id = %s""",
        (set_id, song_id, set_id),
    )


def get_set_song(set_song_id):
    return fetch_one(
        """SELECT ss.id, ss.set_id, s.setlist_id
           FROM set_songs ss JOIN setlist_sets s ON s.id = ss.set_id
           WHERE ss.id = %s""",
        (set_song_id,),
    )


def remove_song_from_set(set_song_id):
    return execute("DELETE FROM set_songs WHERE id = %s", (set_song_id,))


def _move(table, group_column, row_id, direction):
    """Swaps a row with its neighbour inside the same group. Table and column names come from code only."""
    if direction not in ("up", "down"):
        return False
    comparison, order = ("<", "DESC") if direction == "up" else (">", "ASC")
    with transaction() as cursor:
        cursor.execute(
            f"SELECT id, {group_column} AS group_id, position FROM {table} WHERE id = %s FOR UPDATE",
            (row_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return False
        cursor.execute(
            f"""SELECT id, position FROM {table}
                WHERE {group_column} = %s
                  AND (position {comparison} %s OR (position = %s AND id {comparison} %s))
                ORDER BY position {order}, id {order} LIMIT 1""",
            (row["group_id"], row["position"], row["position"], row["id"]),
        )
        other = cursor.fetchone()
        if other is None:
            return False
        cursor.execute(f"UPDATE {table} SET position = %s WHERE id = %s", (other["position"], row["id"]))
        cursor.execute(f"UPDATE {table} SET position = %s WHERE id = %s", (row["position"], other["id"]))
        return True


def move_set(set_id, direction):
    return _move("setlist_sets", "setlist_id", set_id, direction)


def move_set_song(set_song_id, direction):
    return _move("set_songs", "set_id", set_song_id, direction)


if __name__ == "__main__":
    test_connection()
