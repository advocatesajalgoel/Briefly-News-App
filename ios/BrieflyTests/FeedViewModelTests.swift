import XCTest
@testable import Briefly

@MainActor
final class FeedViewModelTests: XCTestCase {
    private var repository: BundledNewsRepository!

    override func setUp() {
        super.setUp()
        repository = TestResources.repository()
    }

    func testLoadsAndSelectsTheFirstStory() async {
        let model = FeedViewModel(category: nil, repository: repository, pageSize: 3)
        await model.load()
        XCTAssertEqual(model.phase, .loaded)
        XCTAssertFalse(model.stories.isEmpty)
        XCTAssertEqual(model.currentStoryID, model.stories.first?.id)
    }

    func testNavigatesForwardAndBack() async {
        let model = FeedViewModel(category: nil, repository: repository, pageSize: 10)
        await model.load()
        guard model.stories.count > 1 else { return }

        model.goToNext()
        XCTAssertEqual(model.currentStoryID, model.stories[1].id)
        model.goToPrevious()
        XCTAssertEqual(model.currentStoryID, model.stories[0].id)
    }

    func testNavigationStopsAtTheEnds() async {
        let model = FeedViewModel(category: nil, repository: repository, pageSize: 50)
        await model.load()
        model.goToPrevious()
        XCTAssertEqual(model.currentStoryID, model.stories.first?.id)

        model.currentStoryID = model.stories.last?.id
        model.goToNext()
        XCTAssertEqual(model.currentStoryID, model.stories.last?.id)
    }

    func testLoadingMoreNeverDuplicatesAStory() async {
        let model = FeedViewModel(category: nil, repository: repository, pageSize: 2)
        await model.load()
        guard let last = model.stories.last else { return XCTFail("no stories") }
        await model.loadMoreIfNeeded(currentItem: last)

        let ids = model.stories.map(\.id)
        XCTAssertEqual(ids.count, Set(ids).count)
    }

    func testProgressText() async {
        let model = FeedViewModel(category: nil, repository: repository, pageSize: 50)
        await model.load()
        XCTAssertTrue(model.progressText.hasPrefix("1 of "))
    }

    func testSampleDataIsFlaggedToTheReader() async {
        let model = FeedViewModel(category: nil, repository: repository)
        await model.load()
        XCTAssertTrue(model.usingSampleData)
    }
}
