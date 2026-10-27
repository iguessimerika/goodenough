"""All SQL queries of the app, grouped by topic."""
from .db import execute, query_all, query_one, transaction
from .utils import youtube_id


def _text(value):
    return value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else value


# ---------------------------------------------------------------- band members

def member_by_id(member_id):
    return query_one(
        "SELECT id, name, email, password_hash, instrument, is_admin FROM band_member WHERE id = %s",
        (member_id,),
    )


def member_by_email(email):
    return query_one(
        "SELECT id, name, email, password_hash, instrument, is_admin FROM band_member WHERE email = %s",
        (email,),
    )


def member_count():
    return query_one("SELECT COUNT(*) AS n FROM band_member")["n"]


def list_members():
    return query_all("SELECT id, name, instrument, is_admin FROM band_member ORDER BY name")


def create_member(name, email, instrument, password_hash, is_admin):
    new_id, _ = execute(
        "INSERT INTO band_member (name, email, instrument, password_hash, is_admin) "
        "VALUES (%s, %s, %s, %s, %s)",
        (name, email, instrument, password_hash, 1 if is_admin else 0),
    )
    return new_id


# ---------------------------------------------------------------- keywords

def list_keywords():
    keywords = query_all("SELECT id, name, is_fixed FROM keyword ORDER BY name")
    values = query_all("SELECT id, keyword_id, value FROM keyword_value ORDER BY sort_order, id")
    by_keyword = {k["id"]: [] for k in keywords}
    for v in values:
        by_keyword.setdefault(v["keyword_id"], []).append(v)
    for k in keywords:
        k["value_list"] = by_keyword.get(k["id"], [])
    return keywords


def keyword_values(name):
    return query_all(
        "SELECT v.id, v.value FROM keyword_value v JOIN keyword k ON k.id = v.keyword_id "
        "WHERE k.name = %s ORDER BY v.sort_order, v.id",
        (name,),
    )


def get_keyword(keyword_id):
    return query_one("SELECT id, name, is_fixed FROM keyword WHERE id = %s", (keyword_id,))


def keyword_name_taken(name):
    return query_one("SELECT id FROM keyword WHERE LOWER(name) = LOWER(%s)", (name,)) is not None


def create_keyword(name):
    execute("INSERT INTO keyword (name, is_fixed) VALUES (%s, 0)", (name,))


def delete_keyword(keyword_id):
    execute("DELETE FROM keyword WHERE id = %s", (keyword_id,))


def value_taken(keyword_id, value):
    return query_one(
        "SELECT id FROM keyword_value WHERE keyword_id = %s AND LOWER(value) = LOWER(%s)",
        (keyword_id, value),
    ) is not None


def add_value(keyword_id, value):
    next_order = query_one(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM keyword_value WHERE keyword_id = %s",
        (keyword_id,),
    )["n"]
    execute(
        "INSERT INTO keyword_value (keyword_id, value, sort_order) VALUES (%s, %s, %s)",
        (keyword_id, value, int(next_order)),
    )


def get_value(value_id):
    return query_one("SELECT id, keyword_id, value FROM keyword_value WHERE id = %s", (value_id,))


def delete_value(value_id):
    # Songs that used this value lose it (ON DELETE SET NULL).
    execute("DELETE FROM keyword_value WHERE id = %s", (value_id,))


# ---------------------------------------------------------------- songs

_SONG_SELECT = """
SELECT s.id, s.title, s.artist, s.capo, s.information, s.youtube_url,
       s.phase_id, s.mood_id, p.value AS phase, m.value AS mood,
       (SELECT COUNT(*) FROM document d WHERE d.song_id = s.id) AS document_count,
       (SELECT GROUP_CONCAT(b.name ORDER BY b.name SEPARATOR ', ')
          FROM song_singer ss JOIN band_member b ON b.id = ss.member_id
         WHERE ss.song_id = s.id) AS singers
  FROM song s
  LEFT JOIN keyword_value p ON p.id = s.phase_id
  LEFT JOIN keyword_value m ON m.id = s.mood_id
"""


def _song(row):
    row["singers"] = _text(row["singers"])
    row["youtube_id"] = youtube_id(row["youtube_url"])
    return row


def list_songs(q="", phase_id=None, mood_id=None):
    where, params = [], []
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(s.title LIKE %s OR s.artist LIKE %s)")
        params += [like, like]
    if phase_id:
        where.append("s.phase_id = %s")
        params.append(phase_id)
    if mood_id:
        where.append("s.mood_id = %s")
        params.append(mood_id)
    sql = _SONG_SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY LOWER(s.title)"
    return [_song(row) for row in query_all(sql, tuple(params))]


def get_song(song_id):
    row = query_one(_SONG_SELECT + " WHERE s.id = %s", (song_id,))
    if row is None:
        return None
    song = _song(row)
    song["singer_list"] = query_all(
        "SELECT b.id, b.name FROM song_singer ss JOIN band_member b ON b.id = ss.member_id "
        "WHERE ss.song_id = %s ORDER BY b.name",
        (song_id,),
    )
    song["singer_ids"] = [s["id"] for s in song["singer_list"]]
    song["documents"] = query_all(
        "SELECT id, filename, size FROM document WHERE song_id = %s ORDER BY created_at, id",
        (song_id,),
    )
    return song


def _set_singers(cursor, song_id, singer_ids):
    cursor.execute("DELETE FROM song_singer WHERE song_id = %s", (song_id,))
    if singer_ids:
        cursor.executemany(
            "INSERT INTO song_singer (song_id, member_id) VALUES (%s, %s)",
            [(song_id, member_id) for member_id in singer_ids],
        )


def create_song(d, created_by):
    with transaction() as cursor:
        cursor.execute(
            "INSERT INTO song (title, artist, capo, information, youtube_url, phase_id, mood_id, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (d["title"], d["artist"], d["capo"], d["information"] or None, d["youtube_url"] or None,
             d["phase_id"], d["mood_id"], created_by),
        )
        song_id = cursor.lastrowid
        _set_singers(cursor, song_id, d["singer_ids"])
    return song_id


def update_song(song_id, d):
    with transaction() as cursor:
        cursor.execute(
            "UPDATE song SET title = %s, artist = %s, capo = %s, information = %s, youtube_url = %s, "
            "phase_id = %s, mood_id = %s WHERE id = %s",
            (d["title"], d["artist"], d["capo"], d["information"] or None, d["youtube_url"] or None,
             d["phase_id"], d["mood_id"], song_id),
        )
        _set_singers(cursor, song_id, d["singer_ids"])


def delete_song(song_id):
    execute("DELETE FROM song WHERE id = %s", (song_id,))


# ---------------------------------------------------------------- documents (sheet music)

def add_document(song_id, filename, data, uploaded_by):
    new_id, _ = execute(
        "INSERT INTO document (song_id, filename, size, data, uploaded_by) VALUES (%s, %s, %s, %s, %s)",
        (song_id, filename, len(data), data, uploaded_by),
    )
    return new_id


def get_document(doc_id):
    """Everything except the PDF bytes."""
    row = query_one(
        "SELECT d.id, d.song_id, d.filename, d.size, d.annot_version, d.annotations, s.title AS song_title "
        "FROM document d JOIN song s ON s.id = d.song_id WHERE d.id = %s",
        (doc_id,),
    )
    if row:
        row["annotations"] = _text(row["annotations"])
    return row


def get_document_file(doc_id):
    row = query_one("SELECT filename, data FROM document WHERE id = %s", (doc_id,))
    if row:
        row["data"] = bytes(row["data"])
    return row


def save_annotations(doc_id, version, payload):
    """Saves only if nobody saved in between. Returns True on success."""
    _, affected = execute(
        "UPDATE document SET annotations = %s, annot_version = annot_version + 1 "
        "WHERE id = %s AND annot_version = %s",
        (payload, doc_id, version),
    )
    return affected == 1


def delete_document(doc_id):
    execute("DELETE FROM document WHERE id = %s", (doc_id,))
