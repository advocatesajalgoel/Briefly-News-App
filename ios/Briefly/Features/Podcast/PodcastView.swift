import SwiftUI

/// Tab 3. Briefly Daily at the top, Deep Dives underneath.
struct PodcastView: View {
    @Environment(AppEnvironment.self) private var appEnvironment
    @Environment(AudioPlayerController.self) private var player
    @State private var model: PodcastViewModel?
    @State private var presentedEpisode: PodcastEpisode?

    var body: some View {
        NavigationStack {
            Group {
                if let model {
                    content(model)
                } else {
                    LoadingStateView(message: "Loading briefings")
                }
            }
            .background(BrieflyColor.paper)
            .navigationTitle("Podcast")
        }
        .task {
            if model == nil {
                model = PodcastViewModel(repository: appEnvironment.repository)
            }
            await model?.load()
        }
        .sheet(item: $presentedEpisode) { episode in
            EpisodePlayerView(episode: episode)
        }
    }

    @ViewBuilder
    private func content(_ model: PodcastViewModel) -> some View {
        switch model.phase {
        case .loading:
            LoadingStateView(message: "Loading briefings")
        case .failed(let message):
            ErrorStateView(
                title: "Couldn't load briefings",
                message: message,
                onRetry: { Task { await model.refresh() } }
            )
        case .loaded:
            if !model.hasAnything {
                EmptyStateView(
                    title: "No briefings yet",
                    message: "Briefly Daily is produced once the pipeline has published "
                           + "enough stories to narrate. Run the daily job on your server, "
                           + "then pull to refresh.",
                    systemImage: "waveform",
                    actionTitle: "Refresh",
                    action: { Task { await model.refresh() } }
                )
            } else {
                list(model)
            }
        }
    }

    private func list(_ model: PodcastViewModel) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: BrieflySpace.xl) {
                if let latest = model.latestDaily {
                    featured(latest)
                }

                if model.daily.count > 1 {
                    section(
                        title: "Earlier editions",
                        episodes: Array(model.daily.dropFirst())
                    )
                }

                if !model.deepDives.isEmpty {
                    VStack(alignment: .leading, spacing: BrieflySpace.s) {
                        Text(EpisodeKind.deepDive.title).brieflySectionHeader()
                        Text(EpisodeKind.deepDive.blurb)
                            .font(BrieflyFont.caption)
                            .foregroundStyle(BrieflyColor.inkMuted)
                            .padding(.bottom, BrieflySpace.xs)
                        episodeRows(model.deepDives)
                    }
                }
            }
            .padding(.horizontal, BrieflySpace.pageMargin)
            .padding(.vertical, BrieflySpace.l)
            .padding(.bottom, BrieflySpace.xxxl)
        }
        .refreshable { await model.refresh() }
    }

    private func featured(_ episode: PodcastEpisode) -> some View {
        VStack(alignment: .leading, spacing: BrieflySpace.m) {
            Text(EpisodeKind.daily.title).brieflySectionHeader()

            VStack(alignment: .leading, spacing: BrieflySpace.m) {
                Text(episode.title)
                    .font(BrieflyFont.headline(.compact))
                    .foregroundStyle(BrieflyColor.ink)
                    .fixedSize(horizontal: false, vertical: true)

                if let subtitle = episode.subtitle {
                    Text(subtitle)
                        .font(BrieflyFont.caption)
                        .foregroundStyle(BrieflyColor.inkMuted)
                }

                HStack(spacing: BrieflySpace.m) {
                    Button {
                        if player.isCurrent(episode) {
                            player.togglePlayPause()
                        } else {
                            player.load(episode)
                        }
                        presentedEpisode = episode
                    } label: {
                        Label(
                            player.isCurrent(episode) && player.isPlaying ? "Pause" : "Play",
                            systemImage: player.isCurrent(episode) && player.isPlaying
                                ? "pause.fill" : "play.fill"
                        )
                    }
                    .buttonStyle(BrieflyPrimaryButtonStyle())
                    .disabled(!episode.isPlayable)

                    VStack(alignment: .leading, spacing: 1) {
                        Text(TimeFormatting.approximate(seconds: episode.durationSeconds))
                            .font(BrieflyFont.label)
                            .foregroundStyle(BrieflyColor.ink)
                        Text("\(episode.chapters.count) stories")
                            .font(.caption2)
                            .foregroundStyle(BrieflyColor.inkMuted)
                    }
                    Spacer(minLength: 0)
                }

                if !episode.isPlayable {
                    Text("Audio for this edition hasn't been generated yet.")
                        .font(.caption2)
                        .foregroundStyle(BrieflyColor.reported)
                }
            }
            .padding(BrieflySpace.l)
            .background(
                RoundedRectangle(cornerRadius: BrieflyRadius.card, style: .continuous)
                    .fill(BrieflyColor.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: BrieflyRadius.card, style: .continuous)
                    .strokeBorder(BrieflyColor.rule, lineWidth: 1)
            )
            .contentShape(Rectangle())
            .onTapGesture { presentedEpisode = episode }
        }
    }

    private func section(title: String, episodes: [PodcastEpisode]) -> some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            Text(title).brieflySectionHeader()
            episodeRows(episodes)
        }
    }

    private func episodeRows(_ episodes: [PodcastEpisode]) -> some View {
        VStack(spacing: 0) {
            ForEach(Array(episodes.enumerated()), id: \.element.id) { index, episode in
                Button { presentedEpisode = episode } label: {
                    HStack(spacing: BrieflySpace.m) {
                        Image(systemName: episode.episodeKind.systemImage)
                            .font(.body)
                            .foregroundStyle(BrieflyColor.accent)
                            .frame(width: 24)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(episode.title)
                                .font(BrieflyFont.body)
                                .foregroundStyle(BrieflyColor.ink)
                                .multilineTextAlignment(.leading)
                                .lineLimit(2)
                            Text(TimeFormatting.approximate(seconds: episode.durationSeconds))
                                .font(.caption2)
                                .foregroundStyle(BrieflyColor.inkMuted)
                        }
                        Spacer(minLength: 0)
                        Image(systemName: "chevron.right")
                            .font(.caption2)
                            .foregroundStyle(BrieflyColor.inkFaint)
                            .accessibilityHidden(true)
                    }
                    .padding(.vertical, BrieflySpace.m)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                if index < episodes.count - 1 { BrieflyRule(opacity: 0.6) }
            }
        }
    }
}
