#!/usr/bin/env bash
# Build Briefly's web app from nothing: fetch the news, cluster it, extract and
# check the facts, write the cards, record the briefing, write the site.
#
# This is everything the publishing workflow does, kept in one script so the
# workflow itself stays short enough to paste. It runs on a fresh GitHub Actions
# runner and needs no secret, no account and no server.
#
#   bash build_site.sh          # writes ./site/api and ./site/media
#
# Set BRIEFLY_DATABASE_URL beforehand to use a database you already have;
# otherwise the runner's own PostgreSQL is started and given a role whose
# password is generated for this run and never written anywhere.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"

group()    { echo "::group::$1"; }
endgroup() { echo "::endgroup::"; }
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"
RUN_JSON="$(mktemp)"; RUN_LOG="$(mktemp)"

# ---------------------------------------------------------------- system ----
group "Install speech and audio tools"
if ! command -v espeak-ng >/dev/null || ! command -v ffmpeg >/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq --no-install-recommends espeak-ng ffmpeg
fi
endgroup

# -------------------------------------------------------------- database ----
if [ -z "${BRIEFLY_DATABASE_URL:-}" ]; then
  group "Start a throwaway database"
  command -v psql >/dev/null || sudo apt-get install -y -qq postgresql
  sudo systemctl start postgresql.service 2>/dev/null || sudo service postgresql start
  for _ in $(seq 1 30); do pg_isready -q -h localhost && break; sleep 1; done
  pg_isready -h localhost

  # Made up now, used for the next few minutes, gone with the runner.
  DB_PASSWORD="$(openssl rand -hex 24)"
  echo "::add-mask::${DB_PASSWORD}"
  sudo -u postgres psql -q -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS briefly;
DROP ROLE IF EXISTS briefly;
CREATE ROLE briefly LOGIN PASSWORD '${DB_PASSWORD}';
CREATE DATABASE briefly OWNER briefly;
SQL
  export BRIEFLY_DATABASE_URL="postgresql+psycopg://briefly:${DB_PASSWORD}@localhost:5432/briefly"
  endgroup
fi

export BRIEFLY_ENV="${BRIEFLY_ENV:-production}"
export BRIEFLY_LLM_PROVIDER="${BRIEFLY_LLM_PROVIDER:-rule_based}"
export BRIEFLY_TTS_PROVIDER="${BRIEFLY_TTS_PROVIDER:-local}"
export BRIEFLY_STORAGE_BACKEND=local
export BRIEFLY_PROCESS_BATCH_SIZE="${BRIEFLY_PROCESS_BATCH_SIZE:-400}"
# Say who is asking, with a link back to the repository that is running this.
export BRIEFLY_USER_AGENT="${BRIEFLY_USER_AGENT:-BrieflyNewsBot/1.0 (+https://github.com/${GITHUB_REPOSITORY:-briefly})}"

# ---------------------------------------------------------------- python ----
group "Install Briefly"
python -m pip install -q --disable-pip-version-check -e "./backend"
endgroup

cd "$ROOT/backend"
group "Create the database schema and load the source registry"
alembic upgrade head
python -m scripts.seed_reference_data
endgroup

# -------------------------------------------------------------- pipeline ----
group "Fetch, cluster, extract, summarise, quality-check"
set +e
python -m scripts.run_pipeline all > "$RUN_JSON" 2> "$RUN_LOG"
pipeline_exit=$?
set -e
tail -n 40 "$RUN_LOG" || true
published="$(python - "$RUN_JSON" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as handle:
        data = json.load(handle)
except Exception:
    data = {}                      # a crashed run published nothing
print(data.get("processing", {}).get("published", 0))
PY
)"
echo "pipeline exit ${pipeline_exit}, stories published: ${published}"
endgroup

if [ "$published" = "0" ]; then
  # A day when no feed answers should still leave a working app on the phone,
  # not an empty one. The app says on screen that these are sample stories,
  # and every outlet in them is invented.
  echo "::warning::No live stories were published. Falling back to the built-in sample stories."
  python -m scripts.load_sample_feeds --reset > /dev/null
fi

group "Narrate and voice the briefing"
python -m scripts.run_pipeline daily-podcast || echo "::warning::Briefly Daily was not produced on this run."
python -m scripts.run_pipeline deep-dive    || echo "::warning::The Deep Dive was not produced on this run."
endgroup

group "Write the site"
python -m scripts.export_static_site --out "$ROOT/site" --run-stats "$RUN_JSON"
touch "$ROOT/site/.nojekyll"
endgroup

# --------------------------------------------------------------- summary ----
python - "$RUN_JSON" "$ROOT/site/api/status.json" >> "$SUMMARY" <<'PY'
import json, sys

def load(path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except Exception:
        return {}

run, status = load(sys.argv[1]), load(sys.argv[2])
ingest = run.get("ingest", {})

print("## Briefly\n")
if status.get("sample"):
    print("> **Sample stories were published.** No live story made it through on this "
          "run, so the app is showing its built-in examples and says so on screen. "
          "The table below shows what each feed answered.\n")
print(f"- **{status.get('stories', 0)} stories** from **{status.get('publisher_count', 0)} publishers**")
print(f"- **{status.get('episodes', 0)} audio episodes**")
if ingest:
    print(f"- feeds: {ingest.get('feeds_ok', 0)} answered, {ingest.get('feeds_failed', 0)} failed, "
          f"{ingest.get('feeds_skipped', 0)} skipped — {ingest.get('articles_created', 0)} reports kept, "
          f"{ingest.get('articles_not_reports', 0)} set aside as not news reports")
for stage in ("clustering", "processing"):
    if run.get(stage):
        bits = ", ".join(f"{k} {v}" for k, v in run[stage].items()
                         if isinstance(v, int) and k != "duration_ms")
        print(f"- {stage}: {bits}")

sections = status.get("by_section") or {}
if sections:
    print("\n| section | stories |\n|---|---|")
    for slug, count in sorted(sections.items(), key=lambda kv: -kv[1]):
        print(f"| {slug} | {count} |")

feeds = ingest.get("feeds") or []
if feeds:
    print("\n<details><summary>What each feed answered</summary>\n")
    print("| publisher | result | items | feed |\n|---|---|---|---|")
    for feed in feeds:
        detail = (feed.get("detail") or "").replace("|", "/")[:90]
        result = feed.get("status", "") + (f" — {detail}" if detail else "")
        print(f"| {feed.get('source')} | {result} | {feed.get('items', 0)} | `{feed.get('url')}` |")
    print("\n</details>")
PY
echo "Site written to $ROOT/site"
