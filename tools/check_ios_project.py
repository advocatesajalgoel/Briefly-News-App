#!/usr/bin/env python3
"""Static consistency checks for the iOS project.

Not a compiler. These checks catch the class of mistake that is easy to make
when writing Swift without one to hand — unbalanced delimiters, a type used but
never declared, two declarations of the same name, a resource the code loads
that is not in the bundle, an object id referenced but not defined in the Xcode
project — and they run anywhere, which the Swift toolchain does not.

    python3 tools/check_ios_project.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IOS = ROOT / "ios"
APP = IOS / "Briefly"
TESTS = IOS / "BrieflyTests"
CORE_TESTS = IOS / "BrieflyCoreTests"
PACKAGE = IOS / "Package.swift"
PBXPROJ = IOS / "Briefly.xcodeproj" / "project.pbxproj"

failures: list[str] = []
warnings: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def warn(message: str) -> None:
    warnings.append(message)


# ---------------------------------------------------------------------------
# Swift source scanning
# ---------------------------------------------------------------------------

STRING_RE = re.compile(r'"""(?:.|\n)*?"""|#"(?:.|\n)*?"#|"(?:\\.|[^"\\\n])*"')
LINE_COMMENT_RE = re.compile(r"//[^\n]*")
BLOCK_COMMENT_RE = re.compile(r"/\*(?:.|\n)*?\*/")


def strip_noise(source: str) -> str:
    """Remove comments and string literals so delimiters inside them don't count."""
    source = BLOCK_COMMENT_RE.sub(" ", source)
    source = STRING_RE.sub('""', source)
    source = LINE_COMMENT_RE.sub(" ", source)
    return source


# Only column-zero declarations: a nested `CodingKeys` or a per-view `Phase` is
# scoped to its parent and cannot collide with another one.
DECL_RE = re.compile(
    r"^(?:public\s+|internal\s+|private\s+|fileprivate\s+|final\s+|@\w+(?:\([^)]*\))?\s+)*"
    r"(struct|class|enum|protocol|actor)\s+([A-Za-z_]\w*)",
    re.MULTILINE,
)
EXTENSION_RE = re.compile(r"^\s*extension\s+([A-Za-z_]\w*)", re.MULTILINE)


def swift_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend(sorted(root.rglob("*.swift")))
    return files


def check_delimiters(path: Path, source: str) -> None:
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    line = 1
    for char in source:
        if char == "\n":
            line += 1
        elif char in "([{":
            stack.append((char, line))
        elif char in ")]}":
            if not stack:
                fail(f"{path.relative_to(ROOT)}:{line} unmatched '{char}'")
                return
            opener, opened_at = stack.pop()
            if opener != pairs[char]:
                fail(
                    f"{path.relative_to(ROOT)}:{line} '{char}' closes '{opener}' "
                    f"opened on line {opened_at}"
                )
                return
    if stack:
        opener, opened_at = stack[-1]
        fail(f"{path.relative_to(ROOT)}: '{opener}' opened on line {opened_at} is never closed")


def main() -> int:
    app_files = swift_files(APP)
    test_files = swift_files(TESTS) + swift_files(CORE_TESTS)
    if not app_files:
        fail("no Swift sources found under ios/Briefly")
        return report()

    declarations: dict[str, list[str]] = defaultdict(list)
    cleaned: dict[Path, str] = {}

    for path in app_files + test_files:
        raw = path.read_text(encoding="utf-8")
        source = strip_noise(raw)
        cleaned[path] = source
        check_delimiters(path, source)
        for _, name in DECL_RE.findall(source):
            declarations[name].append(str(path.relative_to(ROOT)))

    # 1. Duplicate top-level type names in the same module. Two declarations in
    #    one file are fine when they sit in opposite branches of a `#if`.
    conditional_files = {
        str(path.relative_to(ROOT))
        for path, source in cleaned.items()
        if "#else" in path.read_text(encoding="utf-8")
    }
    for name, paths in sorted(declarations.items()):
        app_paths = [p for p in paths if "/BrieflyTests/" not in p]
        distinct = set(app_paths)
        if len(distinct) > 1:
            fail(f"type '{name}' is declared in {len(distinct)} files: {', '.join(sorted(distinct))}")
        elif len(app_paths) > 1 and app_paths[0] not in conditional_files:
            fail(f"type '{name}' is declared {len(app_paths)} times in {app_paths[0]}")

    # 2. Types referenced by our own code but never declared.
    #    Only project-prefixed names are checked, so SDK types are not flagged.
    project_names = set(declarations)
    project_prefixes = ("Briefly", "Story", "News", "Podcast", "Episode", "Source",
                        "Extracted", "Feed", "Saved", "Sources", "Audio", "App",
                        "Fallback", "Bundled", "Remote", "API", "Word", "Relative",
                        "Time", "Confidence", "Diversity", "Mini", "Player",
                        "Categories", "Category", "Settings", "About", "Editorial",
                        "Empty", "Error", "Loading", "Sample", "Share", "Flow",
                        "Device", "Bookmark", "Haptics", "Appearance", "Test")
    referenced = defaultdict(set)
    ident_re = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\b")
    for path, source in cleaned.items():
        for name in ident_re.findall(source):
            if name.startswith(project_prefixes):
                referenced[name].add(str(path.relative_to(ROOT)))

    known_non_types = {
        "AppStorage", "AppKit", "AppDelegate", "AppearanceOption", "Storyboard",
        "TimeInterval", "TimeZone", "APIError", "AVAudioSession", "AVPlayer",
        "AVPlayerItem", "AVAudioSessionInterruptionTypeKey",
        # Module names, not types.
        "BrieflyCore", "BrieflyCoreTests",
    }
    for name, users in sorted(referenced.items()):
        if name in project_names or name in known_non_types:
            continue
        # Enum members and SDK symbols show up here too; only flag names that
        # look like our own composed types.
        if re.match(r"^(Briefly|Story|Feed|Podcast|Episode|Saved|Sources)[A-Z]", name):
            fail(f"'{name}' is used in {', '.join(sorted(users))} but never declared")

    # 3. Environment objects must be injected somewhere.
    env_re = re.compile(r"@Environment\((\w+)\.self\)")
    injected = set()
    for source in cleaned.values():
        injected |= set(re.findall(r"\.environment\((?:appEnvironment(?:\.(\w+))?)\)", source))
    required = set()
    for source in cleaned.values():
        required |= set(env_re.findall(source))
    entry = (APP / "App" / "BrieflyApp.swift").read_text(encoding="utf-8")
    for name in sorted(required):
        token = {
            "AppEnvironment": "appEnvironment)",
            "AppSettings": "appEnvironment.settings)",
            "BookmarkStore": "appEnvironment.bookmarks)",
            "AudioPlayerController": "appEnvironment.player)",
        }.get(name)
        if token and token not in entry:
            fail(f"@Environment({name}.self) is read but never injected in BrieflyApp")

    # 4. Bundled resources the code asks for must exist.
    resources = APP / "Resources"
    for source in cleaned.values():
        for name in re.findall(r'forResource:\s*"([^"]+)"', source):
            if not (resources / f"{name}.json").exists():
                fail(f"code loads '{name}.json' but ios/Briefly/Resources/{name}.json is missing")

    # 4b. A bundled episode that names a local audio file must actually have it.
    episodes_file = resources / "mock_episodes.json"
    if episodes_file.exists():
        try:
            payload = json.loads(episodes_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"mock_episodes.json is not valid JSON: {exc}")
            payload = {"items": []}
        for episode in payload.get("items", []):
            audio = episode.get("audio_url") or ""
            if audio and "://" not in audio and not (resources / audio).exists():
                fail(
                    f"sample episode '{episode.get('slug')}' points at bundled audio "
                    f"'{audio}', which is not in ios/Briefly/Resources"
                )

    # 5. Named colours must be in the asset catalogue.
    catalogue = resources / "Assets.xcassets"
    colour_sets = {p.name.replace(".colorset", "") for p in catalogue.glob("*.colorset")}
    colours_source = (APP / "DesignSystem" / "BrieflyColors.swift").read_text(encoding="utf-8")
    for name in re.findall(r'Color\("(\w+)",\s*bundle:', colours_source):
        if name not in colour_sets:
            fail(f"colour '{name}' is referenced but has no .colorset in the asset catalogue")
    for required_asset in ("AppIcon.appiconset", "AccentColor.colorset"):
        if not (catalogue / required_asset).exists():
            fail(f"asset catalogue is missing {required_asset}")
    if not (catalogue / "AppIcon.appiconset" / "AppIcon.png").exists():
        fail("AppIcon.png is missing from the app icon set")

    # 6. Every asset catalogue Contents.json must be valid JSON.
    for contents in catalogue.rglob("Contents.json"):
        try:
            json.loads(contents.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"{contents.relative_to(ROOT)} is not valid JSON: {exc}")

    # 7. No credential may appear anywhere in the app target.
    secret_re = re.compile(
        r"(sk-[A-Za-z0-9]{16,}|api[_-]?key\s*=\s*\"[^\"]{8,}\"|Bearer\s+[A-Za-z0-9._-]{20,}"
        r"|AKIA[0-9A-Z]{16})",
        re.IGNORECASE,
    )
    for path in app_files:
        raw = path.read_text(encoding="utf-8")
        if secret_re.search(raw):
            fail(f"{path.relative_to(ROOT)} appears to contain a credential")
    plist = (resources / "Info.plist").read_text(encoding="utf-8")
    for banned in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS", "AWS_SECRET",
                   "DATABASE_URL", "ADMIN_TOKEN"):
        if banned in plist:
            fail(f"Info.plist references {banned}; no server credential belongs in the app")

    # 8. Info.plist must declare background audio and a launch screen.
    for key in ("UIBackgroundModes", "UILaunchScreen", "CFBundleShortVersionString"):
        if key not in plist:
            fail(f"Info.plist is missing {key}")
    if "<string>audio</string>" not in plist:
        fail("Info.plist does not declare the audio background mode")

    # 9. Members accessed on our own namespace types must exist.
    check_namespace_members(cleaned)

    # 10. Members accessed on our model types must exist.
    check_instance_members(cleaned)

    # 11. Every SwiftUI View must have a body.
    check_views(cleaned)

    # 12. The SwiftPM package that lets the model layer build without a Mac.
    check_swift_package()

    # 13. Xcode project integrity.
    check_pbxproj()

    # 14. Every test file should contain at least one assertion.
    for path in test_files:
        source = path.read_text(encoding="utf-8")
        asserts = any(k in source for k in ("XCTAssert", "XCTUnwrap", "XCTFail"))
        if not asserts and "final class" in source and "XCTestCase" in source:
                warn(f"{path.relative_to(ROOT)} defines tests but asserts nothing")

    return report()


# Namespaces whose members are referenced all over the UI. A typo in one of
# these is the single most likely way to break the build, and it is exactly the
# kind of thing a compiler would catch instantly and a human never will.
NAMESPACES = [
    "BrieflyColor", "BrieflySpace", "BrieflyRadius", "BrieflyMotion",
    "BrieflyFont", "TimeFormatting", "RelativeTime", "WordCount", "Haptics",
    "APIConfiguration", "TestResources",
]

MEMBER_DECL_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|static\s+|let\s+|var\s+|func\s+|case\s+)+",
)


def declared_members(source: str, type_name: str) -> set[str]:
    """Member names declared directly inside `enum/struct/class <type_name>`."""
    match = re.search(
        rf"^(?:public\s+|final\s+|@\w+\s+)*(?:enum|struct|class|actor)\s+{type_name}\b[^\n{{]*{{",
        source, re.MULTILINE,
    )
    if not match:
        return set()
    start = match.end()
    depth = 1
    index = start
    while index < len(source) and depth > 0:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
        index += 1
    body = source[start:index]

    members: set[str] = set()
    for pattern in (
        r"\b(?:static\s+)?(?:let|var)\s+([A-Za-z_]\w*)",
        r"\b(?:static\s+)?func\s+([A-Za-z_]\w*)",
        r"^\s*case\s+([A-Za-z_]\w*)",
        r"\b(?:enum|struct|class)\s+([A-Za-z_]\w*)",
    ):
        members |= set(re.findall(pattern, body, re.MULTILINE))
    return members


def check_namespace_members(cleaned: dict[Path, str]) -> None:
    all_source = "\n".join(cleaned.values())
    for namespace in NAMESPACES:
        members = declared_members(all_source, namespace)
        if not members:
            warn(f"could not locate the declaration of {namespace}")
            continue
        for path, source in cleaned.items():
            for used in set(re.findall(rf"\b{namespace}\.([A-Za-z_]\w*)", source)):
                if used in members or used in {"self", "Type", "init"}:
                    continue
                fail(f"{path.relative_to(ROOT)}: {namespace}.{used} does not exist")


# Conventional local names for our model types. Checking member access through
# them catches the other common typo class: `story.sourceCounts`, `episode.dek`.
INSTANCE_BINDINGS = {
    "story": "Story",
    "source": "StorySource",
    "fact": "ExtractedFact",
    "episode": "PodcastEpisode",
    "chapter": "EpisodeSegment",
    "segment": "EpisodeSegment",
    "category": "NewsCategory",
    "diversity": "SourceDiversity",
}

# Members every Swift value has, or that come from protocol conformances.
UNIVERSAL_MEMBERS = {
    "id", "hashValue", "description", "debugDescription", "self", "count",
    "isEmpty", "first", "last", "map", "filter", "compactMap", "sorted",
    "prefix", "suffix", "contains", "forEach", "reduce", "joined", "enumerated",
    "allSatisfy", "flatMap", "reversed", "dropFirst", "elementsEqual", "indices",
    "lowercased", "uppercased", "trimmingCharacters", "hasPrefix", "hasSuffix",
    "uuidString", "absoluteString", "rawValue", "formatted",
}


def check_instance_members(cleaned: dict[Path, str]) -> None:
    all_source = "\n".join(cleaned.values())
    member_map = {
        type_name: declared_members(all_source, type_name)
        for type_name in set(INSTANCE_BINDINGS.values())
    }
    # Computed properties declared in extensions count too.
    for type_name in member_map:
        for match in re.finditer(rf"^extension\s+{type_name}\b[^{{]*{{", all_source, re.MULTILINE):
            start = match.end()
            depth, index = 1, start
            while index < len(all_source) and depth > 0:
                if all_source[index] == "{":
                    depth += 1
                elif all_source[index] == "}":
                    depth -= 1
                index += 1
            body = all_source[start:index]
            member_map[type_name] |= set(
                re.findall(r"\b(?:static\s+)?(?:let|var|func)\s+([A-Za-z_]\w*)", body)
            )

    for path, source in cleaned.items():
        for binding, type_name in INSTANCE_BINDINGS.items():
            members = member_map.get(type_name) or set()
            if not members:
                continue
            for used in set(re.findall(rf"(?<![\w.]){binding}\.([A-Za-z_]\w*)", source)):
                if used in members or used in UNIVERSAL_MEMBERS:
                    continue
                fail(f"{path.relative_to(ROOT)}: {type_name}.{used} does not exist "
                     f"(via `{binding}.`)")


def check_views(cleaned: dict[Path, str]) -> None:
    for path, source in cleaned.items():
        for match in re.finditer(
            r"^(?:public\s+)?struct\s+([A-Za-z_]\w*)\s*:\s*([^{\n]+)\{", source, re.MULTILINE
        ):
            name, conformances = match.group(1), match.group(2)
            if "View" not in [c.strip() for c in conformances.split(",")]:
                continue
            start = match.end()
            depth = 1
            index = start
            while index < len(source) and depth > 0:
                if source[index] == "{":
                    depth += 1
                elif source[index] == "}":
                    depth -= 1
                index += 1
            body = source[start:index]
            if not re.search(r"\bvar\s+body\s*:", body):
                fail(f"{path.relative_to(ROOT)}: View '{name}' has no body property")


def check_swift_package() -> None:
    """The Linux-buildable core must stay Foundation-only.

    The whole value of `ios/Package.swift` is that it compiles on a free CI
    runner with no Mac. One `import SwiftUI` in the model layer silently takes
    that away, so it is checked rather than hoped for.
    """
    if not PACKAGE.exists():
        warn("ios/Package.swift is missing; the model layer cannot be built without a Mac")
        return
    text = PACKAGE.read_text(encoding="utf-8")
    target_path = re.search(r'path:\s*"([^"]+)"', text)
    if not target_path:
        fail("Package.swift declares no target path")
        return
    target_dir = IOS / target_path.group(1)
    if not target_dir.is_dir():
        fail(f"Package.swift points at {target_path.group(1)}, which does not exist")
        return

    forbidden = {"SwiftUI", "UIKit", "AppKit", "AVFoundation", "MediaPlayer",
                 "Observation", "Combine", "os", "Security", "XCTest"}
    for path in sorted(target_dir.glob("*.swift")):
        for module in re.findall(r"^import\s+(\w+)", path.read_text(encoding="utf-8"),
                                 re.MULTILINE):
            if module in forbidden:
                fail(
                    f"{path.relative_to(ROOT)} imports {module}; the BrieflyCore target "
                    f"must stay Foundation-only so it builds on Linux"
                )

    if not (CORE_TESTS).is_dir():
        fail("ios/BrieflyCoreTests is missing; `swift test` would have nothing to run")


def check_pbxproj() -> None:
    if not PBXPROJ.exists():
        fail("Briefly.xcodeproj/project.pbxproj is missing")
        return
    text = PBXPROJ.read_text(encoding="utf-8")

    # Balanced braces and parens.
    if text.count("{") != text.count("}"):
        fail(f"project.pbxproj braces unbalanced ({text.count('{')} open, {text.count('}')} close)")
    if text.count("(") != text.count(")"):
        fail("project.pbxproj parentheses unbalanced")

    defined = set(re.findall(r"^\t\t([0-9A-F]{24})\b", text, re.MULTILINE))
    referenced = set(re.findall(r"\b([0-9A-F]{24})\b", text))
    missing = referenced - defined
    if missing:
        fail(f"project.pbxproj references undefined objects: {', '.join(sorted(missing))}")
    unused = defined - (referenced - defined)
    del unused  # every defined object is also referenced by its own definition

    for required in ("PBXProject", "PBXNativeTarget", "XCConfigurationList",
                     "PBXFileSystemSynchronizedRootGroup", "rootObject"):
        if required not in text:
            fail(f"project.pbxproj is missing a {required} section")

    if "objectVersion = 77" not in text:
        warn("project.pbxproj is not using objectVersion 77 (Xcode 16 synchronised groups)")

    for setting in ("INFOPLIST_FILE", "PRODUCT_BUNDLE_IDENTIFIER",
                    "IPHONEOS_DEPLOYMENT_TARGET", "ASSETCATALOG_COMPILER_APPICON_NAME"):
        if setting not in text:
            fail(f"project.pbxproj is missing the {setting} build setting")

    scheme = IOS / "Briefly.xcodeproj" / "xcshareddata" / "xcschemes" / "Briefly.xcscheme"
    if not scheme.exists():
        fail("shared scheme Briefly.xcscheme is missing (xcodebuild -scheme Briefly would fail)")
    else:
        scheme_text = scheme.read_text(encoding="utf-8")
        for blueprint in re.findall(r'BlueprintIdentifier = "([0-9A-F]{24})"', scheme_text):
            if blueprint not in defined:
                fail(f"scheme points at unknown target {blueprint}")


def report() -> int:
    print(f"iOS project check — {len(failures)} failure(s), {len(warnings)} warning(s)\n")
    for warning in warnings:
        print(f"  WARN   {warning}")
    for failure in failures:
        print(f"  FAIL   {failure}")
    if not failures:
        print("  All static checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
