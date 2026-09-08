import XCTest
@testable import BrieflyCore

/// Tests that run anywhere Swift runs — including a free Linux CI runner.
///
/// These cover the layer where a silent bug does the most damage: the Codable
/// contract with the backend. The snapshot in `Briefly/Resources` is generated
/// from the server's own serialisers, so decoding it here proves the app and the
/// API still agree. If someone renames a field on the server, this goes red
/// before anyone opens Xcode.
final class BrieflyCoreTests: XCTestCase {

    // MARK: - Locating the snapshot

    /// The repository's `ios/Briefly/Resources` directory, found relative to this
    /// source file. SwiftPM cannot bundle resources from outside the test
    /// target's own directory, and copying the JSON would let the copy drift
    /// from what the app actually ships — so the real files are read in place.
    private static let resources: URL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // BrieflyCoreTests
        .deletingLastPathComponent()   // ios
        .appendingPathComponent("Briefly/Resources")

    private func data(_ name: String) throws -> Data {
        let url = Self.resources.appendingPathComponent("\(name).json")
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw XCTSkip("\(name).json not found at \(url.path)")
        }
        return try Data(contentsOf: url)
    }

    // MARK: - The API contract

    func testDecodesStories() throws {
        let page = try JSONDecoder.briefly.decode(StoryPage.self, from: try data("mock_stories"))
        XCTAssertFalse(page.items.isEmpty)

        for story in page.items {
            XCTAssertFalse(story.headline.isEmpty)
            XCTAssertFalse(story.summary.isEmpty)
            XCTAssertNotNil(story.publishedAt)
            XCTAssertFalse(story.sources.isEmpty, "\(story.headline) has no sources")
            XCTAssertEqual(story.sources.count, story.sourceCount)
        }
    }

    func testEverySummaryObeysTheThirtyWordRule() throws {
        let page = try JSONDecoder.briefly.decode(StoryPage.self, from: try data("mock_stories"))
        for story in page.items {
            XCTAssertLessThanOrEqual(story.summaryWordCount, WordCount.cardLimit)
            XCTAssertLessThanOrEqual(
                WordCount.count(story.summary), WordCount.cardLimit,
                "\(story.headline): \(WordCount.count(story.summary)) words"
            )
        }
    }

    func testEverySourceIsUsable() throws {
        let page = try JSONDecoder.briefly.decode(StoryPage.self, from: try data("mock_stories"))
        for story in page.items {
            for source in story.sources {
                XCTAssertFalse(source.sourceName.isEmpty)
                XCTAssertFalse(source.originalHeadline.isEmpty)
                XCTAssertNotNil(source.originalURL, "\(source.sourceName) has no link")
            }
        }
    }

    func testDiversityNeverLosesItsDisclaimer() throws {
        let page = try JSONDecoder.briefly.decode(StoryPage.self, from: try data("mock_stories"))
        for story in page.items {
            XCTAssertTrue(
                story.diversity.disclaimer.lowercased().contains("not a measurement of bias"),
                "the indicator must never be presented as a bias score"
            )
            XCTAssertTrue(["low", "medium", "high"].contains(story.diversity.level))
        }
    }

    func testDecodesCategories() throws {
        let categories = try JSONDecoder.briefly.decode(
            [NewsCategory].self, from: try data("mock_categories")
        )
        let slugs = categories.map(\.slug)
        for expected in ["for-you", "india", "world", "business", "technology",
                         "science", "sports", "entertainment"] {
            XCTAssertTrue(slugs.contains(expected), "missing section \(expected)")
        }
    }

    func testDecodesEpisodesWithOrderedChapters() throws {
        let page = try JSONDecoder.briefly.decode(EpisodePage.self, from: try data("mock_episodes"))
        XCTAssertFalse(page.items.isEmpty)

        for episode in page.items {
            XCTAssertFalse(episode.title.isEmpty)
            XCTAssertGreaterThan(episode.durationSeconds, 0)
            let offsets = episode.segments.map(\.startOffsetSeconds)
            XCTAssertEqual(offsets, offsets.sorted(), "chapter offsets must increase")
            for chapter in episode.chapters {
                XCTAssertNotNil(chapter.storyID, "a story chapter must map back to a story")
            }
        }
        XCTAssertTrue(page.items.contains { $0.episodeKind == .daily })
    }

    func testBundledEpisodeAudioIsPresentOnDisk() throws {
        // Read the raw JSON rather than the decoded model: the snapshot stores a
        // bare filename, and the app turns that into a bundle URL at runtime.
        // What matters here is that the file it names is actually shipped.
        let raw = try JSONSerialization.jsonObject(with: try data("mock_episodes"))
        let root = try XCTUnwrap(raw as? [String: Any])
        let items = try XCTUnwrap(root["items"] as? [[String: Any]])
        XCTAssertFalse(items.isEmpty)

        for item in items {
            guard let audio = item["audio_url"] as? String,
                  !audio.isEmpty, !audio.contains("://") else { continue }
            let file = Self.resources.appendingPathComponent(audio)
            XCTAssertTrue(
                FileManager.default.fileExists(atPath: file.path),
                "\(audio) is referenced by the snapshot but is not in Resources"
            )
        }
    }

    // MARK: - Date handling

    func testDateStrategyAcceptsBothPrecisions() throws {
        struct Probe: Decodable { let at: Date }
        XCTAssertNoThrow(try JSONDecoder.briefly.decode(
            Probe.self, from: Data(#"{"at":"2026-09-06T06:22:55.886238Z"}"#.utf8)
        ))
        XCTAssertNoThrow(try JSONDecoder.briefly.decode(
            Probe.self, from: Data(#"{"at":"2026-09-05T08:05:00Z"}"#.utf8)
        ))
        XCTAssertThrowsError(try JSONDecoder.briefly.decode(
            Probe.self, from: Data(#"{"at":"not a date"}"#.utf8)
        ))
    }

    func testEncodingRoundTrip() throws {
        let page = try JSONDecoder.briefly.decode(StoryPage.self, from: try data("mock_stories"))
        let original = try XCTUnwrap(page.items.first)
        let encoded = try JSONEncoder.briefly.encode(original)
        let restored = try JSONDecoder.briefly.decode(Story.self, from: encoded)
        XCTAssertEqual(restored.id, original.id)
        XCTAssertEqual(restored.headline, original.headline)
        XCTAssertEqual(restored.sources.count, original.sources.count)
        XCTAssertEqual(restored.summaryWordCount, original.summaryWordCount)
    }

    // MARK: - Pure logic

    func testWordCountMatchesTheBackendsRule() {
        XCTAssertEqual(WordCount.count(""), 0)
        XCTAssertEqual(WordCount.count("One"), 1)
        XCTAssertEqual(WordCount.count("Two words"), 2)
        XCTAssertEqual(WordCount.count("don't count that twice"), 4)
        XCTAssertEqual(WordCount.count("U.S. officials said"), 3)
        XCTAssertEqual(WordCount.count("!!! ???"), 0)
        XCTAssertTrue(WordCount.isWithinCardLimit(String(repeating: "word ", count: 30)))
        XCTAssertFalse(WordCount.isWithinCardLimit(String(repeating: "word ", count: 31)))
    }

    func testDurationFormatting() {
        XCTAssertEqual(TimeFormatting.formatted(seconds: 0), "0:00")
        XCTAssertEqual(TimeFormatting.formatted(seconds: 9), "0:09")
        XCTAssertEqual(TimeFormatting.formatted(seconds: 65), "1:05")
        XCTAssertEqual(TimeFormatting.formatted(seconds: 3661), "1:01:01")
        XCTAssertEqual(TimeFormatting.formatted(seconds: -5), "0:00")
        XCTAssertEqual(TimeFormatting.approximate(seconds: 20), "Under a minute")
        XCTAssertEqual(TimeFormatting.approximate(seconds: 480), "About 8 min")
    }

    func testRelativeTime() {
        let now = Date()
        XCTAssertEqual(RelativeTime.string(for: now.addingTimeInterval(-30), now: now), "Just now")
        XCTAssertFalse(RelativeTime.string(for: now.addingTimeInterval(-3600), now: now).isEmpty)
        XCTAssertEqual(RelativeTime.string(for: nil), "")
        XCTAssertEqual(RelativeTime.compact(for: now.addingTimeInterval(-120), now: now), "2m")
        XCTAssertEqual(RelativeTime.compact(for: now.addingTimeInterval(-7200), now: now), "2h")
    }

    func testConfidenceLevels() {
        XCTAssertEqual(ConfidenceLevel(rawValue: "confirmed"), .confirmed)
        XCTAssertEqual(ConfidenceLevel(rawValue: "nonsense"), nil)
        for level in [ConfidenceLevel.confirmed, .disputed, .reported] {
            XCTAssertFalse(level.label.isEmpty)
            XCTAssertFalse(level.explanation.isEmpty)
        }
    }

    func testEpisodeKinds() {
        XCTAssertEqual(EpisodeKind(rawValue: "deep_dive"), .deepDive)
        XCTAssertEqual(EpisodeKind.daily.title, "Briefly Daily")
        for kind in EpisodeKind.allCases {
            XCTAssertFalse(kind.blurb.isEmpty)
        }
    }
}
