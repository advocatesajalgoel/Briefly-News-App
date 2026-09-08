import Foundation

/// An audio briefing generated from the same story rows the cards use.
struct PodcastEpisode: Codable, Identifiable, Hashable, Sendable {
    let id: UUID
    /// `daily` or `deep_dive`.
    let kind: String
    let slug: String
    let title: String
    let subtitle: String?
    let editionDate: Date
    let publishedAt: Date?

    let audioURL: URL?
    let audioMimeType: String?
    let audioDurationSeconds: Int?
    let audioBytes: Int?
    let estimatedDurationSeconds: Int
    let scriptWordCount: Int

    let segments: [EpisodeSegment]
    let storyIDs: [UUID]
    /// Full narration, so the reader can follow along or read instead of listen.
    let transcript: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, slug, title, subtitle, editionDate, publishedAt
        case audioMimeType, audioDurationSeconds, audioBytes
        case estimatedDurationSeconds, scriptWordCount, segments, transcript
        case audioURL = "audioUrl"
        case storyIDs = "storyIds"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id)
        kind = try c.decode(String.self, forKey: .kind)
        slug = try c.decode(String.self, forKey: .slug)
        title = try c.decode(String.self, forKey: .title)
        subtitle = try c.decodeIfPresent(String.self, forKey: .subtitle)
        editionDate = try c.decode(Date.self, forKey: .editionDate)
        publishedAt = try c.decodeIfPresent(Date.self, forKey: .publishedAt)
        audioMimeType = try c.decodeIfPresent(String.self, forKey: .audioMimeType)
        audioDurationSeconds = try c.decodeIfPresent(Int.self, forKey: .audioDurationSeconds)
        audioBytes = try c.decodeIfPresent(Int.self, forKey: .audioBytes)
        estimatedDurationSeconds = try c.decodeIfPresent(Int.self, forKey: .estimatedDurationSeconds) ?? 0
        scriptWordCount = try c.decodeIfPresent(Int.self, forKey: .scriptWordCount) ?? 0
        segments = try c.decodeIfPresent([EpisodeSegment].self, forKey: .segments) ?? []
        storyIDs = try c.decodeIfPresent([UUID].self, forKey: .storyIDs) ?? []
        transcript = try c.decodeIfPresent(String.self, forKey: .transcript)
        let rawAudio = (try? c.decodeIfPresent(String.self, forKey: .audioURL)).flatMap { $0 }
        audioURL = PodcastEpisode.resolveAudioURL(rawAudio)
    }

    /// Turns the API's `audio_url` into something playable.
    ///
    /// A normal value is an absolute URL on the server. The bundled snapshot
    /// instead carries a bare filename — the sample episodes ship inside the app
    /// so the podcast tab is genuinely playable before any backend exists, and a
    /// relative path is the honest way to say "this one is local".
    static func resolveAudioURL(_ raw: String?, bundle: Bundle = .main) -> URL? {
        guard let raw, !raw.isEmpty else { return nil }
        if let url = URL(string: raw), url.scheme != nil { return url }
        let name = (raw as NSString).deletingPathExtension
        let ext = (raw as NSString).pathExtension
        return bundle.url(forResource: name, withExtension: ext.isEmpty ? "mp3" : ext)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(kind, forKey: .kind)
        try c.encode(slug, forKey: .slug)
        try c.encode(title, forKey: .title)
        try c.encodeIfPresent(subtitle, forKey: .subtitle)
        try c.encode(editionDate, forKey: .editionDate)
        try c.encodeIfPresent(publishedAt, forKey: .publishedAt)
        try c.encodeIfPresent(audioURL?.absoluteString, forKey: .audioURL)
        try c.encodeIfPresent(audioMimeType, forKey: .audioMimeType)
        try c.encodeIfPresent(audioDurationSeconds, forKey: .audioDurationSeconds)
        try c.encodeIfPresent(audioBytes, forKey: .audioBytes)
        try c.encode(estimatedDurationSeconds, forKey: .estimatedDurationSeconds)
        try c.encode(scriptWordCount, forKey: .scriptWordCount)
        try c.encode(segments, forKey: .segments)
        try c.encode(storyIDs, forKey: .storyIDs)
        try c.encodeIfPresent(transcript, forKey: .transcript)
    }

    var episodeKind: EpisodeKind { EpisodeKind(rawValue: kind) ?? .daily }

    /// Duration to display: the measured length when the audio exists, otherwise
    /// the estimate from the script.
    var durationSeconds: Int { audioDurationSeconds ?? estimatedDurationSeconds }

    var durationText: String { TimeFormatting.formatted(seconds: durationSeconds) }

    var isPlayable: Bool { audioURL != nil && durationSeconds > 0 }

    /// Chapters the player can jump between — story segments only.
    var chapters: [EpisodeSegment] { segments.filter { $0.kind == "story" } }
}

enum EpisodeKind: String, CaseIterable, Sendable {
    case daily
    case deepDive = "deep_dive"

    var title: String {
        switch self {
        case .daily:    return "Briefly Daily"
        case .deepDive: return "Deep Dive"
        }
    }

    var blurb: String {
        switch self {
        case .daily:
            return "Today's stories, narrated from the same facts as the cards."
        case .deepDive:
            return "One story, explained: what is confirmed, where sources disagree, what happens next."
        }
    }

    var systemImage: String {
        switch self {
        case .daily:    return "sun.horizon"
        case .deepDive: return "waveform.path"
        }
    }
}

struct EpisodeSegment: Codable, Hashable, Identifiable, Sendable {
    let kind: String
    let title: String?
    let storyID: UUID?
    let wordCount: Int
    let startOffsetSeconds: Int

    var id: String { "\(kind)-\(startOffsetSeconds)-\(title ?? "")" }

    enum CodingKeys: String, CodingKey {
        case kind, title, wordCount, startOffsetSeconds
        case storyID = "storyId"
    }

    var displayTitle: String {
        if let title, !title.isEmpty { return title }
        switch kind {
        case "intro": return "Introduction"
        case "outro": return "Outro"
        default:      return "Story"
        }
    }

    var startText: String { TimeFormatting.formatted(seconds: startOffsetSeconds) }
}

struct EpisodePage: Codable, Sendable {
    let items: [PodcastEpisode]
    let nextCursor: String?
}
