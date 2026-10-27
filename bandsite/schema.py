"""Creates missing tables and the default keywords. Safe to run on every start."""

PHASE = "Phase"
MOOD = "Mood"

DEFAULT_KEYWORDS = {
    PHASE: ["Idea", "Learning", "Almost ready", "Stage-ready"],
    MOOD: ["Calm", "Emotional", "Cheerful", "Energetic", "Dark"],
}

_TABLE_OPTIONS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

STATEMENTS = [
    f"""
    CREATE TABLE IF NOT EXISTS band_member (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        name          VARCHAR(80)  NOT NULL,
        email         VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        instrument    VARCHAR(80)  NULL,
        is_admin      TINYINT(1)   NOT NULL DEFAULT 0,
        created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) {_TABLE_OPTIONS}
    """,
    f"""
    CREATE TABLE IF NOT EXISTS keyword (
        id       INT AUTO_INCREMENT PRIMARY KEY,
        name     VARCHAR(60) NOT NULL UNIQUE,
        is_fixed TINYINT(1)  NOT NULL DEFAULT 0
    ) {_TABLE_OPTIONS}
    """,
    f"""
    CREATE TABLE IF NOT EXISTS keyword_value (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        keyword_id INT         NOT NULL,
        value      VARCHAR(60) NOT NULL,
        sort_order INT         NOT NULL DEFAULT 0,
        UNIQUE KEY uq_value_per_keyword (keyword_id, value),
        FOREIGN KEY (keyword_id) REFERENCES keyword (id) ON DELETE CASCADE
    ) {_TABLE_OPTIONS}
    """,
    f"""
    CREATE TABLE IF NOT EXISTS song (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        title       VARCHAR(200) NOT NULL,
        artist      VARCHAR(200) NOT NULL,
        capo        INT          NOT NULL DEFAULT 0,
        information TEXT         NULL,
        youtube_url VARCHAR(500) NULL,
        phase_id    INT          NULL,
        mood_id     INT          NULL,
        created_by  INT          NULL,
        created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (phase_id)   REFERENCES keyword_value (id) ON DELETE SET NULL,
        FOREIGN KEY (mood_id)    REFERENCES keyword_value (id) ON DELETE SET NULL,
        FOREIGN KEY (created_by) REFERENCES band_member (id)   ON DELETE SET NULL
    ) {_TABLE_OPTIONS}
    """,
    f"""
    CREATE TABLE IF NOT EXISTS song_singer (
        song_id   INT NOT NULL,
        member_id INT NOT NULL,
        PRIMARY KEY (song_id, member_id),
        FOREIGN KEY (song_id)   REFERENCES song (id)        ON DELETE CASCADE,
        FOREIGN KEY (member_id) REFERENCES band_member (id) ON DELETE CASCADE
    ) {_TABLE_OPTIONS}
    """,
    f"""
    CREATE TABLE IF NOT EXISTS document (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        song_id       INT          NOT NULL,
        filename      VARCHAR(255) NOT NULL,
        size          INT          NOT NULL,
        data          LONGBLOB     NOT NULL,
        annotations   LONGTEXT     NULL,
        annot_version INT          NOT NULL DEFAULT 0,
        uploaded_by   INT          NULL,
        created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (song_id)     REFERENCES song (id)        ON DELETE CASCADE,
        FOREIGN KEY (uploaded_by) REFERENCES band_member (id) ON DELETE SET NULL
    ) {_TABLE_OPTIONS}
    """,
]


def init_schema(connection):
    cursor = connection.cursor()
    try:
        for statement in STATEMENTS:
            cursor.execute(statement)

        for name, values in DEFAULT_KEYWORDS.items():
            cursor.execute("SELECT id FROM keyword WHERE name = %s", (name,))
            if cursor.fetchone():
                continue  # keep whatever the band has changed since
            cursor.execute("INSERT INTO keyword (name, is_fixed) VALUES (%s, 1)", (name,))
            keyword_id = cursor.lastrowid
            cursor.executemany(
                "INSERT INTO keyword_value (keyword_id, value, sort_order) VALUES (%s, %s, %s)",
                [(keyword_id, value, order) for order, value in enumerate(values)],
            )
        connection.commit()
    finally:
        cursor.close()
