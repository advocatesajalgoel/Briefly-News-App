import Foundation

/// What the app needs from a news source. Two implementations exist: one that
/// talks to a Briefly server, and one that reads the bundled snapshot.
///
/// The app is fully usable through the bundled one, which is why Phase 1 of the
/// build could ship a working product before the backend existed.
/// Not `Sendable`: every implementation is used from the main actor (the view
/// models and `AppEnvironment` are all `@MainActor`), and requiring it here would
/// force an `@unchecked` escape hatch on `BundledNewsRepository`, which holds a
/// `Bundle`. Isolation is expressed where it is actually enforced instead.
protocol NewsRepository {
    func categories() async throws -> [NewsCategory]
    func stories(category: String?, cursor: String?, limit: Int) async throws -> StoryPage
    func story(id: UUID) async throws -> Story
    func stories(ids: [UUID]) async throws -> [Story]
    func episodes(kind: EpisodeKind?) async throws -> [PodcastEpisode]
    func latestEpisode(kind: EpisodeKind) async throws -> PodcastEpisode
    /// True when this repository is serving bundled sample data.
    var isSample: Bool { get }
}

// MARK: - Bundled sample data

/// Reads the snapshot in `Resources/`, which is generated from the real API
/// serialisers by `backend/scripts/export_mock_data.py`.
struct BundledNewsRepository: NewsRepository {
    let bundle: Bundle
    var isSample: Bool { true }

    init(bundle: Bundle = .main) {
        self.bundle = bundle
    }

    private func load<T: Decodable>(_ resource: String, as type: T.Type) throws -> T {
        guard let url = bundle.url(forResource: resource, withExtension: "json") else {
            throw APIError.transport("Missing bundled resource \(resource).json")
        }
        let data = try Data(contentsOf: url)
        do {
            return try JSONDecoder.briefly.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }

    func categories() async throws -> [NewsCategory] {
        try load("mock_categories", as: [NewsCategory].self)
    }

    func stories(category: String?, cursor: String?, limit: Int) async throws -> StoryPage {
        let page = try load("mock_stories", as: StoryPage.self)
        var items = page.items
        if let category, category != "for-you", category != "all" {
            items = items.filter { $0.categorySlug == category }
        }
        items.sort { $0.rankScore > $1.rankScore }

        // The snapshot is small, but paginating it anyway keeps the sample path
        // exercising exactly the same cursor logic as the live one.
        let start = cursor.flatMap(Int.init) ?? 0
        let end = min(start + limit, items.count)
        let slice = start < end ? Array(items[start..<end]) : []
        return StoryPage(
            items: slice,
            nextCursor: end < items.count ? String(end) : nil,
            totalEstimate: items.count
        )
    }

    func story(id: UUID) async throws -> Story {
        let page = try load("mock_stories", as: StoryPage.self)
        guard let match = page.items.first(where: { $0.id == id }) else { throw APIError.notFound }
        return match
    }

    func stories(ids: [UUID]) async throws -> [Story] {
        let page = try load("mock_stories", as: StoryPage.self)
        let byID = Dictionary(uniqueKeysWithValues: page.items.map { ($0.id, $0) })
        return ids.compactMap { byID[$0] }
    }

    func episodes(kind: EpisodeKind?) async throws -> [PodcastEpisode] {
        let page = try load("mock_episodes", as: EpisodePage.self)
        guard let kind else { return page.items }
        return page.items.filter { $0.kind == kind.rawValue }
    }

    func latestEpisode(kind: EpisodeKind) async throws -> PodcastEpisode {
        let matching = try await episodes(kind: kind)
            .sorted { $0.editionDate > $1.editionDate }
        guard let first = matching.first else { throw APIError.notFound }
        return first
    }
}

// MARK: - Live server

struct RemoteNewsRepository: NewsRepository {
    private let client: APIClient
    var isSample: Bool { false }

    init(configuration: APIConfiguration) {
        self.client = APIClient(configuration: configuration)
    }

    func categories() async throws -> [NewsCategory] {
        try await client.get("/v1/categories")
    }

    func stories(category: String?, cursor: String?, limit: Int) async throws -> StoryPage {
        var query = [URLQueryItem(name: "limit", value: String(limit))]
        if let category, !category.isEmpty {
            query.append(URLQueryItem(name: "category", value: category))
        }
        if let cursor, !cursor.isEmpty {
            query.append(URLQueryItem(name: "cursor", value: cursor))
        }
        return try await client.get("/v1/stories", query: query)
    }

    func story(id: UUID) async throws -> Story {
        try await client.get("/v1/stories/\(id.uuidString.lowercased())")
    }

    func stories(ids: [UUID]) async throws -> [Story] {
        guard !ids.isEmpty else { return [] }
        return try await client.post("/v1/stories/batch", body: ids.map { $0.uuidString.lowercased() })
    }

    func episodes(kind: EpisodeKind?) async throws -> [PodcastEpisode] {
        var query: [URLQueryItem] = [URLQueryItem(name: "limit", value: "30")]
        if let kind { query.append(URLQueryItem(name: "kind", value: kind.rawValue)) }
        let page: EpisodePage = try await client.get("/v1/podcast/episodes", query: query)
        return page.items
    }

    func latestEpisode(kind: EpisodeKind) async throws -> PodcastEpisode {
        try await client.get(
            "/v1/podcast/latest", query: [URLQueryItem(name: "kind", value: kind.rawValue)]
        )
    }
}

// MARK: - Fallback

/// Tries the server; falls back to the bundled snapshot when there isn't one, or
/// when it cannot be reached.
///
/// The reader is told which they are looking at — a banner on the feed — because
/// silently showing week-old sample stories as if they were today's news would be
/// exactly the kind of thing this app exists not to do.
struct FallbackNewsRepository: NewsRepository {
    let remote: NewsRepository?
    let bundled: NewsRepository
    /// Set when the last call fell back, so the UI can say so.
    let onFallback: @Sendable (APIError) -> Void

    var isSample: Bool { remote == nil }

    init(remote: NewsRepository?,
         bundled: NewsRepository = BundledNewsRepository(),
         onFallback: @escaping @Sendable (APIError) -> Void = { _ in }) {
        self.remote = remote
        self.bundled = bundled
        self.onFallback = onFallback
    }

    private func attempt<T>(
        _ remoteCall: (NewsRepository) async throws -> T,
        fallback: (NewsRepository) async throws -> T
    ) async throws -> T {
        guard let remote else { return try await fallback(bundled) }
        do {
            return try await remoteCall(remote)
        } catch let error as APIError where error.isRetryable || error == .notConfigured {
            onFallback(error)
            return try await fallback(bundled)
        }
    }

    func categories() async throws -> [NewsCategory] {
        try await attempt({ try await $0.categories() }, fallback: { try await $0.categories() })
    }

    func stories(category: String?, cursor: String?, limit: Int) async throws -> StoryPage {
        try await attempt(
            { try await $0.stories(category: category, cursor: cursor, limit: limit) },
            fallback: { try await $0.stories(category: category, cursor: cursor, limit: limit) }
        )
    }

    func story(id: UUID) async throws -> Story {
        try await attempt({ try await $0.story(id: id) }, fallback: { try await $0.story(id: id) })
    }

    func stories(ids: [UUID]) async throws -> [Story] {
        try await attempt({ try await $0.stories(ids: ids) }, fallback: { try await $0.stories(ids: ids) })
    }

    func episodes(kind: EpisodeKind?) async throws -> [PodcastEpisode] {
        try await attempt({ try await $0.episodes(kind: kind) }, fallback: { try await $0.episodes(kind: kind) })
    }

    func latestEpisode(kind: EpisodeKind) async throws -> PodcastEpisode {
        try await attempt({ try await $0.latestEpisode(kind: kind) },
                          fallback: { try await $0.latestEpisode(kind: kind) })
    }
}
