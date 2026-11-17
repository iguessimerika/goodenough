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
    """CREATE TABLE IF NOT EXISTS pinned_setlists (
        setlist_id INT PRIMARY KEY,
        pinned_by INT NULL,
        pinned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_pin_setlist FOREIGN KEY (setlist_id) REFERENCES setlists (id) ON DELETE CASCADE,
        CONSTRAINT fk_pin_member FOREIGN KEY (pinned_by) REFERENCES members (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS rehearsals (
        id INT AUTO_INCREMENT PRIMARY KEY,
        rehearsal_date DATE NOT NULL UNIQUE,
        is_cancelled TINYINT(1) NOT NULL DEFAULT 0,
        cancel_reason VARCHAR(200) NULL,
        setlist_id INT NULL,
        notes TEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_rehearsal_setlist FOREIGN KEY (setlist_id) REFERENCES setlists (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS rehearsal_responses (
        rehearsal_id INT NOT NULL,
        member_id INT NOT NULL,
        status VARCHAR(3) NOT NULL,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (rehearsal_id, member_id),
        CONSTRAINT fk_response_rehearsal FOREIGN KEY (rehearsal_id) REFERENCES rehearsals (id) ON DELETE CASCADE,
        CONSTRAINT fk_response_member FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS rehearsal_songs (
        rehearsal_id INT NOT NULL,
        song_id INT NOT NULL,
        position INT NOT NULL,
        PRIMARY KEY (rehearsal_id, song_id),
        CONSTRAINT fk_rsong_rehearsal FOREIGN KEY (rehearsal_id) REFERENCES rehearsals (id) ON DELETE CASCADE,
        CONSTRAINT fk_rsong_song FOREIGN KEY (song_id) REFERENCES songs (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    # Kept apart from rehearsals so "Clean up" can delete old rehearsals without losing who still owes food.
    """CREATE TABLE IF NOT EXISTS food_duties (
        id INT AUTO_INCREMENT PRIMARY KEY,
        member_id INT NOT NULL,
        rehearsal_id INT NULL,
        rehearsal_date DATE NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        settled_at DATETIME NULL,
        settled_by INT NULL,
        CONSTRAINT fk_food_member FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE,
        CONSTRAINT fk_food_rehearsal FOREIGN KEY (rehearsal_id) REFERENCES rehearsals (id) ON DELETE SET NULL,
        CONSTRAINT fk_food_settler FOREIGN KEY (settled_by) REFERENCES members (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS settings (
        name VARCHAR(60) PRIMARY KEY,
        value VARCHAR(255) NOT NULL,
        updated_by INT NULL,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_setting_member FOREIGN KEY (updated_by) REFERENCES members (id) ON DELETE SET NULL
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
                    WHERE s.setlist_id = l.id) AS song_count,
                  p.pinned_at IS NOT NULL AS is_pinned
           FROM setlists l
           LEFT JOIN pinned_setlists p ON p.setlist_id = l.id
           ORDER BY p.pinned_at IS NULL, p.pinned_at DESC, l.event_date IS NULL, l.event_date ASC, l.name"""
    )


def get_setlist(setlist_id):
    """A setlist with its 'sets' (ordered), each with a 'songs' list (ordered)."""
    setlist = fetch_one(
        """SELECT l.id, l.name, l.event_date, l.information,
                  p.pinned_at, m.name AS pinned_by_name
           FROM setlists l
           LEFT JOIN pinned_setlists p ON p.setlist_id = l.id
           LEFT JOIN members m ON m.id = p.pinned_by
           WHERE l.id = %s""",
        (setlist_id,),
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


# --------------------------------------------------------------------- sheet music for setlists

def _in_clause(ids):
    return ", ".join(["%s"] * len(ids))


def list_documents_for_songs(song_ids):
    """{song_id: [documents in upload order]} for several songs at once."""
    song_ids = sorted(set(song_ids))
    if not song_ids:
        return {}
    result = {}
    for d in fetch_all(
        f"""SELECT id, song_id, filename FROM documents
            WHERE song_id IN ({_in_clause(song_ids)}) ORDER BY created_at, id""",
        tuple(song_ids),
    ):
        result.setdefault(d["song_id"], []).append(d)
    return result


def list_singers_for_songs(song_ids):
    """{song_id: [singer names]} for several songs at once."""
    song_ids = sorted(set(song_ids))
    if not song_ids:
        return {}
    result = {}
    for r in fetch_all(
        f"""SELECT ss.song_id, mb.name FROM song_singers ss JOIN members mb ON mb.id = ss.member_id
            WHERE ss.song_id IN ({_in_clause(song_ids)}) ORDER BY mb.name""",
        tuple(song_ids),
    ):
        result.setdefault(r["song_id"], []).append(r["name"])
    return result


def get_annotations_for(document_ids):
    """{document_id: annotations json string or None} for several PDFs at once."""
    document_ids = sorted(set(document_ids))
    if not document_ids:
        return {}
    result = {}
    for r in fetch_all(
        f"SELECT id, annotations FROM documents WHERE id IN ({_in_clause(document_ids)})",
        tuple(document_ids),
    ):
        value = r["annotations"]
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        result[r["id"]] = value
    return result


def get_setlist_with_sheets(setlist_id):
    """Like get_setlist, but every song also has 'documents' (its PDFs) and 'singers'."""
    setlist = get_setlist(setlist_id)
    if setlist is None:
        return None
    song_ids = [entry["song_id"] for one_set in setlist["sets"] for entry in one_set["songs"]]
    documents = list_documents_for_songs(song_ids)
    singers = list_singers_for_songs(song_ids)
    for one_set in setlist["sets"]:
        for entry in one_set["songs"]:
            entry["documents"] = documents.get(entry["song_id"], [])
            entry["singers"] = singers.get(entry["song_id"], [])
        one_set["document_count"] = sum(len(entry["documents"]) for entry in one_set["songs"])
    setlist["document_count"] = sum(one_set["document_count"] for one_set in setlist["sets"])
    return setlist


# --------------------------------------------------------------------- pinned setlists (shared by the whole band)

def pin_setlist(setlist_id, member_id):
    """Pins a setlist for everyone. Pinning again keeps the original pin."""
    return execute(
        """INSERT INTO pinned_setlists (setlist_id, pinned_by) VALUES (%s, %s)
           ON DUPLICATE KEY UPDATE setlist_id = setlist_id""",
        (setlist_id, member_id),
    )


def unpin_setlist(setlist_id):
    return execute("DELETE FROM pinned_setlists WHERE setlist_id = %s", (setlist_id,))


def list_pinned_setlists():
    """Pinned setlists for the bar under the menu, newest pin first, with whether they have sheet music."""
    return fetch_all(
        """SELECT l.id, l.name, l.event_date,
                  EXISTS (SELECT 1 FROM documents d
                          JOIN set_songs ss ON ss.song_id = d.song_id
                          JOIN setlist_sets s ON s.id = ss.set_id
                          WHERE s.setlist_id = l.id) AS has_sheets
           FROM pinned_setlists p JOIN setlists l ON l.id = p.setlist_id
           ORDER BY p.pinned_at DESC, l.id DESC"""
    )


# --------------------------------------------------------------------- rehearsals

def ensure_rehearsals(dates):
    """Creates a rehearsal for every given date that doesn't have one yet. Safe to call on every visit."""
    if not dates:
        return
    existing = {
        r["rehearsal_date"]
        for r in fetch_all(
            "SELECT rehearsal_date FROM rehearsals WHERE rehearsal_date BETWEEN %s AND %s",
            (min(dates), max(dates)),
        )
    }
    missing = [d for d in dates if d not in existing]
    if missing:
        # IGNORE only matters if two band members open the page at the same moment.
        with transaction() as cursor:
            cursor.executemany(
                "INSERT IGNORE INTO rehearsals (rehearsal_date) VALUES (%s)", [(d,) for d in missing]
            )


def list_rehearsals(from_date=None):
    """Rehearsals in ascending date order (from from_date on, if given), each with its responses."""
    where, params = ("WHERE r.rehearsal_date >= %s", (from_date,)) if from_date else ("", ())
    rehearsals = fetch_all(
        f"""SELECT r.id, r.rehearsal_date, r.is_cancelled, r.cancel_reason, r.setlist_id, r.notes,
                   r.created_at, l.name AS setlist_name,
                   (SELECT COUNT(*) FROM rehearsal_songs rs WHERE rs.rehearsal_id = r.id) AS song_count
            FROM rehearsals r LEFT JOIN setlists l ON l.id = r.setlist_id
            {where}
            ORDER BY r.rehearsal_date ASC""",
        params,
    )
    _attach_responses(rehearsals)
    return rehearsals


def count_past_rehearsals(before_date):
    return fetch_one(
        "SELECT COUNT(*) AS n FROM rehearsals WHERE rehearsal_date < %s", (before_date,)
    )["n"]


def get_rehearsal(rehearsal_id):
    rehearsal = fetch_one(
        """SELECT r.id, r.rehearsal_date, r.is_cancelled, r.cancel_reason, r.setlist_id, r.notes,
                  r.created_at, l.name AS setlist_name
           FROM rehearsals r LEFT JOIN setlists l ON l.id = r.setlist_id
           WHERE r.id = %s""",
        (rehearsal_id,),
    )
    if rehearsal is None:
        return None
    _attach_responses([rehearsal])
    rehearsal["songs"] = fetch_all(
        """SELECT so.id, so.title, so.artist, so.capo
           FROM rehearsal_songs rs JOIN songs so ON so.id = rs.song_id
           WHERE rs.rehearsal_id = %s ORDER BY rs.position, so.title""",
        (rehearsal_id,),
    )
    return rehearsal


def _attach_responses(rehearsals):
    """Adds 'responses': {member_id: 'yes' | 'no'} to every rehearsal."""
    for r in rehearsals:
        r["responses"] = {}
    ids = [r["id"] for r in rehearsals]
    if not ids:
        return
    by_id = {r["id"]: r for r in rehearsals}
    for row in fetch_all(
        f"""SELECT rehearsal_id, member_id, status FROM rehearsal_responses
            WHERE rehearsal_id IN ({_in_clause(ids)})""",
        tuple(ids),
    ):
        by_id[row["rehearsal_id"]]["responses"][row["member_id"]] = row["status"]


def create_rehearsal(rehearsal_date):
    """Adds an extra rehearsal. Returns its id, or None if there already is one that day."""
    existing = fetch_one("SELECT id FROM rehearsals WHERE rehearsal_date = %s", (rehearsal_date,))
    if existing:
        return None
    return insert("INSERT INTO rehearsals (rehearsal_date) VALUES (%s)", (rehearsal_date,))


def update_rehearsal_plan(rehearsal_id, setlist_id, notes):
    return execute(
        "UPDATE rehearsals SET setlist_id = %s, notes = %s WHERE id = %s",
        (setlist_id, notes or None, rehearsal_id),
    )


def set_rehearsal_cancelled(rehearsal_id, cancelled, reason):
    """Cancels (or restores) a rehearsal. Food owed for a cancelled rehearsal is dropped."""
    with transaction() as cursor:
        cursor.execute(
            "UPDATE rehearsals SET is_cancelled = %s, cancel_reason = %s WHERE id = %s",
            (1 if cancelled else 0, (reason or None) if cancelled else None, rehearsal_id),
        )
        if cancelled:
            cursor.execute(
                "DELETE FROM food_duties WHERE rehearsal_id = %s AND settled_at IS NULL", (rehearsal_id,)
            )


def delete_past_rehearsals(before_date):
    """Deletes rehearsals before the date. Food duties stay (their rehearsal link becomes empty)."""
    return execute("DELETE FROM rehearsals WHERE rehearsal_date < %s", (before_date,))


def add_song_to_rehearsal(rehearsal_id, song_id):
    return execute(
        """INSERT IGNORE INTO rehearsal_songs (rehearsal_id, song_id, position)
           SELECT %s, %s, COALESCE(MAX(position), 0) + 1 FROM rehearsal_songs WHERE rehearsal_id = %s""",
        (rehearsal_id, song_id, rehearsal_id),
    )


def remove_song_from_rehearsal(rehearsal_id, song_id):
    return execute(
        "DELETE FROM rehearsal_songs WHERE rehearsal_id = %s AND song_id = %s", (rehearsal_id, song_id)
    )


def set_response(rehearsal_id, member_id, status, late):
    """Saves a yes/no answer. Returns True if this answer means the member now owes food.

    Owing food: saying no after the deadline when you hadn't said no before.
    Saying yes again (you come after all) drops the open food duty for this rehearsal.
    """
    with transaction() as cursor:
        cursor.execute(
            """SELECT status FROM rehearsal_responses
               WHERE rehearsal_id = %s AND member_id = %s FOR UPDATE""",
            (rehearsal_id, member_id),
        )
        row = cursor.fetchone()
        previous = row["status"] if row else None
        cursor.execute(
            """INSERT INTO rehearsal_responses (rehearsal_id, member_id, status) VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE status = %s""",
            (rehearsal_id, member_id, status, status),
        )
        owes = False
        if status == "no" and previous != "no" and late:
            cursor.execute(
                """INSERT INTO food_duties (member_id, rehearsal_id, rehearsal_date)
                   SELECT %s, id, rehearsal_date FROM rehearsals WHERE id = %s""",
                (member_id, rehearsal_id),
            )
            owes = True
        elif status == "yes":
            cursor.execute(
                """DELETE FROM food_duties
                   WHERE member_id = %s AND rehearsal_id = %s AND settled_at IS NULL""",
                (member_id, rehearsal_id),
            )
        return owes


def list_member_instruments():
    """{member_id: set of instrument labels}."""
    result = {}
    for r in fetch_all(
        """SELECT mi.member_id, v.label FROM member_instruments mi
           JOIN keyword_values v ON v.id = mi.value_id"""
    ):
        result.setdefault(r["member_id"], set()).add(r["label"])
    return result


# --------------------------------------------------------------------- food duty

def list_open_food_duties():
    """Unsettled food duties, oldest first, with the member's name."""
    return fetch_all(
        """SELECT f.id, f.member_id, m.name, f.rehearsal_date
           FROM food_duties f JOIN members m ON m.id = f.member_id
           WHERE f.settled_at IS NULL
           ORDER BY f.rehearsal_date, f.id"""
    )


def food_brought_counts():
    """{member_id: how often they have brought food}."""
    return {
        r["member_id"]: r["n"]
        for r in fetch_all(
            """SELECT member_id, COUNT(*) AS n FROM food_duties
               WHERE settled_at IS NOT NULL GROUP BY member_id"""
        )
    }


def get_food_duty(duty_id):
    return fetch_one(
        """SELECT f.id, f.member_id, m.name, f.rehearsal_date, f.settled_at
           FROM food_duties f JOIN members m ON m.id = f.member_id WHERE f.id = %s""",
        (duty_id,),
    )


def settle_food_duty(duty_id, settled_by):
    return execute(
        "UPDATE food_duties SET settled_at = CURRENT_TIMESTAMP, settled_by = %s WHERE id = %s AND settled_at IS NULL",
        (settled_by, duty_id),
    )


# --------------------------------------------------------------------- settings

# Band-wide settings and their defaults. Values are stored as text.
SETTING_DEFAULTS = {
    "rehearsal_weekday": "0",    # 0 = Monday … 6 = Sunday (like Python's date.weekday())
    "rehearsal_time": "17:30",
}


def get_settings():
    """All settings, with the defaults filled in for anything not saved yet."""
    values = dict(SETTING_DEFAULTS)
    for r in fetch_all("SELECT name, value FROM settings"):
        values[r["name"]] = r["value"]
    return values


def save_settings(values, member_id):
    with transaction() as cursor:
        for name, value in values.items():
            cursor.execute(
                """INSERT INTO settings (name, value, updated_by) VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE value = %s, updated_by = %s""",
                (name, value, member_id, value, member_id),
            )


def remove_unused_rehearsals(from_date, weekday):
    """After the rehearsal day changed: deletes upcoming rehearsals on the old weekday that nobody
    has used yet (no answers, no plan, not cancelled). Returns the dates of the ones that were kept."""
    rows = fetch_all(
        """SELECT r.id, r.rehearsal_date,
                  r.is_cancelled OR r.setlist_id IS NOT NULL OR COALESCE(r.notes, '') <> ''
                  OR EXISTS (SELECT 1 FROM rehearsal_responses x WHERE x.rehearsal_id = r.id)
                  OR EXISTS (SELECT 1 FROM rehearsal_songs x WHERE x.rehearsal_id = r.id) AS in_use
           FROM rehearsals r WHERE r.rehearsal_date >= %s ORDER BY r.rehearsal_date""",
        (from_date,),
    )
    on_old_day = [r for r in rows if r["rehearsal_date"].weekday() == weekday]
    unused = [r["id"] for r in on_old_day if not r["in_use"]]
    if unused:
        execute(f"DELETE FROM rehearsals WHERE id IN ({_in_clause(unused)})", tuple(unused))
    return [r["rehearsal_date"] for r in on_old_day if r["in_use"]]


if __name__ == "__main__":
    test_connection()
