import SwiftUI

/// The five tabs. The feed is tab one and stays the primary experience.
struct RootView: View {
    @Environment(AppEnvironment.self) private var appEnvironment
    @Environment(AppSettings.self) private var settings

    @State private var selectedTab: Tab = .forYou
    @State private var feedModel: FeedViewModel?
    @State private var presentedEpisode: PodcastEpisode?

    enum Tab: Hashable {
        case forYou, sections, podcast, saved, settings
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            forYouTab
                .tabItem { Label("For You", systemImage: "sparkles") }
                .tag(Tab.forYou)

            CategoriesView()
                .tabItem { Label("Sections", systemImage: "square.grid.2x2") }
                .tag(Tab.sections)

            PodcastView()
                .tabItem { Label("Podcast", systemImage: "waveform") }
                .tag(Tab.podcast)

            SavedView()
                .tabItem { Label("Saved", systemImage: "bookmark") }
                .tag(Tab.saved)

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
                .tag(Tab.settings)
        }
        .tint(BrieflyColor.accent)
        .safeAreaInset(edge: .bottom) {
            if appEnvironment.player.episode != nil {
                MiniPlayerBar { presentedEpisode = appEnvironment.player.episode }
                    .animation(BrieflyMotion.sheet, value: appEnvironment.player.episode?.id)
            }
        }
        .sheet(item: $presentedEpisode) { episode in
            EpisodePlayerView(episode: episode)
        }
        .onChange(of: selectedTab) { _, _ in
            Haptics.selection(enabled: settings.hapticsEnabled)
        }
    }

    private var forYouTab: some View {
        NavigationStack {
            Group {
                if let feedModel {
                    VStack(spacing: 0) {
                        if appEnvironment.isShowingSampleData {
                            SampleDataBanner(reason: appEnvironment.fallbackReason) {
                                selectedTab = .settings
                            }
                        }
                        FeedView(model: feedModel)
                    }
                } else {
                    StorySkeletonView()
                }
            }
            .background(BrieflyColor.paper)
            .navigationTitle("Briefly")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) { wordmark }
            }
            .toolbarBackground(BrieflyColor.paper, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
        }
        .onAppear {
            if feedModel == nil {
                feedModel = FeedViewModel(category: nil, repository: appEnvironment.repository)
            }
        }
        .onChange(of: appEnvironment.settings.apiConfiguration) { _, _ in
            // A new server means a new stack of stories.
            feedModel = FeedViewModel(category: nil, repository: appEnvironment.repository)
        }
    }

    /// The wordmark: a serif name with a full stop. Briefly is a sentence that
    /// ends — that is the whole idea, so the mark says it.
    private var wordmark: some View {
        HStack(spacing: 1) {
            Text("Briefly")
                .font(.system(.headline, design: .serif, weight: .semibold))
                .foregroundStyle(BrieflyColor.ink)
            Text(".")
                .font(.system(.headline, design: .serif, weight: .bold))
                .foregroundStyle(BrieflyColor.accent)
        }
        .accessibilityAddTraits(.isHeader)
        .accessibilityLabel("Briefly")
    }
}
