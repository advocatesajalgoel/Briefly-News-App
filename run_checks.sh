#!/usr/bin/env bash
# Everything that can be verified without a Mac.
#
#   ./run_checks.sh
#
# Needs a PostgreSQL database for the backend tests; set
# BRIEFLY_TEST_DATABASE_URL if it is not at the default local address.
set -uo pipefail
cd "$(dirname "$0")"

status=0
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

step "Backend lint"
(cd backend && python3 -m ruff check app scripts tests) || status=1

step "Backend tests"
(cd backend && python3 -m pytest -q) || status=1

step "iOS static checks"
python3 tools/check_ios_project.py || status=1

step "End-to-end pipeline on the sample feeds"
if (cd backend && python3 -m scripts.load_sample_feeds --reset --podcast > /tmp/briefly-pipeline.json); then
  python3 - <<'PY'
import json
with open("/tmp/briefly-pipeline.json") as handle:
    data = json.load(handle)
print(f"  articles     {data['ingest']['articles_created']}")
print(f"  stories      {data['clustering']['created']}")
print(f"  published    {data['processing']['published']}"
      f"  flagged {data['processing']['flagged']}")
for kind in ("daily", "deep_dive"):
    episode = data.get(kind)
    if episode:
        print(f"  {kind:12} {episode['status']}  qc_passed={episode['qc_passed']}")
PY
else
  status=1
fi

if [ "$status" -eq 0 ]; then
  printf '\n\033[32mAll checks passed.\033[0m\n'
else
  printf '\n\033[31mSomething failed — see above.\033[0m\n'
fi
exit "$status"
