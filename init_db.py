"""Creates missing tables and seeds the default keywords.

Runs on every start (see Procfile). Existing data is left untouched.
"""
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from bandsite import db  # noqa: E402

ATTEMPTS = 7

for attempt in range(1, ATTEMPTS + 1):
    try:
        db.init_schema()
        print("Database ready.")
        break
    except Exception as exc:  # the database is sometimes not reachable yet right after a deploy
        print(f"Database not reachable yet (attempt {attempt}/{ATTEMPTS}): {exc!r}", file=sys.stderr)
        if attempt == ATTEMPTS:
            raise
        time.sleep(4)
