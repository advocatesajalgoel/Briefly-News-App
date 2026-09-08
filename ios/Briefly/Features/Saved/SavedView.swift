import SwiftUI

/// Tab 4. Stories the reader kept, stored on the device.
struct SavedView: View {
    @Environment(BookmarkStore.self) private var bookmarks
    @Environment(AppEnvironment.self) private var appEnvironment
    @State private var selected: Story?
    @State private var isRefreshing = false

    var body: some View {
        NavigationStack {
            Group {
                if bookmarks.isEmpty {
                    EmptyStateView(
                        title: "Nothing saved yet",
                        message: "Tap Save on any card and it will be kept here — "
                               + "with its sources and links — even when you're offline.",
                        systemImage: "bookmark"
                    )
                } else {
                    list
                }
            }
            .background(BrieflyColor.paper)
            .navigationTitle("Saved")
            .toolbar {
                if !bookmarks.isEmpty {
                    ToolbarItem(placement: .topBarTrailing) { EditButton() }
                }
            }
            .sheet(item: $selected) { story in
                SavedStoryDetail(story: story)
            }
        }
    }

    private var list: some View {
        List {
            ForEach(bookmarks.stories) { story in
                Button { selected = story } label: { row(story) }
                    .buttonStyle(.plain)
                    .listRowBackground(BrieflyColor.paper)
                    .listRowSeparatorTint(BrieflyColor.rule)
            }
            .onDelete { bookmarks.remove(atOffsets: $0) }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(BrieflyColor.paper)
        .refreshable { await refresh() }
    }

    private func row(_ story: Story) -> some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            HStack(spacing: BrieflySpace.s) {
                if let category = story.categoryName {
                    Text(category.uppercased())
                        .font(.caption2.weight(.medium))
                        .tracking(0.9)
                        .foregroundStyle(BrieflyColor.accent)
                }
                Text(story.timestampText)
                    .font(.caption2)
                    .foregroundStyle(BrieflyColor.inkFaint)
                Spacer(minLength: 0)
                Text(story.sourceCountText)
                    .font(.caption2)
                    .foregroundStyle(BrieflyColor.inkFaint)
            }
            Text(story.headline)
                .font(.system(.headline, design: .serif))
                .foregroundStyle(BrieflyColor.ink)
                .fixedSize(horizontal: false, vertical: true)
                .multilineTextAlignment(.leading)
            Text(story.summary)
                .font(BrieflyFont.caption)
                .foregroundStyle(BrieflyColor.inkMuted)
                .lineLimit(3)
                .multilineTextAlignment(.leading)
        }
        .padding(.vertical, BrieflySpace.xs)
    }

    /// Saved stories keep their own copy, but refreshing picks up a corrected
    /// summary or an added source without the reader losing the bookmark.
    private func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        let ids = bookmarks.stories.map(\.id)
        if let updated = try? await appEnvironment.repository.stories(ids: ids) {
            bookmarks.refresh(with: updated)
        }
    }
}

/// A saved story, shown as a card with its sources one tap away.
struct SavedStoryDetail: View {
    let story: Story
    @Environment(BookmarkStore.self) private var bookmarks
    @Environment(AppSettings.self) private var settings
    @Environment(\.dismiss) private var dismiss
    @State private var showSources = false
    @State private var shareItem: SharePayload?

    var body: some View {
        NavigationStack {
            StoryCardView(
                story: story,
                isSaved: bookmarks.contains(story),
                showConfidence: settings.showConfidenceOnCards,
                onOpenSources: { showSources = true },
                onToggleSave: { bookmarks.toggle(story) },
                onShare: { shareItem = SharePayload(story: story) }
            )
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .sheet(isPresented: $showSources) { SourcesSheet(story: story) }
            .sheet(item: $shareItem) { ShareSheet(items: $0.items) }
        }
    }
}
