import SwiftUI

/// The compact bar that sits above the tab bar while something is playing.
struct MiniPlayerBar: View {
    @Environment(AudioPlayerController.self) private var player
    let onTap: () -> Void

    var body: some View {
        if let episode = player.episode {
            VStack(spacing: 0) {
                ProgressView(value: player.progress)
                    .progressViewStyle(.linear)
                    .tint(BrieflyColor.accent)
                    .frame(height: 2)
                    .accessibilityHidden(true)

                HStack(spacing: BrieflySpace.m) {
                    // The title area opens the full player. It is a tap target
                    // rather than a Button so it can sit beside the transport
                    // buttons without nesting controls inside a control.
                    HStack(spacing: BrieflySpace.m) {
                        Image(systemName: episode.episodeKind.systemImage)
                            .font(.footnote)
                            .foregroundStyle(BrieflyColor.accent)
                            .frame(width: 20)
                            .accessibilityHidden(true)

                        VStack(alignment: .leading, spacing: 1) {
                            Text(episode.title)
                                .font(BrieflyFont.label)
                                .foregroundStyle(BrieflyColor.ink)
                                .lineLimit(1)
                            Text(player.currentChapter?.displayTitle ?? episode.episodeKind.title)
                                .font(.caption2)
                                .foregroundStyle(BrieflyColor.inkMuted)
                                .lineLimit(1)
                        }
                        Spacer(minLength: 0)
                    }
                    .contentShape(Rectangle())
                    .onTapGesture(perform: onTap)
                    .accessibilityElement(children: .combine)
                    .accessibilityAddTraits(.isButton)
                    .accessibilityLabel("\(episode.title). Open player")

                    Button {
                        player.skipBackward()
                    } label: {
                        Image(systemName: "gobackward.15")
                            .font(.body)
                            .foregroundStyle(BrieflyColor.ink)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Skip back 15 seconds")

                    Button {
                        player.togglePlayPause()
                    } label: {
                        Image(systemName: player.isPlaying ? "pause.fill" : "play.fill")
                            .font(.title3)
                            .foregroundStyle(BrieflyColor.ink)
                            .frame(width: 30)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(player.isPlaying ? "Pause" : "Play")
                }
                .padding(.horizontal, BrieflySpace.l)
                .padding(.vertical, BrieflySpace.s)
            }
            .background(.ultraThinMaterial)
            .overlay(alignment: .top) { BrieflyRule() }
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }
}

/// The full-screen player: scrubber, transport, speed, chapters, transcript.
struct EpisodePlayerView: View {
    let episode: PodcastEpisode
    @Environment(AudioPlayerController.self) private var player
    @Environment(AppSettings.self) private var settings
    @Environment(\.dismiss) private var dismiss
    @State private var showTranscript = false

    private var isCurrent: Bool { player.isCurrent(episode) }
    private var displayDuration: Double {
        isCurrent && player.duration > 0 ? player.duration : Double(episode.durationSeconds)
    }
    private var displayTime: Double { isCurrent ? player.currentTime : 0 }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: BrieflySpace.xl) {
                    header
                    scrubber
                    transport
                    speedControl
                    if !episode.chapters.isEmpty { chapters }
                    if let transcript = episode.transcript, !transcript.isEmpty {
                        transcriptSection(transcript)
                    }
                    provenanceNote
                }
                .padding(.horizontal, BrieflySpace.pageMargin)
                .padding(.vertical, BrieflySpace.l)
            }
            .background(BrieflyColor.paper)
            .navigationTitle(episode.episodeKind.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .onAppear { player.rate = Float(settings.playbackRate) }
    }

    // MARK: - Sections

    private var header: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            Text(episode.editionDate.formatted(date: .complete, time: .omitted).uppercased())
                .font(BrieflyFont.label)
                .tracking(1.0)
                .foregroundStyle(BrieflyColor.inkMuted)
            Text(episode.title)
                .font(BrieflyFont.headline(.compact))
                .foregroundStyle(BrieflyColor.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let subtitle = episode.subtitle {
                Text(subtitle)
                    .font(BrieflyFont.caption)
                    .foregroundStyle(BrieflyColor.inkMuted)
            }
            HStack(spacing: BrieflySpace.s) {
                BrieflyChip(text: TimeFormatting.approximate(seconds: episode.durationSeconds),
                            systemImage: "clock")
                BrieflyChip(text: "\(episode.chapters.count) stories", systemImage: "list.bullet")
            }
            .padding(.top, BrieflySpace.xs)
        }
    }

    private var scrubber: some View {
        VStack(spacing: BrieflySpace.xs) {
            Slider(
                value: Binding(
                    get: { displayTime },
                    set: { player.updateScrub(to: $0) }
                ),
                in: 0...max(displayDuration, 1),
                onEditingChanged: { editing in
                    if editing { player.beginScrubbing() } else { player.endScrubbing() }
                }
            )
            .tint(BrieflyColor.accent)
            .disabled(!isCurrent)
            .accessibilityLabel("Playback position")
            .accessibilityValue(TimeFormatting.formatted(seconds: Int(displayTime)))

            HStack {
                Text(TimeFormatting.formatted(seconds: Int(displayTime)))
                Spacer()
                Text("−" + TimeFormatting.formatted(seconds: Int(max(0, displayDuration - displayTime))))
            }
            .font(BrieflyFont.mono)
            .foregroundStyle(BrieflyColor.inkMuted)
        }
    }

    private var transport: some View {
        HStack(spacing: BrieflySpace.xxl) {
            Spacer(minLength: 0)

            Button { player.skipBackward() } label: {
                Image(systemName: "gobackward.15").font(.title2)
            }
            .buttonStyle(.plain)
            .foregroundStyle(BrieflyColor.ink)
            .disabled(!isCurrent)
            .accessibilityLabel("Skip back 15 seconds")

            Button {
                if isCurrent {
                    player.togglePlayPause()
                } else {
                    player.load(episode)
                }
            } label: {
                ZStack {
                    Circle()
                        .fill(BrieflyColor.accent)
                        .frame(width: 68, height: 68)
                    if case .loading = player.state, isCurrent {
                        ProgressView().tint(BrieflyColor.paper)
                    } else {
                        Image(systemName: (isCurrent && player.isPlaying) ? "pause.fill" : "play.fill")
                            .font(.system(size: 26, weight: .semibold))
                            .foregroundStyle(BrieflyColor.paper)
                            .offset(x: (isCurrent && player.isPlaying) ? 0 : 2)
                    }
                }
            }
            .buttonStyle(.plain)
            .disabled(!episode.isPlayable)
            .accessibilityLabel(isCurrent && player.isPlaying ? "Pause" : "Play")

            Button { player.skipForward() } label: {
                Image(systemName: "goforward.30").font(.title2)
            }
            .buttonStyle(.plain)
            .foregroundStyle(BrieflyColor.ink)
            .disabled(!isCurrent)
            .accessibilityLabel("Skip forward 30 seconds")

            Spacer(minLength: 0)
        }
        .overlay(alignment: .center) {
            if case .failed(let message) = player.state, isCurrent {
                Text(message)
                    .font(BrieflyFont.caption)
                    .foregroundStyle(BrieflyColor.disputed)
                    .padding(.top, 90)
                    .multilineTextAlignment(.center)
            }
        }
    }

    private var speedControl: some View {
        HStack(spacing: BrieflySpace.s) {
            Text("Speed").brieflySectionHeader()
            Spacer(minLength: 0)
            ForEach([0.75, 1.0, 1.25, 1.5, 2.0], id: \.self) { speed in
                Button {
                    player.rate = Float(speed)
                    settings.playbackRate = speed
                } label: {
                    Text(speed == 1.0 ? "1×" : String(format: "%g×", speed))
                        .font(BrieflyFont.label)
                        .foregroundStyle(abs(Double(player.rate) - speed) < 0.01
                                         ? BrieflyColor.paper : BrieflyColor.ink)
                        .padding(.horizontal, BrieflySpace.s)
                        .padding(.vertical, 5)
                        .background(
                            RoundedRectangle(cornerRadius: BrieflyRadius.chip, style: .continuous)
                                .fill(abs(Double(player.rate) - speed) < 0.01
                                      ? BrieflyColor.accent : Color.clear)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: BrieflyRadius.chip, style: .continuous)
                                .strokeBorder(BrieflyColor.rule, lineWidth: 1)
                                .opacity(abs(Double(player.rate) - speed) < 0.01 ? 0 : 1)
                        )
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Play at \(String(format: "%g", speed)) times speed")
            }
        }
    }

    private var chapters: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            Text("In this episode").brieflySectionHeader()
            VStack(spacing: 0) {
                ForEach(Array(episode.chapters.enumerated()), id: \.element.id) { index, chapter in
                    Button {
                        if !isCurrent { player.load(episode, autoplay: false) }
                        player.seek(toChapter: chapter)
                    } label: {
                        HStack(spacing: BrieflySpace.m) {
                            Text(chapter.startText)
                                .font(BrieflyFont.mono)
                                .foregroundStyle(BrieflyColor.inkFaint)
                                .frame(width: 44, alignment: .leading)
                            Text(chapter.displayTitle)
                                .font(BrieflyFont.body)
                                .foregroundStyle(
                                    player.currentChapter?.id == chapter.id && isCurrent
                                        ? BrieflyColor.accent : BrieflyColor.ink
                                )
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 0)
                        }
                        .padding(.vertical, BrieflySpace.m)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    if index < episode.chapters.count - 1 { BrieflyRule(opacity: 0.6) }
                }
            }
        }
    }

    private func transcriptSection(_ transcript: String) -> some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            Button {
                withAnimation(BrieflyMotion.subtle) { showTranscript.toggle() }
            } label: {
                HStack {
                    Text("Transcript").brieflySectionHeader()
                    Spacer(minLength: 0)
                    Image(systemName: showTranscript ? "chevron.up" : "chevron.down")
                        .font(.caption2)
                        .foregroundStyle(BrieflyColor.inkFaint)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if showTranscript {
                Text(transcript)
                    .font(BrieflyFont.body)
                    .foregroundStyle(BrieflyColor.ink.opacity(0.9))
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
        }
    }

    private var provenanceNote: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            BrieflyRule()
            Text(
                "This briefing was written from the same extracted facts as the story "
                + "cards, not read from publishers' articles. Every story it covers is in "
                + "the app with its full source list."
            )
            .font(.caption2)
            .foregroundStyle(BrieflyColor.inkFaint)
            .fixedSize(horizontal: false, vertical: true)
        }
    }
}
