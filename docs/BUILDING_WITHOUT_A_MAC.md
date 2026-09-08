# Building Briefly without Xcode

Everything in this repository can be built, tested and run using free online
services. What follows is what each one gives you, what it costs, and — the part
most guides skip — what it cannot do.

## Read this first: there is a route with no Mac and no caveats

If what you want is *Briefly on your iPhone, today, for nothing*, use the web
app in `site/` and skip the rest of this document. It is described in the
README under **"Put it on your iPhone without a Mac"** and summarised here:

1. Put this repository on GitHub (public).
2. Actions → **Publish site** → Run workflow.
3. Open the address it prints, in Safari, on the phone.
4. Share → **Add to Home Screen**.

That is a real installation: its own icon, full screen, no browser bars, works
offline, refreshes itself twice a day. It is the same stories, the same 30-word
rule, the same source lists and the same audio as the native app, because it is
built from the same database by the same pipeline.

What it is *not*: an App Store app. It cannot be found by searching the App
Store, and iOS gives home-screen web apps a smaller share of the system than
native ones (notifications must be granted explicitly, and background refresh
is not available — Briefly refreshes when you open it).

Everything below is about the **native** app in `ios/`, which is a harder
problem.

---

## The one hard limit (native app)

Compiling a native iOS app requires Apple's toolchain, which only runs on macOS.
No free service changes that. What free services *do* let you do is rent a Mac
for a few minutes at a time, automatically, without owning one.

Signing is the second wall, and the higher one. A compiled `.ipa` is not an
installable app until Apple's servers have signed it against a developer
identity — which means an Apple ID, and a computer running Xcode or a
sideloading tool to do the pairing. There is no website that will do this part
for you, and any that offers to is asking for your Apple ID password.

So the honest picture is:

| Goal | Possible without a Mac? | Cost |
|---|---|---|
| Use Briefly on your iPhone | **Yes** — the web app in `site/` | Free |
| Compile and test the model layer | **Yes**, on Linux | Free |
| Compile the whole app, run its tests | **Yes**, on a cloud Mac | Free |
| Get an installable-shaped `.ipa` | **Yes**, unsigned | Free |
| See the app running on a simulated iPhone | **Yes**, in a browser | Free tier |
| Install the native app on *your own* iPhone | Only with your Apple ID + a computer to pair | Free Apple ID, 7-day expiry |
| TestFlight or the App Store | No | $99/year Apple Developer Program |

The $99 is Apple's, not a tooling limitation. Nothing gets a native app onto
other people's phones without it.

---

## Path 1 — Verify the logic on Linux (30 seconds, no Mac at all)

The models, the Codable layer, the word counter and the formatters are plain
Foundation code. `ios/Package.swift` exposes them as a Swift package so they
compile and test anywhere Swift runs.

Run it on **[replit.com](https://replit.com)**, **[GitHub Codespaces](https://github.com/codespaces)**
(60 free core-hours a month), or any Linux box with Swift:

```bash
cd ios
swift build --build-tests
swift test
```

This is not a toy check. It compiles `Story`, `PodcastEpisode`, `NewsCategory`
and the coding configuration for real, and runs the contract tests that decode
the bundled snapshot — the layer where a renamed field silently empties the
whole feed.

A guard in `tools/check_ios_project.py` fails the build if anything in that
layer ever imports SwiftUI, so this path cannot quietly stop working.

```bash
python3 tools/check_ios_project.py
```

runs the rest of the static checks — undefined members, missing View bodies,
Xcode project integrity — and needs nothing but Python.

---

## Path 2 — Build the real app on a free cloud Mac

### GitHub Actions (the recommended route)

GitHub gives **public repositories unlimited free minutes on standard runners,
macOS included**. That is a real Mac with real Xcode, for nothing.

1. Create a free account at [github.com](https://github.com).
2. Create a **public** repository.
3. Push this project:

```bash
cd briefly
git init && git add -A && git commit -m "Briefly"
git branch -M main
git remote add origin https://github.com/YOUR-NAME/briefly.git
git push -u origin main
```

4. Open the **Actions** tab. `.github/workflows/ios-build.yml` starts on its own.

After a few minutes the run page has, under **Artifacts**:

* `Briefly-Simulator.app.zip` — the app built for the iOS Simulator
* `Briefly-unsigned.ipa` — a device build with signing disabled
* `briefly-logs` — full build output and the `.xcresult` test bundle

The run summary shows the Xcode version, the simulator used, and — if the build
failed — the first 40 compiler errors, so you can paste them straight back to me.

> **Private repositories:** the free plan includes 2,000 minutes a month, but
> macOS is billed at about ten times the Linux rate, so budget roughly 200
> macOS minutes. Fine for occasional builds; make the repo public if you want
> them unmetered.

### Codemagic (if the repository must stay private)

[codemagic.io](https://codemagic.io) gives **500 free macOS M2 minutes a month**
regardless of repository visibility. `codemagic.yaml` at the repository root is
already configured — sign in with your Git provider, add the repository, and it
picks the file up. No Apple account is needed for the unsigned workflow.

Its free plan allows one build at a time and keeps artifacts for 30 days.

### What about Xcode Cloud?

It works, but it requires an Apple Developer Program membership, so it is not a
free option.

---

## Path 3 — Actually *see* the app running, in a browser

A simulator build is a real app; it just needs a simulator. Free ways to get one
without a Mac:

**[Appetize.io](https://appetize.io)** streams an iOS Simulator into a browser
tab. Upload the `Briefly-Simulator.app.zip` from your Actions run and you get a
link that shows the app running on a simulated iPhone — swipe gestures, audio,
everything. It has a free tier; check their pricing page for the current
monthly session allowance, as it changes.

Because the app ships with bundled sample stories *and* bundled audio, it works
fully in that browser session with no backend at all.

To automate it, add an `APPETIZE_API_TOKEN` secret and append this to the build
workflow:

```yaml
      - name: Publish to Appetize
        if: success() && env.APPETIZE_API_TOKEN != ''
        env:
          APPETIZE_API_TOKEN: ${{ secrets.APPETIZE_API_TOKEN }}
        run: |
          curl -sS --http1.1 https://APIKEY@api.appetize.io/v1/apps \
            -F "file=@ios/artifacts/Briefly-Simulator.app.zip" \
            -F "platform=ios" | tee /tmp/appetize.json
```

Other browser-based simulator services exist and come and go; Appetize is the
one with the longest track record.

---

## Path 4 — Getting it onto your own iPhone

This is where Apple's rules bite, and where most "no Mac needed" guides get
vague. The truth:

**An iOS app must be signed by an Apple-issued certificate to launch on a
device.** There is no way around it.

| Route | What you need | Lasts |
|---|---|---|
| **SideStore / AltStore** | Free Apple ID | 7 days, auto-renews over Wi-Fi |
| **Signing service** | Free Apple ID + an unsigned `.ipa` | 7 days |
| **Apple Developer Program** | $99/year | 1 year, and TestFlight |

With a free Apple ID you can sign the `Briefly-unsigned.ipa` from your CI run
using [SideStore](https://sidestore.io) — it runs on the iPhone itself and
re-signs the app every seven days over Wi-Fi, so no computer is needed after
setup. Apple limits free accounts to three sideloaded apps at a time.

For anything you want to keep, or share with anyone else, the $99 membership is
the only route. It also unlocks TestFlight, which is by far the easiest way to
put the app on other people's phones. The Codemagic config has a ready-made
TestFlight workflow, commented out, for when you get there.

Apple does [waive the fee](https://developer.apple.com/help/account/membership/fee-waivers/)
for some non-profit, educational and government organisations — worth checking if
one applies to you.

---

## Path 5 — The backend, hosted free

The app is only half of it. To run the real news pipeline online:

**[Render](https://render.com)** — `backend/render.yaml` is a ready blueprint.
New → Blueprint → point it at your repository and it builds the Docker image,
provisions Postgres and sets the environment. Free instances sleep when idle and
take about 30 seconds to wake.

**[Neon](https://neon.tech)** — free Postgres with no time limit, if you would
rather not use Render's own database. Set `BRIEFLY_DATABASE_URL` to its
connection string with the scheme changed to `postgresql+psycopg://`.

**[Fly.io](https://fly.io)** and **[Railway](https://railway.app)** both work
too; the Dockerfile is standard.

Render's free plan has no background worker, so
`.github/workflows/pipeline.yml` runs the schedule instead — it calls the admin
API every two hours and builds the daily briefing at 06:00 IST. Add two repository
secrets and it takes over:

```
BRIEFLY_API_URL       https://your-service.onrender.com
BRIEFLY_ADMIN_TOKEN   from the Render dashboard
```

Then in the app: **Settings → Briefly server → your URL**. The sample banner
disappears and the feed is live.

---

## What I would actually do

0. **Get the web app onto the phone first.** Push to a public GitHub repo, run
   *Publish site*, Add to Home Screen. Ten minutes, no Apple ID, and you are
   reading Briefly on your own phone the same afternoon. Everything below is an
   upgrade from a working app rather than a prerequisite for one.
1. Let the other Actions run on the same push. Free, and they tell you within
   minutes whether the native app compiles — which is the one thing I could not
   verify from here, since no Swift toolchain was reachable in my sandbox.
2. Fix whatever the first build reports. Paste the errors from the run summary
   back to me and I will correct them.
3. Upload the simulator build to Appetize to *see* the native app.
4. Deploy the backend to Render + Neon if you want the native app live too. The
   web app does not need this — its data is built by the Action.
5. Only then decide whether the $99 is worth it. Everything up to that point
   costs nothing.

Expect the first compilation to surface a handful of ordinary Swift errors. I
wrote nearly 5,000 lines of SwiftUI without a compiler, and the static checker
catches typos and structural mistakes but not type inference, `@Observable`
subtleties or SwiftUI API changes. That is the honest gap, and step 1 closes it.

---

## Things that will not work, despite what you may read

* **"iOS emulators for Windows/Linux."** Almost all of them are either Android
  emulators mislabelled, remote-Mac services with a free trial, or malware. A
  genuine iOS Simulator is part of Xcode and runs only on macOS — which is why
  Appetize works: it runs the real thing on real Macs and streams you the screen.
* **Compiling SwiftUI on Linux.** The open-source Swift toolchain has Foundation
  but not SwiftUI or UIKit; those are closed-source Apple frameworks. This is
  exactly why `ios/Package.swift` covers only the Foundation-only layer.
* **Sideloading without any Apple ID.** Signing requires an Apple-issued
  certificate. Free accounts work, with the seven-day limit.
* **A website that installs a native app onto your iPhone for you.** Signing
  needs your Apple ID credentials and a machine to pair with the phone. Any
  service offering to skip that is asking you to hand over your Apple account,
  and enterprise-certificate "app installers" are revoked by Apple in batches.
  If you want a native app with no Mac and no risk, the $99 developer account
  plus a cloud-Mac build is the only clean route.
