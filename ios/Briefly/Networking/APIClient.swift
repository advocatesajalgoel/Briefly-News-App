import Foundation

/// Errors the UI knows how to explain.
enum APIError: LocalizedError, Equatable {
    case notConfigured
    case offline
    case timedOut
    case unauthorized
    case notFound
    case server(status: Int)
    case decoding(String)
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .notConfigured: return "No Briefly server is configured."
        case .offline:       return "You appear to be offline."
        case .timedOut:      return "The server took too long to respond."
        case .unauthorized:  return "This Briefly server rejected the app's key."
        case .notFound:      return "That isn't on the server any more."
        case .server(let status): return "The server returned an error (\(status))."
        case .decoding:      return "The server sent something this version can't read."
        case .transport(let detail): return detail
        }
    }

    /// What the reader can actually do about it.
    var recoverySuggestion: String? {
        switch self {
        case .notConfigured:
            return "Add your server's address in Settings, or keep reading the bundled sample stories."
        case .offline:
            return "Check your connection and pull to refresh."
        case .timedOut, .server, .transport:
            return "Pull to refresh to try again."
        case .unauthorized:
            return "Check the client key in Settings."
        case .notFound:
            return "Pull to refresh for the current stories."
        case .decoding:
            return "Updating the app should fix this."
        }
    }

    var isRetryable: Bool {
        switch self {
        case .offline, .timedOut, .server, .transport: return true
        case .notConfigured, .unauthorized, .notFound, .decoding: return false
        }
    }
}

/// A small JSON client. No third-party dependency: `URLSession` does this well.
actor APIClient {
    private let configuration: APIConfiguration
    private let session: URLSession
    private let decoder: JSONDecoder

    init(configuration: APIConfiguration, session: URLSession? = nil) {
        self.configuration = configuration
        if let session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = configuration.timeout
            config.waitsForConnectivity = false
            config.requestCachePolicy = .reloadRevalidatingCacheData
            self.session = URLSession(configuration: config)
        }
        self.decoder = JSONDecoder.briefly
    }

    func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        try await send(request(method: "GET", path: path, query: query))
    }

    func post<T: Decodable, Body: Encodable>(
        _ path: String, body: Body, query: [URLQueryItem] = []
    ) async throws -> T {
        var request = try request(method: "POST", path: path, query: query)
        request.httpBody = try JSONEncoder.briefly.encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return try await send(request)
    }

    func delete(_ path: String, query: [URLQueryItem] = []) async throws {
        _ = try await raw(request(method: "DELETE", path: path, query: query))
    }

    // MARK: - Plumbing

    private func request(method: String, path: String, query: [URLQueryItem]) throws -> URLRequest {
        guard let baseURL = configuration.baseURL else { throw APIError.notConfigured }
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(path),
            resolvingAgainstBaseURL: false
        ) else {
            throw APIError.notConfigured
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw APIError.notConfigured }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let key = configuration.clientKey, !key.isEmpty {
            request.setValue(key, forHTTPHeaderField: "X-Briefly-Key")
        }
        return request
    }

    private func raw(_ request: URLRequest) async throws -> Data {
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw APIError.transport("The server sent an unexpected response.")
            }
            switch http.statusCode {
            case 200..<300: return data
            case 401, 403:  throw APIError.unauthorized
            case 404:       throw APIError.notFound
            default:        throw APIError.server(status: http.statusCode)
            }
        } catch let error as APIError {
            throw error
        } catch let error as URLError {
            switch error.code {
            case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed:
                throw APIError.offline
            case .timedOut:
                throw APIError.timedOut
            default:
                throw APIError.transport(error.localizedDescription)
            }
        }
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data = try await raw(request)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            BrieflyLog.networking.error("decoding \(String(describing: T.self)): \(String(describing: error))")
            throw APIError.decoding(String(describing: error))
        }
    }
}
