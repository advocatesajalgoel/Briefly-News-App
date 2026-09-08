import SwiftUI

/// The vertical card stack — the app's primary experience.
///
/// Paging is done with SwiftUI's own scroll targets rather than a rotated
/// `TabView`: it gives a real swipe-up/swipe-down page turn, keeps VoiceOver's
/// reading order correct, and lets each card scroll internally when a reader has
/// text set very large.
struct FeedView: View {
    @Bindable var model: FeedViewModel

    @Environment(BookmarkStore.self) private var bookmarks
    @Environment(AppSettings.self) private var settings
    @Environment(\.openURL) private var openURL

    @State private var sourcesStory: Story?
    @State private var shareItem: SharePayload?

    var body: some View {
        Group {
            switch model.phase {
            case .idle, .loading:
                if model.stories.isEmpty {
                    StorySkeletonView()
                } else {
                    stack
                }
            case .failed(let error):
                ErrorStateView(
                    title: "Couldn't load the feed",
                    message: [error.errorDescription, error.recoverySuggestion]
                        .compactMap { $0 }.joined(separator: " "),
                    systemImage: error == .offline ? "wifi.slash" : "exclamationmark.triangle",
                    onRetry: { Task { await model.load() } }
                )
            case .loaded:
                if model.stories.isEmpty {
                    EmptyStateView(
                        title: "Nothing here yet",
                        message: "No stories have been published in this section. "
                               + "Pull to refresh once the pipeline has run.",
                        systemImage: "newspaper",
                        actionTitle: "Refresh",
                        action: { Task { await model.refresh() } }
                    )
                } else {
                    stack
                }
            }
        }
        .background(BrieflyColor.paper)
        .task { await model.loadIfNeeded() }
        .sheet(item: $sourcesStory) { story in
            SourcesSheet(story: story)
        }
        .sheet(item: $shareItem) { payload in
            ShareSheet(items: payload.items)
                .presentationDetents([.medium])
        }
    }

    // MARK: - The stack

    private var stack: some View {
        ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach(model.stories) { story in
                    StoryCardView(
                        story: story,
                        isSaved: bookmarks.contains(story),
                        showConfidence: settings.showConfidenceOnCards,
                        onOpenSources: { sourcesStory = story },
                        onToggleSave: { toggleSave(story) },
                        onShare: { shareItem = SharePayload(story: story) }
                    )
                    .containerRelativeFrame(.vertical)
                    .id(story.id)
                    .task { await model.loadMoreIfNeeded(currentItem: story) }
                    .accessibilityAction(named: "Next story") { model.goToNext() }
                    .accessibilityAction(named: "Previous story") { model.goToPrevious() }
                    .accessibilityAction(named: "Show sources") { sourcesStory = story }
                    .accessibilityAction(named: bookmarks.contains(story) ? "Remove from saved" : "Save") {
                        toggleSave(story)
                    }
                }

                if model.isLoadingMore {
                    ProgressView()
                        .tint(BrieflyColor.accent)
                        .frame(maxWidth: .infinity)
                        .frame(height: 60)
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.paging)
        .scrollPosition(id: $model.currentStoryID)
        .scrollIndicators(.hidden)
        // Deliberately *not* ignoring the bottom safe area: `containerRelativeFrame`
        // sizes each card to the scroll container, so extending the container under
        // the tab bar and the mini player would push the card's own footer — the
        // source count and the save button — out of reach.
        .refreshable { await model.refresh() }
        .onChange(of: model.currentStoryID) { _, _ in
            Haptics.pageTurn(enabled: settings.hapticsEnabled)
        }
    }

    private func toggleSave(_ story: Story) {
        let saved = bookmarks.toggle(story)
        if saved { Haptics.saved(enabled: settings.hapticsEnabled) }
    }
}

/// What "share" puts on the pasteboard: Briefly's own summary plus the source
/// links, never a publisher's article text.
struct SharePayload: Identifiable {
    let id = UUID()
    let items: [Any]

    init(story: Story) {
        var text = "\(story.headline)\n\n\(story.summary)\n\n\(story.sourceCountText):"
        for source in story.sourcesByTime.prefix(6) {
            text += "\n• \(source.sourceName)"
            if let url = source.originalURL { text += " — \(url.absoluteString)" }
        }
        text += "\n\nvia Briefly"
        self.items = [text]
    }
}

#if canImport(UIKit)
import UIKit

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
#else
struct ShareSheet: View {
    let items: [Any]
    var body: some View { Text("Sharing is unavailable on this platform.") }
}
#endif
