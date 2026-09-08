import XCTest
@testable import Briefly

/// The bundled snapshot is generated from the backend's own serialisers, so
/// decoding it here is a real contract test between the app and the API: if the
/// server changes a field name, these fail rather than the app showing a blank
/// screen on someone's phone.
final class ModelDecodingTests: XCTestCase {
    private func data(_ resource: String) throws -> Data {
        try TestResources.data(resource)
    }

    func testDecodesBundledStories() throws {
        let page = try JSONDecoder.briefly.decode(StoryPage.self, from: try data("mock_stories"))
        XCTAssertFalse(page.items.isEmpty, "the snapshot should contain stories")

        let story = try XCTUnwrap(page.items.first)
        XCTAssertFalse(story.headline.isEmpty)
        XCTAssertFalse(story.summary.isEmpty)
        XCTAssertFalse(story.sources.isEmpty)
        XCTAssertNotNil(story.publishedAt)
    }

    func testEverySummaryRespectsTheThirtyWordRule() throws {
        let page = try JSONDecoder.briefly.decode(StoryPage.self, from: try data("mock_stories"))
        for story in page.items {
            XCTAssertLessThanOrEqual(
                story.summaryWordCount, WordCount.cardLimit,
                "\(story.headline) reports \(story.summaryWordCount) words"
            )
            XCTAssertLessThanOrEqual(
                WordCount.count(story.summary), WordCount.cardLimit,
                "\(story.headline) actually contains \(WordCount.count(story.summary)) words"
            )
        }
    }

    func testEverySourceHasANameHeadlineAndLink() throws {
        let page = try JSONDecoder.briefly.decode(StoryPage.self, from: try data("mock_stories"))
        for story in page.items {
            XCTAssertEqual(story.sources.count, story.sourceCount,
                           "source list and count disagree for \(story.headline)")
            for source in story.sources {
                XCTAssertFalse(source.sourceName.isEmpty)
                XCTAssertFalse(source.originalHeadline.isEmpty)
                XCTAssertNotNil(source.originalURL, "\(source.sourceName) has no link")
            }
        }
    }

    func testDiversityAlwaysCarriesItsDisclaimer() throws {
        let page = try JSONDecoder.briefly.decode(StoryPage.self, from: try data("mock_stories"))
        for story in page.items {
            XCTAssertTrue(
                story.diversity.disclaimer.lowercased().contains("not a measurement of bias"),
                "the diversity indicator must never be presented as a bias score"
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
        XCTAssertTrue(try XCTUnwrap(categories.first { $0.slug == "for-you" }).isSynthetic)
    }

    func testDecodesEpisodes() throws {
        let page = try JSONDecoder.briefly.decode(EpisodePage.self, from: try data("mock_episodes"))
        XCTAssertFalse(page.items.isEmpty)
        for episode in page.items {
            XCTAssertFalse(episode.title.isEmpty)
            XCTAssertGreaterThan(episode.durationSeconds, 0)
            XCTAssertFalse(episode.segments.isEmpty)
        }
        XCTAssertTrue(page.items.contains { $0.episodeKind == .daily })
    }

    func testEpisodeChaptersAreOrderedAndLinkedToStories() throws {
        let page = try JSONDecoder.briefly.decode(EpisodePage.self, from: try data("mock_episodes"))
        let daily = try XCTUnwrap(page.items.first { $0.episodeKind == .daily })
        let offsets = daily.segments.map(\.startOffsetSeconds)
        XCTAssertEqual(offsets, offsets.sorted(), "chapter offsets must increase")
        XCTAssertFalse(daily.chapters.isEmpty)
        for chapter in daily.chapters {
            XCTAssertNotNil(chapter.storyID, "every story chapter maps back to a story")
        }
    }

    func testDateStrategyAcceptsBothPrecisions() throws {
        struct Probe: Decodable { let at: Date }
        let withFraction = #"{"at":"2026-09-06T06:22:55.886238Z"}"#
        let withoutFraction = #"{"at":"2026-09-05T08:05:00Z"}"#
        XCTAssertNoThrow(try JSONDecoder.briefly.decode(Probe.self, from: Data(withFraction.utf8)))
        XCTAssertNoThrow(try JSONDecoder.briefly.decode(Probe.self, from: Data(withoutFraction.utf8)))
    }

    func testBundledEpisodesShipTheirAudio() throws {
        let page = try JSONDecoder.briefly.decode(EpisodePage.self, from: try data("mock_episodes"))
        for episode in page.items {
            // The snapshot points at a bare filename; the app resolves it against
            // its own bundle so the podcast tab plays with no backend at all.
            XCTAssertNotNil(
                episode.audioURL,
                "\(episode.slug) has no playable audio — is sample-*.mp3 in the bundle?"
            )
            XCTAssertTrue(episode.isPlayable)
        }
    }

    func testAudioURLResolution() {
        XCTAssertEqual(
            PodcastEpisode.resolveAudioURL("https://example.com/a.mp3")?.absoluteString,
            "https://example.com/a.mp3",
            "an absolute URL passes straight through"
        )
        XCTAssertNil(PodcastEpisode.resolveAudioURL(nil))
        XCTAssertNil(PodcastEpisode.resolveAudioURL(""))
        XCTAssertNotNil(
            PodcastEpisode.resolveAudioURL("sample-daily.mp3", bundle: TestResources.bundle),
            "a bare filename resolves against the bundle"
        )
        XCTAssertNil(
            PodcastEpisode.resolveAudioURL("not-in-the-bundle.mp3", bundle: TestResources.bundle)
        )
    }

    func testAMalformedSourceURLDoesNotLoseTheStory() throws {
        let json = """
        {"source_name":"Outlet","source_kind":"national","original_headline":"H",
         "original_url":"", "published_at":null,"is_primary_source":false}
        """
        let source = try JSONDecoder.briefly.decode(StorySource.self, from: Data(json.utf8))
        XCTAssertEqual(source.sourceName, "Outlet")
    }
}
