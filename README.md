# Pocket Notes — Ubuntu 24.04 / Lightsail lab

A small server-rendered notes website for a cloud infrastructure exercise. Flask handles registration, login, sessions, CSRF protection, and note operations. SQLite stores users and notes on the Lightsail instance. Passwords are stored as Werkzeug password hashes, never as plain text. Every note query is scoped to the signed-in user's ID.

- **Application:** Python 3 + Flask
- **Database:** SQLite (`instance/notes.sqlite3` by default)
- **Port:** `8080` (TCP)
- **Deploy directory:** `/opt/website`
- **Initial setup:** `flask --app app init-db`

## 1. Ubuntu packages

The supplied OpenTofu template runs `apt-get install -y git ${local.website_packages}`. Set `WEBSITE_PACKAGES` to:

```text
python3-venv python3-pip
```

No separate database server is needed; Python's `sqlite3` module uses the SQLite library provided by Ubuntu's Python build.

## 2. Configure the app on the instance

After the template clones this public repository into `/opt/website`, connect by SSH and run:

```bash
cd /opt/website
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Edit `.env` and replace `SECRET_KEY` with the random value printed above. Keep `.env` private; it is excluded from Git. Confirm `DATABASE_PATH=/opt/website/instance/notes.sqlite3` and `PORT=8080`, then initialize the database:

```bash
flask --app app init-db
```

Start the server for the lab:

```bash
.venv/bin/gunicorn --workers 2 --bind 0.0.0.0:8080 app:app
```

Keep this SSH session running while trying the site. For a persistent service across SSH disconnects, use the optional systemd setup below.

## 3. Optional systemd service

Create `/etc/systemd/system/pocket-notes.service`:

```ini
[Unit]
Description=Pocket Notes Flask application
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/website
EnvironmentFile=/opt/website/.env
ExecStart=/opt/website/.venv/bin/gunicorn --workers 2 --bind 0.0.0.0:8080 app:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pocket-notes
sudo systemctl status pocket-notes --no-pager
```

## 4. Verify in a browser

With `public_http = true` in the Terraform template and the service running, open:

```text
http://INSTANCE_STATIC_IPV4:8080
```

1. Choose **Get started**, register a username and a password of at least 10 characters.
2. Create a note and confirm it appears under **My notes**. This demonstrates an authenticated database write and read.
3. Edit the note, then delete it to demonstrate update and delete operations.
4. Sign out and sign in again with the same account. The note list is loaded from SQLite.
5. (Optional ownership check) Register a second account; its notes page must not show the first user's notes.

The database file is at `/opt/website/instance/notes.sqlite3`. A basic service check is:

```bash
sudo systemctl status pocket-notes --no-pager
```

For a direct database check, install `sqlite3` (`sudo apt-get install -y sqlite3`) and run:

```bash
sqlite3 /opt/website/instance/notes.sqlite3 '.tables'
sqlite3 /opt/website/instance/notes.sqlite3 'select username, length(password_hash) from users;'
sqlite3 /opt/website/instance/notes.sqlite3 'select user_id, title from notes;'
```

Do not include password hashes, credentials, or `.env` contents in screenshots.

## Cloudflare tunnel note

The app listens on port 8080. For the lab's SSH forward use local port 8080 to remote `localhost:8080`, then run `cloudflared tunnel --url http://localhost:8080`. Keep the SSH forward and cloudflared running. Browser cookies use `SameSite=Lax`; set `COOKIE_SECURE=true` only if the browser visits the app exclusively over HTTPS. Quick Tunnels are temporary and their hostname changes when recreated.

## Security and lab limits

- Do not commit `.env`, the SQLite database, or SSH private keys. `.gitignore` excludes them.
- Use a unique random `SECRET_KEY`; the placeholder is intentionally invalid, so the app refuses to start until changed.
- Passwords are hashed with Werkzeug's secure password hashing helper. Forms use Flask-WTF CSRF protection.
- User input is parameterized in SQL and note operations check ownership on every request.
- This is a classroom demonstration, not a hardened public production service. Use HTTPS for public access, keep dependencies updated, back up the SQLite file, and add operational protections before real use.

## Publish on GitHub

Create an empty **public** GitHub repository, then from this project directory:

```bash
git init
git add app.py requirements.txt .env.example .gitignore README.md templates static
git commit -m "Create Pocket Notes lab website"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Use that repository URL in `GITHUB_REPOSITORY_URL` in the provided Terraform template. Since the template clones the repository, do not include real credentials or `.env` in Git.
