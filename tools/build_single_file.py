#!/usr/bin/env python3
"""Fold the web app and one build of the news into a single HTML file.

    python tools/build_single_file.py [--out preview/briefly-app.html]

`site/index.html` fetches its stories from `api/*.json` next to it. That is the
right shape for GitHub Pages, and the wrong shape for handing somebody one file
they can open. This script produces the other shape: the same app, byte for byte
the same markup and CSS, with the JSON and the audio carried inside it.

The result has no network dependency of any kind — no font CDN, no API, no
media host — so it works from a phone with no signal, and it can be published
anywhere that serves a page.

What it is *not* is live. A single file is a photograph of the news at the
moment it was built, so the script stamps the build time into the page and the
app says on screen that this copy does not refresh itself. A news app that
quietly showed you last week's headlines as though they were today's would be
the exact failure Briefly is built to avoid.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

# --- demo mode --------------------------------------------------------------
#
# The sample stories describe invented events — a cyclone called Verath, a city
# called Kalpore. Inside the repository they carry real mastheads, because they
# exercise the real source registry and every screen says "Sample stories".
#
# A page published at a public address is a different thing. Nobody arriving at
# a URL should read "BBC News — Ordelia keeps rates on hold" and have to work
# out that neither the outlet's involvement nor the country exists. Briefly's
# entire premise is that it never invents an attribution, and a demo that
# breaks that premise to show it off is not worth publishing.
#
# So a published build swaps every masthead for an outlet that does not exist,
# keeping the *kind* of outlet — official, international, national — because
# that is what the Source Diversity panel is actually demonstrating.
DEMO_PUBLISHERS = {
    "Press Information Bureau (Government of India)":
        "Ordelia State Press Office",
    "BBC News": "Continental Review",
    "Al Jazeera English": "The Meridian Post",
    "The Guardian": "Northwatch Daily",
    "The Hindu": "The Kalpore Herald",
    "The Indian Express": "Ordelia Chronicle",
    "The Economic Times": "The Ledger",
    "The Times of India": "Ordelia Times",
    "Hindustan Times": "The National Record",
    "NDTV": "Ordelia News Network",
}


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def anonymise(payload: dict) -> dict:
    """Return the payload with every real masthead replaced.

    Done on the serialised JSON rather than field by field, because a
    publisher's name turns up in more places than the source list: inside a
    summary's attribution clause, in the line that says which outlet disputes
    a figure, in a fact's evidence, and in the narrated script. Missing one of
    those is exactly the failure this function exists to prevent, so it
    replaces the text everywhere and does not try to be clever about where.

    It runs *before* the audio is embedded, so it can never corrupt base64.
    """
    text = json.dumps(payload, ensure_ascii=False)
    for real, fake in DEMO_PUBLISHERS.items():
        text = text.replace(real, fake)
    # Short forms that appear without the full masthead.
    for real, fake in (("Press Information Bureau", "Ordelia State Press Office"),
                       ("Government of India", "the Ordelia government")):
        text = text.replace(real, fake)
    return json.loads(text)


# Audio dominates the file size. Above this, episodes are listed with their
# scripts and chapter marks but no player, rather than producing a page too
# large to load on a phone.
MAX_TOTAL_AUDIO_BYTES = 9 * 1024 * 1024


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def load(name: str) -> object:
    return json.loads((SITE / "api" / f"{name}.json").read_text(encoding="utf-8"))


def to_artifact(html: str) -> str:
    """Strip the document shell so the page can be published as an Artifact.

    The publisher supplies its own doctype, <head> and <body>, so those have to
    go. The head tags that make iOS treat this as an app rather than a web page
    cannot simply be dropped, though — without them "Add to Home Screen" gives
    you a Safari bookmark with a screenshot for an icon. So they are put back
    into document.head at runtime, before anyone can reach the Share button,
    and the icon travels as a data URI because there is no icons/ directory on
    an Artifact's origin.
    """
    for tag in ("<!doctype html>", '<html lang="en">', "<head>", "</head>",
                "<body>", "</body>", "</html>"):
        html = html.replace(tag, "", 1)

    # The skeleton already sets charset and viewport; ours differ only in
    # viewport-fit, which the injector below restores.
    drop = (
        '<meta charset="utf-8">',
        ('<meta name="viewport" content="width=device-width, initial-scale=1,'
         ' viewport-fit=cover, maximum-scale=1">'),
        '<link rel="manifest" href="manifest.webmanifest">',
        '<link rel="apple-touch-icon" href="icons/icon-180.png">',
        '<link rel="icon" href="icons/icon-192.png">',
    )
    for tag in drop:
        html = html.replace(tag, "")

    icon = data_uri(SITE / "icons" / "icon-180.png")
    injector = (
        "<script>\n"
        "/* Put back the head tags the Artifact skeleton owns, so that adding\n"
        "   this to an iPhone home screen produces an app icon and a full-screen\n"
        "   window rather than a Safari bookmark. Safari reads these when the\n"
        "   user taps Share, which is always after load. */\n"
        "(function () {\n"
        "  const head = document.head;\n"
        "  const meta = (name, content) => {\n"
        "    let el = head.querySelector(`meta[name=\"${name}\"]`);\n"
        "    if (!el) { el = document.createElement(\"meta\");"
        " el.name = name; head.appendChild(el); }\n"
        "    el.content = content;\n"
        "  };\n"
        "  meta(\"viewport\","
        " \"width=device-width, initial-scale=1, viewport-fit=cover, maximum-scale=1\");\n"
        "  meta(\"apple-mobile-web-app-capable\", \"yes\");\n"
        "  meta(\"mobile-web-app-capable\", \"yes\");\n"
        "  meta(\"apple-mobile-web-app-title\", \"Briefly\");\n"
        "  meta(\"apple-mobile-web-app-status-bar-style\", \"default\");\n"
        "  const link = document.createElement(\"link\");\n"
        "  link.rel = \"apple-touch-icon\";\n"
        f'  link.href = "{icon}";\n'
        "  head.appendChild(link);\n"
        "})();\n"
        "</script>\n"
    )
    return injector + html.lstrip("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "preview" / "briefly-app.html"))
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--demo", action="store_true",
                        help="replace real mastheads with invented outlets")
    parser.add_argument("--artifact", action="store_true",
                        help="emit body-only markup for the Artifact publisher")
    args = parser.parse_args()

    html = (SITE / "index.html").read_text(encoding="utf-8")

    stories = load("stories")
    categories = load("categories")
    episodes = load("episodes")
    status = load("status")

    if args.demo:
        swapped = anonymise({"stories": stories, "categories": categories,
                             "episodes": episodes, "status": status})
        stories, categories, episodes, status = (
            swapped["stories"], swapped["categories"],
            swapped["episodes"], swapped["status"])

    # --- audio -------------------------------------------------------------
    total = 0
    embedded = 0
    for episode in episodes.get("items", []):
        url = episode.get("audio_url")
        if not url:
            continue
        source = SITE / url
        if args.no_audio or not source.exists():
            episode["audio_url"] = None
            continue
        size = source.stat().st_size
        if total + size > MAX_TOTAL_AUDIO_BYTES:
            episode["audio_url"] = None
            continue
        episode["audio_url"] = data_uri(source)
        total += size
        embedded += 1

    status = dict(status or {})
    status["frozen"] = True
    status["demo"] = bool(args.demo)
    status["built_at"] = status.get("built_at") or datetime.now(UTC).isoformat()

    payload = {
        "stories": stories,
        "categories": categories,
        "episodes": episodes,
        "status": status,
    }

    # --- swap the loader ---------------------------------------------------
    # Everything else in the page is untouched; only the four fetches become
    # four lookups in a constant that is already in memory.
    inline = (
        "const BUNDLED = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
        "// This build carries its news inside it. `load` therefore resolves\n"
        "// immediately and can never fail — but it also can never bring\n"
        "// anything new, which is why the banner below says so.\n"
        "async function getJSON(path) {\n"
        "  const key = String(path).replace(/^api\\//, \"\").replace(/\\.json$/, \"\");\n"
        "  if (key in BUNDLED) return BUNDLED[key];\n"
        "  throw new Error(`${path}: not bundled`);\n"
        "}\n"
    )

    pattern = re.compile(
        r"async function getJSON\(path\) \{.*?\n\}\n", re.DOTALL
    )
    if not pattern.search(html):
        raise SystemExit("could not find getJSON() in site/index.html")
    # A lambda, not the string: re.sub treats backslashes in a replacement as
    # escapes, and JSON is full of them — "\n" inside a narration script would
    # become a real newline and break the literal.
    html = pattern.sub(lambda _: inline, html, count=1)

    # No service worker: there is nothing to cache that is not already here,
    # and registering one from a file:// page throws.
    html = re.sub(
        r'\n?\s*navigator\.serviceWorker\.register\("sw\.js"\)\.catch\(\(\) => \{\}\);',
        "\n    /* single-file build: nothing to cache */",
        html,
    )

    built = datetime.fromisoformat(status["built_at"]).astimezone(UTC)
    stamp = built.strftime("%-d %B %Y, %H:%M UTC")

    # The standing notice. `renderBanner` owns the transient one; this sits in
    # the About tab's place at the top of the document so it cannot be missed.
    if args.demo:
        notice = (
            '<div id="frozen-notice" role="note">'
            "<b>Demonstration copy.</b> Every story, outlet and place named "
            "here is invented — this is the real app running on its test "
            "fixtures, so that nothing false is attached to a real publisher. "
            "Run it from your own GitHub repository and it fills with real "
            "news from real feeds."
            "</div>"
        )
    else:
        notice = (
            '<div id="frozen-notice" role="note">'
            f"<b>This is a fixed copy</b>, built {stamp}. It does not refresh. "
            "The stories, sources and audio in it are exactly what the pipeline "
            "produced at that moment."
            "</div>"
        )
    # Above the section rail, not between the rail and the cards: a standing
    # notice about what the whole page is belongs with the page's chrome, not
    # wedged into the reading column.
    anchor = '<nav class="rail hidden" id="rail"'
    if anchor not in html:
        raise SystemExit("could not find the section rail in site/index.html")
    html = html.replace(anchor, notice + "\n  " + anchor, 1)

    css = """
#frozen-notice {
  font-family: var(--sans); font-size: 12.5px; line-height: 1.45;
  color: var(--muted); background: var(--surface);
  border-bottom: 1px solid var(--rule);
  padding: 9px 18px; text-align: center;
}
#frozen-notice b { color: var(--ink); font-weight: 600; }
"""
    html = html.replace("</style>", css + "</style>", 1)

    if args.artifact:
        html = to_artifact(html)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    size = out.stat().st_size
    print(f"{out}  {size / 1024 / 1024:.1f} MB")
    print(f"  stories   {len(stories.get('items', []))}")
    print(f"  episodes  {len(episodes.get('items', []))} "
          f"({embedded} with audio, {total / 1024 / 1024:.1f} MB)")
    print(f"  built     {stamp}")
    if "fetch(" in re.sub(r"async function getJSON.*?\n\}\n", "", html, flags=re.DOTALL):
        print("  note: the page still contains a fetch() call")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
