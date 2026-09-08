import Foundation

/// One event, as reported by one or more publishers.
///
/// Mirrors `StoryOut` in `backend/app/schemas.py`. The bundled JSON in
/// `Resources/` is generated from that same serialiser (see
/// `backend/scripts/export_mock_data.py`), so a mismatch shows up as a decoding
/// failure in the test suite rather than as an empty screen on device.
struct Story: Codable, Identifiable, Hashable, Sendable {
    let id: UUID
    let slug: String

    /// Neutral headline. Selected from the plainest formulation the sources used,
    /// never a paraphrase Briefly invented.
    let headline: String

    /// The card summary. Guaranteed by the backend — in code and by a database
    /// constraint — to be 30 words or fewer.
    let summary: String
    let summaryWordCount: Int

    /// A longer neutral standfirst, used on the detail sheet when present.
    let dek: String?

    let categorySlug: String?
    let categoryName: String?

    let publishedAt: Date?
    let firstReportedAt: Date?
    let lastReportedAt: Date?

    let sourceCount: Int
    let independentSourceCount: Int
    let hasOfficialSource: Bool
    let hasDisputedClaims: Bool

    /// `confirmed`, `disputed` or `reported`.
    let confidence: String

    let diversity: SourceDiversity
    let sources: [StorySource]
    let facts: [ExtractedFact]
    let rankScore: Double

    // MARK: - Derived

    var confidenceLevel: ConfidenceLevel {
        ConfidenceLevel(rawValue: confidence) ?? .reported
    }

    /// What the card shows above the headline.
    var timestampText: String {
        RelativeTime.string(for: publishedAt ?? lastReportedAt)
    }

    var sourceCountText: String {
        sourceCount == 1 ? "1 source" : "\(sourceCount) sources"
    }

    var confirmedFacts: [ExtractedFact] { facts.filter { $0.kind == "confirmed" } }
    var attributedFacts: [ExtractedFact] { facts.filter { $0.kind == "attributed" } }
    var disputedFacts: [ExtractedFact] { facts.filter { $0.kind == "disputed" } }
    var uncertainFacts: [ExtractedFact] { facts.filter { $0.kind == "uncertain" } }
    var keyFigures: [ExtractedFact] { facts.filter { $0.slot == "number" } }

    /// Sources that filed first, oldest first — the order the sheet lists them in.
    var sourcesByTime: [StorySource] {
        sources.sorted { lhs, rhs in
            if lhs.isPrimarySource != rhs.isPrimarySource { return lhs.isPrimarySource }
            return (lhs.publishedAt ?? .distantFuture) < (rhs.publishedAt ?? .distantFuture)
        }
    }
}

enum ConfidenceLevel: String, Sendable {
    case confirmed
    case disputed
    case reported

    var label: String {
        switch self {
        case .confirmed: return "Confirmed"
        case .disputed:  return "Disputed"
        case .reported:  return "Reported"
        }
    }

    /// Plain-language explanation shown in the transparency sheet. Briefly does
    /// not claim to be unbiased, so these describe what was actually checked.
    var explanation: String {
        switch self {
        case .confirmed:
            return "Several independent outlets, or an official source, state this directly."
        case .disputed:
            return "Sources contradict each other on part of this story. Both accounts are listed below."
        case .reported:
            return "Reported, but not yet independently corroborated. Treat it as one account."
        }
    }

    var systemImage: String {
        switch self {
        case .confirmed: return "checkmark.seal"
        case .disputed:  return "exclamationmark.bubble"
        case .reported:  return "dot.radiowaves.left.and.right"
        }
    }
}

/// One row of the source-transparency panel.
struct StorySource: Codable, Hashable, Identifiable, Sendable {
    let sourceName: String
    let sourceKind: String
    /// The publisher's own headline, quoted exactly as they wrote it.
    let originalHeadline: String
    let originalURL: URL?
    let publishedAt: Date?
    let isPrimarySource: Bool

    var id: String { sourceName + originalHeadline }

    enum CodingKeys: String, CodingKey {
        case sourceName, sourceKind, originalHeadline, publishedAt, isPrimarySource
        case originalURL = "originalUrl"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sourceName = try container.decode(String.self, forKey: .sourceName)
        sourceKind = try container.decode(String.self, forKey: .sourceKind)
        originalHeadline = try container.decode(String.self, forKey: .originalHeadline)
        publishedAt = try container.decodeIfPresent(Date.self, forKey: .publishedAt)
        isPrimarySource = try container.decodeIfPresent(Bool.self, forKey: .isPrimarySource) ?? false
        // A malformed URL must not lose the whole story; the row simply is not tappable.
        originalURL = (try? container.decodeIfPresent(String.self, forKey: .originalURL))
            .flatMap { $0.flatMap(URL.init(string:)) }
    }

    init(sourceName: String, sourceKind: String, originalHeadline: String,
         originalURL: URL?, publishedAt: Date?, isPrimarySource: Bool) {
        self.sourceName = sourceName
        self.sourceKind = sourceKind
        self.originalHeadline = originalHeadline
        self.originalURL = originalURL
        self.publishedAt = publishedAt
        self.isPrimarySource = isPrimarySource
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(sourceName, forKey: .sourceName)
        try container.encode(sourceKind, forKey: .sourceKind)
        try container.encode(originalHeadline, forKey: .originalHeadline)
        try container.encodeIfPresent(publishedAt, forKey: .publishedAt)
        try container.encode(isPrimarySource, forKey: .isPrimarySource)
        try container.encodeIfPresent(originalURL?.absoluteString, forKey: .originalURL)
    }

    var kindLabel: String {
        switch sourceKind {
        case "official":      return "Official source"
        case "wire":          return "Wire service"
        case "international": return "International"
        case "regional":      return "Regional"
        case "national":      return "National"
        default:              return "Publisher"
        }
    }

    var timestampText: String { RelativeTime.string(for: publishedAt) }
}

/// A structured fact the summary and the narration were both written from.
struct ExtractedFact: Codable, Hashable, Identifiable, Sendable {
    let slot: String
    let kind: String
    let text: String
    let attributedTo: String?
    let supportCount: Int

    var id: String { "\(slot)|\(kind)|\(text)" }

    var isConfirmed: Bool { kind == "confirmed" }
    var isDisputed: Bool { kind == "disputed" }

    /// How the fact is introduced in the transparency sheet.
    var attributionText: String? {
        guard let attributedTo, !attributedTo.isEmpty else { return nil }
        switch kind {
        case "disputed": return "\(attributedTo) disputes this"
        default:         return "According to \(attributedTo)"
        }
    }

    var supportText: String? {
        guard supportCount > 1 else { return nil }
        return "\(supportCount) sources"
    }
}

/// The Source Diversity indicator.
///
/// A count of where reporting came from. Not a bias score — the `disclaimer`
/// travels with the data so the UI cannot show the number without the caveat.
struct SourceDiversity: Codable, Hashable, Sendable {
    let level: String
    let total: Int
    let independent: Int
    let countries: Int
    let hasOfficial: Bool
    let lines: [String]
    let byKind: [String: Int]
    let byCountry: [String: Int]
    let disclaimer: String

    var levelLabel: String { level.uppercased() }

    var levelRank: Int {
        switch level {
        case "high":   return 3
        case "medium": return 2
        default:       return 1
        }
    }

    static let empty = SourceDiversity(
        level: "low", total: 0, independent: 0, countries: 0, hasOfficial: false,
        lines: [], byKind: [:], byCountry: [:],
        disclaimer: "Source diversity counts where reporting came from. It is not a measurement of bias."
    )
}

/// A page of stories.
struct StoryPage: Codable, Sendable {
    let items: [Story]
    let nextCursor: String?
    let totalEstimate: Int?
}
