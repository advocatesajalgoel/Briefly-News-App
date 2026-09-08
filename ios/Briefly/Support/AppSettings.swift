import Foundation
import Observation
import SwiftUI

/// Reader-facing preferences plus the server address.
@MainActor
@Observable
final class AppSettings {
    /// `system`, `light` or `dark`.
    var appearance: AppearanceOption {
        didSet { defaults.set(appearance.rawValue, forKey: Keys.appearance) }
    }

    /// Show the confidence chip (Confirmed / Disputed / Reported) on cards.
    var showConfidenceOnCards: Bool {
        didSet { defaults.set(showConfidenceOnCards, forKey: Keys.showConfidence) }
    }

    /// Play a light haptic when the reader moves between cards.
    var hapticsEnabled: Bool {
        didSet { defaults.set(hapticsEnabled, forKey: Keys.haptics) }
    }

    /// Continue audio when the app is backgrounded or the screen locks.
    var backgroundAudioEnabled: Bool {
        didSet { defaults.set(backgroundAudioEnabled, forKey: Keys.backgroundAudio) }
    }

    var playbackRate: Double {
        didSet { defaults.set(playbackRate, forKey: Keys.playbackRate) }
    }

    private(set) var apiConfiguration: APIConfiguration

    private let defaults: UserDefaults

    private enum Keys {
        static let appearance = "briefly.appearance"
        static let showConfidence = "briefly.showConfidence"
        static let haptics = "briefly.haptics"
        static let backgroundAudio = "briefly.backgroundAudio"
        static let playbackRate = "briefly.playbackRate"
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.appearance = AppearanceOption(
            rawValue: defaults.string(forKey: Keys.appearance) ?? ""
        ) ?? .system
        self.showConfidenceOnCards = defaults.object(forKey: Keys.showConfidence) as? Bool ?? true
        self.hapticsEnabled = defaults.object(forKey: Keys.haptics) as? Bool ?? true
        self.backgroundAudioEnabled = defaults.object(forKey: Keys.backgroundAudio) as? Bool ?? true
        self.playbackRate = defaults.object(forKey: Keys.playbackRate) as? Double ?? 1.0
        self.apiConfiguration = APIConfiguration.load(defaults: defaults)
    }

    func updateServer(baseURL: String, clientKey: String) {
        let trimmedURL = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedKey = clientKey.trimmingCharacters(in: .whitespacesAndNewlines)
        let url = trimmedURL.isEmpty ? nil : URL(string: trimmedURL)
        let configuration = APIConfiguration(
            baseURL: url, clientKey: trimmedKey.isEmpty ? nil : trimmedKey
        )
        configuration.save(to: defaults)
        apiConfiguration = configuration
    }

    func clearServer() {
        APIConfiguration.offline.save(to: defaults)
        apiConfiguration = .offline
    }
}

enum AppearanceOption: String, CaseIterable, Identifiable, Sendable {
    case system, light, dark

    var id: String { rawValue }

    var label: String {
        switch self {
        case .system: return "System"
        case .light:  return "Light"
        case .dark:   return "Dark"
        }
    }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light:  return .light
        case .dark:   return .dark
        }
    }
}
