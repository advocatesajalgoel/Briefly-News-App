import XCTest
@testable import Briefly

final class BundledRepositoryTests: XCTestCase {
    private var repository: BundledNewsRepository!

    override func setUp() {
        super.setUp()
        repository = TestResources.repository()
    }

    func testServesCategories() async throws {
        let categories = try await repository.categories()
        XCTAssertFalse(categories.isEmpty)
    }

    func testStoriesAreRankedHighestFirst() async throws {
        let page = try await repository.stories(category: nil, cursor: nil, limit: 50)
        let scores = page.items.map(\.rankScore)
        XCTAssertEqual(scores, scores.sorted(by: >))
    }

    func testCategoryFilterApplies() async throws {
        let all = try await repository.stories(category: nil, cursor: nil, limit: 50)
        guard let slug = all.items.compactMap(\.categorySlug).first else {
            throw XCTSkip("snapshot has no categorised stories")
        }
        let filtered = try await repository.stories(category: slug, cursor: nil, limit: 50)
        XCTAssertFalse(filtered.items.isEmpty)
        XCTAssertTrue(filtered.items.allSatisfy { $0.categorySlug == slug })
    }

    func testPaginationDoesNotRepeatOrSkip() async throws {
        let first = try await repository.stories(category: nil, cursor: nil, limit: 2)
        XCTAssertEqual(first.items.count, 2)
        let cursor = try XCTUnwrap(first.nextCursor)
        let second = try await repository.stories(category: nil, cursor: cursor, limit: 2)
        let firstIDs = Set(first.items.map(\.id))
        let secondIDs = Set(second.items.map(\.id))
        XCTAssertTrue(firstIDs.isDisjoint(with: secondIDs))
    }

    func testMissingStoryThrowsNotFound() async {
        do {
            _ = try await repository.story(id: UUID())
            XCTFail("expected notFound")
        } catch let error as APIError {
            XCTAssertEqual(error, .notFound)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    func testLatestDailyEpisodeIsAvailable() async throws {
        let episode = try await repository.latestEpisode(kind: .daily)
        XCTAssertEqual(episode.episodeKind, .daily)
        XCTAssertGreaterThan(episode.durationSeconds, 0)
    }

    func testReportsItselfAsSampleData() {
        XCTAssertTrue(repository.isSample, "the reader must be told when data is sample data")
    }
}

/// A repository that always fails, so the fallback path can be exercised.
private struct FailingRepository: NewsRepository {
    let error: APIError
    var isSample: Bool { false }

    func categories() async throws -> [NewsCategory] { throw error }
    func stories(category: String?, cursor: String?, limit: Int) async throws -> StoryPage { throw error }
    func story(id: UUID) async throws -> Story { throw error }
    func stories(ids: [UUID]) async throws -> [Story] { throw error }
    func episodes(kind: EpisodeKind?) async throws -> [PodcastEpisode] { throw error }
    func latestEpisode(kind: EpisodeKind) async throws -> PodcastEpisode { throw error }
}

final class FallbackRepositoryTests: XCTestCase {
    private var bundled: BundledNewsRepository!

    override func setUp() {
        super.setUp()
        bundled = TestResources.repository()
    }

    func testFallsBackWhenTheServerIsUnreachable() async throws {
        let notified = expectation(description: "fallback reported")
        let repository = FallbackNewsRepository(
            remote: FailingRepository(error: .offline),
            bundled: bundled,
            onFallback: { _ in notified.fulfill() }
        )
        let page = try await repository.stories(category: nil, cursor: nil, limit: 5)
        XCTAssertFalse(page.items.isEmpty)
        await fulfillment(of: [notified], timeout: 1)
    }

    func testDoesNotMaskAnAuthenticationFailure() async {
        let repository = FallbackNewsRepository(
            remote: FailingRepository(error: .unauthorized), bundled: bundled
        )
        do {
            _ = try await repository.stories(category: nil, cursor: nil, limit: 5)
            XCTFail("a rejected key must surface, not be papered over with sample data")
        } catch let error as APIError {
            XCTAssertEqual(error, .unauthorized)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    func testWithoutARemoteItIsHonestlyMarkedAsSample() {
        let repository = FallbackNewsRepository(remote: nil, bundled: bundled)
        XCTAssertTrue(repository.isSample)
    }
}

final class APIConfigurationTests: XCTestCase {
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        defaults = UserDefaults(suiteName: "briefly.tests.\(UUID().uuidString)")
    }

    func testOfflineByDefault() {
        let configuration = APIConfiguration.load(defaults: defaults, bundle: TestResources.bundle)
        XCTAssertFalse(configuration.isConfigured)
    }

    func testRoundTripsThroughDefaults() {
        let configuration = APIConfiguration(
            baseURL: URL(string: "https://briefly.example.com"), clientKey: "abc"
        )
        configuration.save(to: defaults)
        let loaded = APIConfiguration.load(defaults: defaults, bundle: TestResources.bundle)
        XCTAssertEqual(loaded.baseURL?.absoluteString, "https://briefly.example.com")
        XCTAssertEqual(loaded.clientKey, "abc")
    }

    func testClearingRemovesTheServer() {
        APIConfiguration(baseURL: URL(string: "https://x.example"), clientKey: nil).save(to: defaults)
        APIConfiguration.offline.save(to: defaults)
        XCTAssertFalse(
            APIConfiguration.load(defaults: defaults, bundle: TestResources.bundle).isConfigured
        )
    }
}
