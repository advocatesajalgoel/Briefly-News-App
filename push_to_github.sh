#!/usr/bin/env bash
# Push Briefly to GitHub so the free cloud-Mac build runs.
#
#   ./push_to_github.sh https://github.com/YOUR-NAME/briefly.git
#
# Create the repository first at github.com/new. Make it PUBLIC if you want
# unlimited free macOS build minutes; private works too, on a 2,000-minute
# monthly allowance where macOS costs about ten times the Linux rate.
set -euo pipefail
cd "$(dirname "$0")"

remote="${1:-}"
if [ -z "$remote" ]; then
  echo "usage: $0 <git remote url>" >&2
  echo "   e.g. $0 https://github.com/yourname/briefly.git" >&2
  exit 2
fi

# Refuse to push a real .env, whatever .gitignore says.
if git ls-files --cached --others --exclude-standard | grep -qx "backend/.env"; then
  echo "backend/.env is about to be committed. Remove it first." >&2
  exit 1
fi

if [ ! -d .git ]; then
  git init
fi

git add -A
if ! git diff --cached --quiet; then
  git commit -m "Briefly — transparent news app and backend"
fi

git branch -M main
if git remote get-url origin > /dev/null 2>&1; then
  git remote set-url origin "$remote"
else
  git remote add origin "$remote"
fi

git push -u origin main

cat <<'EOF'

Pushed.

To get Briefly onto your iPhone — no Mac, no Apple ID, no cost:

  1. Open the repository's Actions tab.
  2. Choose "Publish site" on the left, then press "Run workflow".
     It takes five to ten minutes: it fetches the news, builds the stories,
     records the briefing, and publishes the app.
  3. When it turns green, the run's summary page prints an address like
       https://YOUR-NAME.github.io/briefly/
  4. Open that address in Safari ON YOUR IPHONE.
     Tap Share, scroll down, tap "Add to Home Screen".

After that it refreshes itself twice a day and works offline.

Meanwhile the other workflows run on their own:
    CI            Linux — backend tests, Swift model layer, static checks
    iOS build     a free cloud Mac — compiles the native app, runs XCTest
  When "iOS build" finishes it uploads:
    Briefly-Simulator.app.zip   run it in a browser via appetize.io
    Briefly-unsigned.ipa        input for a signing service or SideStore
  If it failed, the run Summary lists the compiler errors. Paste them back
  and they can be fixed.

Full detail: docs/BUILDING_WITHOUT_A_MAC.md
EOF
