import Foundation
import Observation

/// Drives one vertical stack of cards.
///
/// A single instance backs a single category, so "For You" and "Business" keep
/// their own scroll positions and their own cursors — moving between sections
/// never loses the reader's place.
@MainActor
@Observable
final class FeedViewModel {
    enum Phase: Equatable {
        case idle
        case loading
        case loaded
        case failed(APIError)
    }

    private(set) var phase: Phase = .idle
    private(set) var stories: [Story] = []
    private(set) var isLoadingMore = false
    private(set) var isRefreshing = false
    private(set) var usingSampleData = false
    private(set) var sampleReason: String?

    /// The card currently on screen. Bound to the paging scroll view.
    var currentStoryID: UUID?

    let category: NewsCategory?
    private let repository: NewsRepository
    private var nextCursor: String?
    private var hasMore = true
    private let pageSize: Int

    init(category: NewsCategory?, repository: NewsRepository, pageSize: Int = 15) {
        self.category = category
        self.repository = repository
        self.pageSize = pageSize
        self.usingSampleData = repository.isSample
    }

    var categorySlug: String? { category?.slug }

    var currentIndex: Int? {
        guard let currentStoryID else { return nil }
        return stories.firstIndex { $0.id == currentStoryID }
    }

    var progressText: String {
        guard let index = currentIndex, !stories.isEmpty else { return "" }
        return "\(index + 1) of \(stories.count)"
    }

    // MARK: - Loading

    func loadIfNeeded() async {
        guard case .idle = phase else { return }
        await load()
    }

    func load() async {
        phase = .loading
        nextCursor = nil
        hasMore = true
        await fetchPage(replacing: true)
    }

    func refresh() async {
        isRefreshing = true
        nextCursor = nil
        hasMore = true
        await fetchPage(replacing: true)
        isRefreshing = false
    }

    /// Called as the reader approaches the end of the stack.
    func loadMoreIfNeeded(currentItem: Story) async {
        guard hasMore, !isLoadingMore, phase == .loaded else { return }
        let threshold = 4
        guard let index = stories.firstIndex(where: { $0.id == currentItem.id }),
              index >= stories.count - threshold else { return }
        isLoadingMore = true
        await fetchPage(replacing: false)
        isLoadingMore = false
    }

    private func fetchPage(replacing: Bool) async {
        do {
            let page = try await repository.stories(
                category: categorySlug, cursor: replacing ? nil : nextCursor, limit: pageSize
            )
            if replacing {
                stories = page.items
                currentStoryID = page.items.first?.id
            } else {
                // Defensive: a cursor bug on the server must never produce a
                // stack with the same card twice.
                let existing = Set(stories.map(\.id))
                stories.append(contentsOf: page.items.filter { !existing.contains($0.id) })
            }
            nextCursor = page.nextCursor
            hasMore = page.nextCursor != nil
            phase = .loaded
            usingSampleData = repository.isSample
        } catch let error as APIError {
            BrieflyLog.feed.error("feed load failed: \(error.localizedDescription)")
            if replacing, stories.isEmpty {
                phase = .failed(error)
            } else {
                phase = .loaded
                hasMore = false
            }
        } catch {
            phase = .failed(.transport(error.localizedDescription))
        }
    }

    func noteFallback(_ error: APIError) {
        usingSampleData = true
        sampleReason = error.errorDescription
    }

    // MARK: - Navigation helpers (also used by the accessibility actions)

    func goToNext() {
        guard let index = currentIndex, index + 1 < stories.count else { return }
        currentStoryID = stories[index + 1].id
    }

    func goToPrevious() {
        guard let index = currentIndex, index > 0 else { return }
        currentStoryID = stories[index - 1].id
    }

    func story(withID id: UUID) -> Story? {
        stories.first { $0.id == id }
    }
}
