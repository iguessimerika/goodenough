# #goodEnough – band site

Flask app with a public landing page and a members-only band area. Data lives in MySQL, accessed with
plain `mysql.connector` functions (`bandsite/db.py`, built on `get_connection()` / `test_connection()`).
Made for Railway.

**Status:** the *Song* area is done (create, edit, delete, search, filter, YouTube, sheet-music PDFs with shared notes).
*Band member* (list) and *Keywords* (manage Phase and Mood) are kept simple.
*Setlist*, *Rehearsal* and *Questionnaire* show a placeholder.

## Deploy on Railway

1. Put this folder in a GitHub repository (the `.env` file is ignored; never commit passwords).
2. Railway: **New Project → Deploy from GitHub repo**.
3. Make sure the project has a **MySQL** service.
4. In the web service's **Variables**, add references to the MySQL service (replace `MySQL` with your service's name):
   - `MYSQLHOST` = `${{MySQL.MYSQLHOST}}`
   - `MYSQLPORT` = `${{MySQL.MYSQLPORT}}`
   - `MYSQLUSER` = `${{MySQL.MYSQLUSER}}`
   - `MYSQLPASSWORD` = `${{MySQL.MYSQLPASSWORD}}`
   - `MYSQLDATABASE` = `${{MySQL.MYSQLDATABASE}}`
   - `SECRET_KEY` = a long random string (`python -c "import secrets; print(secrets.token_hex(32))"`)
   - `BAND_CODE` = the secret band word everyone needs to register
5. **Settings → Networking → Generate Domain**.

On every start `init_db.py` creates missing tables and seeds Phase and Mood values (see `Procfile`).
The first person to register becomes admin.

## Run locally

```
pip install -r requirements.txt
cp .env.example .env      # fill in the values
python init_db.py
flask --app wsgi run
```
`mysql.railway.internal` only works inside Railway. Locally, use the MySQL service's public connection
(enable it under the service's Networking settings) and put its host, port, user, password and database in `.env`.
Check the connection any time with `python -m bandsite.db`.

## Where do I change what?

- Landing page texts: `bandsite/band_info.py`
- Look: `bandsite/static/css/style.css`
- All SQL: `bandsite/db.py`
- Default Phase/Mood values: `DEFAULT_KEYWORDS` in `bandsite/db.py` (or the Keywords tab)

## Good to know

- Sheet-music PDFs are stored in the database (up to 16 MB), not on disk. Railway wipes files on every deploy; the database stays.
- Notes in the editor are shared by the whole band. Saving checks whether someone saved in between.
- `CREATE TABLE IF NOT EXISTS` adds new tables but never changes existing ones. Changing columns later needs a migration (an `ALTER TABLE`).
- Table names are English (`members`, `songs`, …). If you already ran the German version against this database, use a fresh database or drop the old tables.
- There is no limit on failed sign-in attempts.
