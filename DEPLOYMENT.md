# Deployment

## The zero-server deployment

Before the real thing, note that there is a deployment with no server in it at
all, and it is the one most people should start with.

`.github/workflows/publish-site.yml` starts a PostgreSQL service container on a
free GitHub Actions runner, runs migrations, ingests, clusters, extracts,
summarises, quality-checks, narrates and voices — then calls
`scripts/export_static_site.py`, which replays the read API through
`fastapi.testclient` and writes its responses to disk:

```
site/api/stories.json      every published story, ranked, with sources
site/api/categories.json   the sections
site/api/episodes.json     episodes, audio rewritten to relative paths
site/api/status.json       build time, publisher count, provider names
site/media/…               the generated mp3s
```

That directory is uploaded as a Pages artifact and served. The database is
thrown away with the runner. Nothing persists between runs except
`backend/data/sources.json`, which the workflow commits back so that feeds
found unreachable stay disabled.

The trade-offs are real and worth stating: there is no API to query, no
bookmarking across devices, no on-demand refresh, and the news is as fresh as
the last scheduled run rather than continuous. In exchange it costs nothing,
has no attack surface, cannot fall over under load, and has no credentials to
leak. For one reader on one phone that is the better deal.

Everything below is the real deployment, for when it is not.

---

## What you need

| | Minimum | Comfortable |
|---|---|---|
| Python | 3.11 | 3.12 |
| PostgreSQL | 14 | 16 |
| RAM | 1 GB | 2 GB |
| Disk | 10 GB | 40 GB (audio accumulates) |
| Also | `espeak-ng`, `ffmpeg` — only if you use the local TTS provider | |

No external account is required to run Briefly. Hosted model and voice providers
are optional upgrades.

---

## 1. Database

```bash
sudo -u postgres createuser briefly --pwprompt
sudo -u postgres createdb briefly --owner=briefly
```

```bash
cd backend
cp .env.example .env
```

Set at minimum:

```dotenv
BRIEFLY_ENV=production
BRIEFLY_DATABASE_URL=postgresql+psycopg://briefly:YOUR_PASSWORD@localhost:5432/briefly
BRIEFLY_ADMIN_TOKEN=            # python -c "import secrets;print(secrets.token_urlsafe(32))"
BRIEFLY_STORAGE_PUBLIC_BASE_URL=https://briefly.example.com/media
BRIEFLY_USER_AGENT=BrieflyNewsBot/1.0 (+https://example.com/bot)
```

Put a real, contactable URL in the User-Agent. Publishers use it to reach you,
and an honest bot string is part of being allowed to keep reading their feeds.

```bash
pip install -e .
alembic upgrade head
python -m scripts.seed_reference_data
```

## 2. Check which feeds actually work

Feed URLs move. The registry ships with the documented pattern for each
publisher and a `feed_verified: false` flag; nothing is presented as confirmed
until you have checked it from your own network:

```bash
python -m scripts.verify_feeds          # report
python -m scripts.verify_feeds --write  # disable the ones that failed
```

Anything reported `SKIP` was refused by `robots.txt` — that is the system
working, not a bug. Do not try to work around it.

Reuters, AP and PTI ship **disabled**: they need a commercial licence. Leave
them off until you have one. They still appear on cards when Google News credits
them, with a link and no stored summary.

## 3. First run

```bash
python -m scripts.run_pipeline all
python -m scripts.run_pipeline daily-podcast
```

Check what happened:

```bash
curl -s localhost:8000/v1/health | jq
curl -s -H "X-Admin-Token: $BRIEFLY_ADMIN_TOKEN" localhost:8000/v1/admin/stats | jq
curl -s -H "X-Admin-Token: $BRIEFLY_ADMIN_TOKEN" localhost:8000/v1/admin/stories/flagged \
  | jq '.items[].qc_report.issues'
```

Flagged stories are the interesting output: they tell you which quality gate
fired and why.

## 4. Services

`/etc/systemd/system/briefly-api.service`:

```ini
[Unit]
Description=Briefly API
After=network.target postgresql.service

[Service]
Type=simple
User=briefly
WorkingDirectory=/opt/briefly/backend
EnvironmentFile=/opt/briefly/backend/.env
ExecStart=/opt/briefly/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/briefly/backend/var

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/briefly-worker.service`:

```ini
[Unit]
Description=Briefly pipeline worker
After=network.target postgresql.service

[Service]
Type=simple
User=briefly
WorkingDirectory=/opt/briefly/backend
EnvironmentFile=/opt/briefly/backend/.env
Environment=BRIEFLY_SCHEDULER_ENABLED=true
ExecStart=/opt/briefly/backend/.venv/bin/python -m app.jobs.worker
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```

> **Run exactly one worker.** The API service must keep
> `BRIEFLY_SCHEDULER_ENABLED=false`. Two schedulers means two daily episodes.

```bash
sudo systemctl enable --now briefly-api briefly-worker
```

Schedules are cron expressions in the environment:

```dotenv
BRIEFLY_SCHEDULER_ENABLED=true
BRIEFLY_INGEST_CRON=*/20 * * * *      # ingest, cluster, summarise, gate
BRIEFLY_DAILY_PODCAST_CRON=30 5 * * * # 05:30 in BRIEFLY_SCHEDULER_TIMEZONE
BRIEFLY_SCHEDULER_TIMEZONE=Asia/Kolkata
```

## 5. TLS and the reverse proxy

```nginx
server {
    listen 443 ssl http2;
    server_name briefly.example.com;

    ssl_certificate     /etc/letsencrypt/live/briefly.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/briefly.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Serve audio directly; it is immutable once written.
    location /media/ {
        alias /opt/briefly/backend/var/media/;
        add_header Cache-Control "public, max-age=604800, immutable";
    }

    # The admin surface is not for the public internet.
    location /v1/admin/ {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://127.0.0.1:8000;
    }
}
```

The iPhone app requires HTTPS. `Info.plist` allows cleartext for `localhost`
only, so the simulator can reach a development backend — nothing else.

## 6. Audio storage

Local disk is fine for one server. For anything larger:

```dotenv
BRIEFLY_STORAGE_BACKEND=s3
BRIEFLY_S3_BUCKET=briefly-media
AWS_REGION=ap-south-1
BRIEFLY_STORAGE_PUBLIC_BASE_URL=https://cdn.example.com
# Prefer an instance role; only set keys when you have no other option.
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

Works with any S3-compatible service (Cloudflare R2, MinIO, Wasabi) via
`BRIEFLY_S3_ENDPOINT_URL`. Install the extra: `pip install -e ".[s3]"`.

## 7. Optional upgrades

**Better prose:**

```dotenv
BRIEFLY_LLM_PROVIDER=anthropic
BRIEFLY_LLM_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...
```

**Better voice:**

```dotenv
BRIEFLY_TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
```

Both fall back to the offline provider when the key is missing or the call
fails. Grounding, the 30-word rule and every quality gate apply identically
whichever backend produced the text — a hosted model cannot widen what Briefly
is allowed to say.

## 8. Building and shipping the app

**This is the one part that cannot be done for you: it needs your Apple
account and a Mac.**

1. `open ios/Briefly.xcodeproj`
2. Select the **Briefly** target → **Signing & Capabilities**
   * Team: your Apple Developer team
   * Bundle identifier: change `com.briefly.app` to something you own
   * **Background Modes → Audio** is already declared in `Info.plist`; confirm
     the capability is present.
3. Optionally set `BRIEFLY_API_BASE_URL` in Build Settings to bake in your
   server address. It is a public URL — never put a credential there.
4. Run on a simulator (⌘R) or a device.
5. Archive → Distribute → App Store Connect.

If you would rather regenerate the project (after a merge, or to change the
identifier cleanly):

```bash
brew install xcodegen
cd ios && xcodegen generate
```

### App Review notes

* The app displays headlines, short original summaries and links. It does not
  reproduce article bodies.
* Background audio is used for the news briefing and is declared.
* No tracking, no advertising identifier, no analytics SDK. The one identifier
  is a random value in the keychain, used only if the reader turns on bookmark
  sync.
* Privacy nutrition label: *Data Not Collected*, unless you add analytics.

## 9. Operating it

```bash
# what the pipeline is doing
curl -s -H "X-Admin-Token: $TOKEN" localhost:8000/v1/admin/stats | jq

# which sources are failing
curl -s -H "X-Admin-Token: $TOKEN" localhost:8000/v1/admin/sources \
  | jq '.items[] | select(.consecutive_failures > 0)'

# review queue
curl -s -H "X-Admin-Token: $TOKEN" localhost:8000/v1/admin/stories/flagged | jq
```

Back up the database (`pg_dump`) and the media directory. `pipeline_runs` keeps
an audit row per run.

Every story is reproducible: its articles, extracted facts with evidence spans,
and QC report are all retained.
