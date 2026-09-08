import Foundation

/// Where the app talks to, and how it behaves when it cannot.
///
/// There is no credential here and there never will be. The app knows a base URL
/// and, optionally, a shared client key the operator may set; every private key —
/// model providers, text-to-speech, storage, the database — lives on the server.
struct APIConfiguration: Equatable, Sendable {
    var baseURL: URL?
    var clientKey: String?
    var timeout: TimeInterval = 20

    /// No backend configured: the app runs entirely on its bundled snapshot.
    static let offline = APIConfiguration(baseURL: nil, clientKey: nil)

    /// The simulator's view of a backend running on the development machine.
    static let localDevelopment = APIConfiguration(
        baseURL: URL(string: "http://localhost:8000"), clientKey: nil
    )

    var isConfigured: Bool { baseURL != nil }

    // MARK: - Persistence

    private static let baseURLKey = "briefly.api.baseURL"
    private static let clientKeyKey = "briefly.api.clientKey"

    /// Reads the configuration a reader entered in Settings, falling back to the
    /// value baked in at build time (`BRIEFLY_API_BASE_URL` in Info.plist).
    static func load(defaults: UserDefaults = .standard, bundle: Bundle = .main) -> APIConfiguration {
        if let stored = defaults.string(forKey: baseURLKey), let url = URL(string: stored) {
            return APIConfiguration(url: url, clientKey: defaults.string(forKey: clientKeyKey))
        }
        if let configured = bundle.object(forInfoDictionaryKey: "BRIEFLY_API_BASE_URL") as? String,
           !configured.isEmpty, !configured.hasPrefix("$("),
           let url = URL(string: configured) {
            return APIConfiguration(url: url, clientKey: nil)
        }
        return .offline
    }

    func save(to defaults: UserDefaults = .standard) {
        if let baseURL {
            defaults.set(baseURL.absoluteString, forKey: Self.baseURLKey)
        } else {
            defaults.removeObject(forKey: Self.baseURLKey)
        }
        if let clientKey, !clientKey.isEmpty {
            defaults.set(clientKey, forKey: Self.clientKeyKey)
        } else {
            defaults.removeObject(forKey: Self.clientKeyKey)
        }
    }

    init(baseURL: URL?, clientKey: String?, timeout: TimeInterval = 20) {
        self.baseURL = baseURL
        self.clientKey = clientKey
        self.timeout = timeout
    }

    private init(url: URL, clientKey: String?) {
        self.baseURL = url
        self.clientKey = clientKey
    }
}
