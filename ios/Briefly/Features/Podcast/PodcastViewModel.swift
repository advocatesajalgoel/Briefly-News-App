import Foundation
import Observation

/// Loads the episode list for the Podcast tab.
@MainActor
@Observable
final class PodcastViewModel {
    enum Phase: Equatable {
        case loading
        case loaded
        case failed(String)
    }

    private(set) var phase: Phase = .loading
    private(set) var daily: [PodcastEpisode] = []
    private(set) var deepDives: [PodcastEpisode] = []
    private(set) var usingSampleData = false

    private let repository: NewsRepository

    init(repository: NewsRepository) {
        self.repository = repository
        self.usingSampleData = repository.isSample
    }

    var latestDaily: PodcastEpisode? { daily.first }
    var hasAnything: Bool { !daily.isEmpty || !deepDives.isEmpty }

    func load() async {
        phase = .loading
        do {
            async let dailyTask = repository.episodes(kind: .daily)
            async let deepTask = repository.episodes(kind: .deepDive)
            let (dailyEpisodes, deepEpisodes) = try await (dailyTask, deepTask)
            daily = dailyEpisodes.sorted { $0.editionDate > $1.editionDate }
            deepDives = deepEpisodes.sorted { $0.editionDate > $1.editionDate }
            usingSampleData = repository.isSample
            phase = .loaded
        } catch let error as APIError {
            phase = .failed([error.errorDescription, error.recoverySuggestion]
                .compactMap { $0 }.joined(separator: " "))
        } catch {
            phase = .failed(error.localizedDescription)
        }
    }

    func refresh() async { await load() }
}
