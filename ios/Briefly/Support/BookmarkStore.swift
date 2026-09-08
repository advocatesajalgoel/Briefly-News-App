import Foundation
import Observation

/// Saved stories.
///
/// Local by design for v1, as the brief allows: the whole story is kept on
/// device, so a bookmark still opens with its sources and links when the reader
/// is on a plane and the server is unreachable. Writes are atomic and off the
/// main thread; a corrupt file is discarded rather than crashing the app.
@MainActor
@Observable
final class BookmarkStore {
    private(set) var stories: [Story] = []
    private(set) var lastError: String?

    private let fileURL: URL
    private let encoder = JSONEncoder.briefly
    private let decoder = JSONDecoder.briefly

    init(directory: URL? = nil) {
        let base = directory ?? FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        ).first ?? FileManager.default.temporaryDirectory
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        self.fileURL = base.appendingPathComponent("briefly-bookmarks.json")
        load()
    }

    // MARK: - Queries

    var isEmpty: Bool { stories.isEmpty }
    var count: Int { stories.count }

    func contains(_ story: Story) -> Bool {
        stories.contains { $0.id == story.id }
    }

    func contains(id: UUID) -> Bool {
        stories.contains { $0.id == id }
    }

    // MARK: - Mutations

    @discardableResult
    func toggle(_ story: Story) -> Bool {
        if contains(story) {
            remove(story)
            return false
        }
        add(story)
        return true
    }

    func add(_ story: Story) {
        guard !contains(story) else { return }
        stories.insert(story, at: 0)
        persist()
    }

    func remove(_ story: Story) {
        stories.removeAll { $0.id == story.id }
        persist()
    }

    func remove(atOffsets offsets: IndexSet) {
        stories.remove(atOffsets: offsets)
        persist()
    }

    func removeAll() {
        stories.removeAll()
        persist()
    }

    /// Replaces a saved copy with a fresher one from the server, keeping its
    /// position. A story that has been unpublished simply keeps its saved copy.
    func refresh(with updated: [Story]) {
        guard !updated.isEmpty else { return }
        let byID = Dictionary(uniqueKeysWithValues: updated.map { ($0.id, $0) })
        stories = stories.map { byID[$0.id] ?? $0 }
        persist()
    }

    // MARK: - Storage

    private func load() {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return }
        do {
            let data = try Data(contentsOf: fileURL)
            stories = try decoder.decode([Story].self, from: data)
        } catch {
            // A file written by an older, incompatible version is not worth
            // crashing over — start clean and say so rather than failing to launch.
            BrieflyLog.storage.error("dropping unreadable bookmarks: \(String(describing: error))")
            stories = []
            try? FileManager.default.removeItem(at: fileURL)
        }
    }

    private func persist() {
        let snapshot = stories
        let url = fileURL
        Task.detached(priority: .utility) {
            do {
                // A fresh encoder inside the task: JSONEncoder is not Sendable,
                // so capturing the shared one would cross an isolation boundary.
                let data = try JSONEncoder.briefly.encode(snapshot)
                try data.write(to: url, options: [.atomic, .completeFileUntilFirstUserAuthentication])
            } catch {
                BrieflyLog.storage.error("saving bookmarks failed: \(String(describing: error))")
            }
        }
    }
}
