import XCTest
@testable import Briefly

@MainActor
final class BookmarkStoreTests: XCTestCase {
    private var directory: URL!
    private var store: BookmarkStore!

    override func setUp() async throws {
        try await super.setUp()
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        store = BookmarkStore(directory: directory)
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: directory)
        try await super.tearDown()
    }

    private func makeStory(headline: String = "A story") throws -> Story {
        let json = """
        {
          "id": "\(UUID().uuidString.lowercased())",
          "slug": "a-story",
          "headline": "\(headline)",
          "summary": "A short summary of the story, well under the limit.",
          "summary_word_count": 10,
          "dek": null,
          "category_slug": "india",
          "category_name": "India",
          "published_at": "2026-09-05T08:05:00Z",
          "first_reported_at": null,
          "last_reported_at": null,
          "source_count": 1,
          "independent_source_count": 1,
          "has_official_source": false,
          "has_disputed_claims": false,
          "confidence": "reported",
          "diversity": {"level":"low","total":1,"independent":1,"countries":1,
                        "has_official":false,"lines":[],"by_kind":{},"by_country":{},
                        "disclaimer":"Source diversity counts where reporting came from. It is not a measurement of bias."},
          "sources": [],
          "facts": [],
          "rank_score": 0.4
        }
        """
        return try JSONDecoder.briefly.decode(Story.self, from: Data(json.utf8))
    }

    func testStartsEmpty() {
        XCTAssertTrue(store.isEmpty)
    }

    func testAddAndRemove() throws {
        let story = try makeStory()
        store.add(story)
        XCTAssertTrue(store.contains(story))
        XCTAssertEqual(store.count, 1)

        store.remove(story)
        XCTAssertFalse(store.contains(story))
        XCTAssertTrue(store.isEmpty)
    }

    func testAddingTwiceDoesNotDuplicate() throws {
        let story = try makeStory()
        store.add(story)
        store.add(story)
        XCTAssertEqual(store.count, 1)
    }

    func testToggleReportsTheNewState() throws {
        let story = try makeStory()
        XCTAssertTrue(store.toggle(story))
        XCTAssertFalse(store.toggle(story))
    }

    func testMostRecentlySavedComesFirst() throws {
        let first = try makeStory(headline: "First")
        let second = try makeStory(headline: "Second")
        store.add(first)
        store.add(second)
        XCTAssertEqual(store.stories.first?.headline, "Second")
    }

    func testRefreshReplacesInPlaceWithoutLosingUnknownStories() throws {
        let kept = try makeStory(headline: "Kept")
        let stale = try makeStory(headline: "Stale")
        store.add(kept)
        store.add(stale)

        let updatedJSON = try JSONEncoder.briefly.encode(kept)
        var updated = try JSONDecoder.briefly.decode(Story.self, from: updatedJSON)
        updated = try makeStory(headline: "Updated")
        store.refresh(with: [updated])

        XCTAssertEqual(store.count, 2, "an unmatched update must not delete anything")
    }

    func testSurvivesARestart() async throws {
        let story = try makeStory(headline: "Persisted")
        store.add(story)
        // Writes are asynchronous by design; give the detached task a moment.
        try await Task.sleep(nanoseconds: 300_000_000)

        let reopened = BookmarkStore(directory: directory)
        XCTAssertEqual(reopened.count, 1)
        XCTAssertEqual(reopened.stories.first?.headline, "Persisted")
    }

    func testACorruptFileIsDiscardedRatherThanCrashing() throws {
        let corrupt = directory.appendingPathComponent("briefly-bookmarks.json")
        try Data("not json at all".utf8).write(to: corrupt)
        let reopened = BookmarkStore(directory: directory)
        XCTAssertTrue(reopened.isEmpty)
    }

    func testRemoveAll() throws {
        store.add(try makeStory())
        store.add(try makeStory())
        store.removeAll()
        XCTAssertTrue(store.isEmpty)
    }
}
