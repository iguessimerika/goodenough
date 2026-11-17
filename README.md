# #goodEnough – band site

Flask app with a public landing page and a members-only band area. Data lives in MySQL, accessed with
plain `mysql.connector` functions (`bandsite/db.py`, built on `get_connection()` / `test_connection()`).
Made for Railway.

**Status:** the *Song* area is done (create, edit, delete, search, filter, YouTube, sheet-music PDFs with shared notes).
*Band member* (list) and *Keywords* (manage Phase and Mood) are kept simple.
*Setlist* is done, including the sheet music of a set opened in running order.
*Rehearsal* is done: Mondays planned automatically, yes/no answers, food duty for late cancellations.
*Questionnaire* shows a placeholder.

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

## Sheet music for a gig

On a setlist, **Open sheet music** (per set) or **Open all sheet music** shows every PDF of the songs
one after another, in the running order, with the band's notes on top. Songs without a PDF still
appear, so the order on screen always matches the setlist.

- Next / previous page: `→` / `←`, `Page Down` / `Page Up`, `Space`, or tap the right / left third of a page.
  Bluetooth page-turn pedals usually send exactly these keys.
- Next / previous song: the ◀ ▶ buttons, the song list in the bar, or `N` / `P`.
- **Whole page** fits one page on the screen; the choice is remembered on that device.
- **Full screen** hides the browser bars. The screen stays on while the view is open (where the browser supports it).
- **Download as one PDF** merges all PDFs of a set into one file with a bookmark per song, for apps
  like forScore or for when there's no internet at the venue. The band's notes are not part of that file.

## Rehearsals

- Every Monday for the next three months is created automatically when someone opens *Rehearsal*.
  A single Monday can be cancelled (e.g. a public holiday); extra days can be added.
- Every member answers **I'm in** or **Can't make it**. Cancelling is free until the end of the
  Saturday before (German time). Cancelling later means bringing food to the next rehearsal; this
  shows up under *Band member* and on the rehearsal page until someone presses **Brought it**.
  Saying "I'm in" again before the rehearsal drops the food duty; a cancelled rehearsal never costs food.
- Will it happen? **Yes** when guitar (Gitarre), vocals (Gesang) and drums (Schlagzeug) are in,
  **Maybe** with at least one singer and one other instrument, otherwise **No**. The rule lives in
  `outlook()` in `bandsite/views/rehearsals.py` and uses the members' instruments.
- Past rehearsals are hidden; **Clean up past rehearsals** deletes them (food duties are kept).
- Each rehearsal can have a setlist, single songs and notes.

## Good to know

- Sheet-music PDFs are stored in the database (up to 16 MB), not on disk. Railway wipes files on every deploy; the database stays.
- Notes in the editor are shared by the whole band. Saving checks whether someone saved in between.
- `CREATE TABLE IF NOT EXISTS` adds new tables but never changes existing ones. Changing columns later needs a migration (an `ALTER TABLE`).
- Table names are English (`members`, `songs`, …). If you already ran the German version against this database, use a fresh database or drop the old tables.
- There is no limit on failed sign-in attempts.
