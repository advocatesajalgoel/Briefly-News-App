import Foundation
import Observation

/// Everything the views need, assembled in one place.
///
/// Holding the repository here — rather than constructing one per screen — means
/// changing the server address in Settings takes effect everywhere on the next
/// refresh, without restarting the app.
@MainActor
@Observable
final class AppEnvironment {
    let settings: AppSettings
    let bookmarks: BookmarkStore
    let player: AudioPlayerController

    private(set) var repository: NewsRepository
    /// Set when a live call failed and the bundled snapshot was served instead.
    private(set) var fallbackReason: String?

    init(settings: AppSettings = AppSettings(),
         bookmarks: BookmarkStore = BookmarkStore(),
         repository: NewsRepository? = nil) {
        self.settings = settings
        self.bookmarks = bookmarks
        self.player = AudioPlayerController(
            backgroundAudioEnabled: settings.backgroundAudioEnabled
        )
        self.repository = repository ?? Self.makeRepository(for: settings.apiConfiguration)
        self.player.rate = Float(settings.playbackRate)
    }

    /// Called after the reader edits the server settings.
    func rebuildRepository() {
        fallbackReason = nil
        repository = Self.makeRepository(for: settings.apiConfiguration) { [weak self] reason in
            Task { @MainActor in self?.fallbackReason = reason }
        }
    }

    var isShowingSampleData: Bool { repository.isSample || fallbackReason != nil }

    private static func makeRepository(
        for configuration: APIConfiguration,
        onFallback: (@Sendable (String) -> Void)? = nil
    ) -> NewsRepository {
        let remote = configuration.isConfigured
            ? RemoteNewsRepository(configuration: configuration) : nil
        return FallbackNewsRepository(remote: remote) { error in
            BrieflyLog.networking.warning("falling back to bundled data: \(error.localizedDescription)")
            onFallback?(error.errorDescription ?? "The server could not be reached.")
        }
    }
}
