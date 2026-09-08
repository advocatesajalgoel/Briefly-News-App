import Foundation

/// How Briefly encodes and decodes everything that crosses the wire.
///
/// This lives with the models rather than with the network client because the
/// bundled snapshot uses exactly the same configuration — and because keeping it
/// Foundation-only lets the whole Codable surface be compiled and tested on
/// Linux, with no Mac involved. See `ios/Package.swift`.
///
/// A note on `.convertFromSnakeCase`: it rewrites *every* key, including the
/// keys of `[String: Int]` dictionaries such as the diversity breakdown. That is
/// safe here only because those keys contain no underscores — Foundation leaves
/// a single-component key alone. Adding a dictionary whose keys are snake_cased
/// would need an explicit `CodingKey` type instead.

extension JSONDecoder {
    /// The decoder both the network client and the bundled snapshot use.
    ///
    /// The date strategy accepts ISO-8601 with or without fractional seconds,
    /// because the API emits both (a timestamp written by Postgres carries
    /// microseconds; one parsed from an RSS feed does not).
    static var briefly: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            if let date = ISO8601DateFormatter.brieflyFractional.date(from: raw) { return date }
            if let date = ISO8601DateFormatter.brieflyPlain.date(from: raw) { return date }
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "Unrecognised date: \(raw)"
            )
        }
        return decoder
    }
}

extension JSONEncoder {
    static var briefly: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}

extension ISO8601DateFormatter {
    static let brieflyFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    static let brieflyPlain: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}
