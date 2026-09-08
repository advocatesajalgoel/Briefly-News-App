import AVFoundation
import Combine
import Foundation
import MediaPlayer
import Observation

/// Holds `NotificationCenter` tokens so they can be removed when the controller
/// goes away.
///
/// This exists because a `@MainActor` type cannot safely touch its own isolated
/// state from `deinit`. `NotificationCenter.removeObserver` is thread-safe, so a
/// plain box with its own deinit is both correct and simpler than trying to hop
/// actors during deallocation.
private final class NotificationTokenBox: @unchecked Sendable {
    private var tokens: [NSObjectProtocol] = []

    func add(_ token: NSObjectProtocol) { tokens.append(token) }

    func removeAll() {
        tokens.forEach { NotificationCenter.default.removeObserver($0) }
        tokens.removeAll()
    }

    deinit { removeAll() }
}

/// Playback for Briefly's audio briefings.
///
/// Wraps `AVPlayer` with the things a podcast player actually has to get right:
/// an audio session configured for background playback, lock-screen and Control
/// Centre controls, a time observer that survives seeking, and correct behaviour
/// when the route changes or another app interrupts.
@MainActor
@Observable
final class AudioPlayerController {
    enum PlaybackState: Equatable {
        case idle
        case loading
        case playing
        case paused
        case finished
        case failed(String)
    }

    private(set) var state: PlaybackState = .idle
    private(set) var episode: PodcastEpisode?
    private(set) var currentTime: Double = 0
    private(set) var duration: Double = 0
    private(set) var isSeeking = false

    var rate: Float = 1.0 {
        didSet {
            guard case .playing = state else { return }
            player?.rate = rate
            updateNowPlayingInfo()
        }
    }

    /// Seconds the skip buttons move. Matches the system podcast conventions.
    let skipForwardInterval: Double = 30
    let skipBackwardInterval: Double = 15

    private var player: AVPlayer?
    private var timeObserver: Any?
    private var itemObservations: [NSKeyValueObservation] = []
    private var endObserver: NSObjectProtocol?
    private let sessionTokens = NotificationTokenBox()
    private var observingSession = false
    private var wasPlayingBeforeInterruption = false
    private var commandsConfigured = false
    private var backgroundAudioEnabled = true

    // MARK: - Derived

    var progress: Double {
        guard duration > 0 else { return 0 }
        return min(1, max(0, currentTime / duration))
    }

    var isPlaying: Bool { state == .playing }

    var currentTimeText: String { TimeFormatting.formatted(seconds: Int(currentTime)) }
    var remainingTimeText: String { "−" + TimeFormatting.formatted(seconds: Int(max(0, duration - currentTime))) }
    var durationText: String { TimeFormatting.formatted(seconds: Int(duration)) }

    /// The chapter the playhead is inside, so the UI can show what is being read.
    var currentChapter: EpisodeSegment? {
        guard let episode else { return nil }
        return episode.segments
            .filter { Double($0.startOffsetSeconds) <= currentTime + 0.5 }
            .max { $0.startOffsetSeconds < $1.startOffsetSeconds }
    }

    func isCurrent(_ candidate: PodcastEpisode) -> Bool { episode?.id == candidate.id }

    // MARK: - Lifecycle

    init(backgroundAudioEnabled: Bool = true) {
        self.backgroundAudioEnabled = backgroundAudioEnabled
    }

    func setBackgroundAudio(_ enabled: Bool) {
        backgroundAudioEnabled = enabled
        configureAudioSession()
    }

    // MARK: - Loading

    func load(_ episode: PodcastEpisode, autoplay: Bool = true) {
        guard let url = episode.audioURL else {
            state = .failed("This episode has no audio yet.")
            return
        }
        if self.episode?.id == episode.id, player != nil {
            if autoplay { play() }
            return
        }

        teardownPlayer()
        self.episode = episode
        state = .loading
        currentTime = 0
        duration = Double(episode.durationSeconds)

        configureAudioSession()

        let item = AVPlayerItem(url: url)
        let player = AVPlayer(playerItem: item)
        player.automaticallyWaitsToMinimizeStalling = true
        self.player = player

        observe(item: item)
        addTimeObserver(to: player)
        configureRemoteCommands()
        updateNowPlayingInfo()

        if autoplay { play() }
    }

    // MARK: - Transport

    func play() {
        guard let player else { return }
        configureAudioSession()
        player.rate = rate
        state = .playing
        updateNowPlayingInfo()
    }

    func pause() {
        player?.pause()
        if state == .playing { state = .paused }
        updateNowPlayingInfo()
    }

    func togglePlayPause() {
        switch state {
        case .playing:  pause()
        case .finished: seek(to: 0); play()
        default:        play()
        }
    }

    func stop() {
        teardownPlayer()
        episode = nil
        state = .idle
        currentTime = 0
        duration = 0
        clearNowPlayingInfo()
        deactivateAudioSession()
    }

    func seek(to seconds: Double) {
        guard let player else { return }
        let target = min(max(0, seconds), max(duration, 0))
        currentTime = target
        let time = CMTime(seconds: target, preferredTimescale: 600)
        player.seek(to: time, toleranceBefore: .zero, toleranceAfter: .zero) { [weak self] _ in
            Task { @MainActor in
                self?.updateNowPlayingInfo()
                if self?.state == .finished, target < (self?.duration ?? 0) - 1 {
                    self?.state = .paused
                }
            }
        }
    }

    func skipForward() { seek(to: currentTime + skipForwardInterval) }
    func skipBackward() { seek(to: max(0, currentTime - skipBackwardInterval)) }

    func seek(toChapter segment: EpisodeSegment) {
        seek(to: Double(segment.startOffsetSeconds))
        if state != .playing { play() }
    }

    /// Called while the reader drags the scrubber, so the time label tracks the
    /// thumb without seeking on every frame.
    func beginScrubbing() { isSeeking = true }

    func updateScrub(to seconds: Double) {
        guard isSeeking else { return }
        currentTime = min(max(0, seconds), max(duration, 0))
    }

    func endScrubbing() {
        isSeeking = false
        seek(to: currentTime)
    }

    // MARK: - AVPlayer plumbing

    private func observe(item: AVPlayerItem) {
        // KVO callbacks arrive on an arbitrary queue and `AVPlayerItem` is not
        // `Sendable`, so each handler reads the primitive values it needs first
        // and only those cross onto the main actor.
        itemObservations = [
            item.observe(\.status, options: [.new]) { [weak self] item, _ in
                let status = item.status
                let seconds = item.duration.seconds
                let failure = item.error?.localizedDescription
                Task { @MainActor in
                    guard let self else { return }
                    switch status {
                    case .readyToPlay:
                        if seconds.isFinite, seconds > 0 { self.duration = seconds }
                        if self.state == .loading { self.state = .playing }
                        self.updateNowPlayingInfo()
                    case .failed:
                        let reason = failure ?? "The episode could not be played."
                        BrieflyLog.audio.error("player item failed: \(reason)")
                        self.state = .failed(reason)
                    default:
                        break
                    }
                }
            },
            item.observe(\.isPlaybackBufferEmpty, options: [.new]) { [weak self] item, _ in
                let isEmpty = item.isPlaybackBufferEmpty
                Task { @MainActor in
                    guard let self, self.state == .playing, isEmpty else { return }
                    self.state = .loading
                }
            },
            item.observe(\.isPlaybackLikelyToKeepUp, options: [.new]) { [weak self] item, _ in
                let keepUp = item.isPlaybackLikelyToKeepUp
                Task { @MainActor in
                    guard let self, self.state == .loading, keepUp else { return }
                    self.state = (self.player?.rate ?? 0) > 0 ? .playing : .paused
                }
            }
        ]

        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                self.state = .finished
                self.currentTime = self.duration
                self.updateNowPlayingInfo()
            }
        }

        observeInterruptions()
    }

    private func addTimeObserver(to player: AVPlayer) {
        let interval = CMTime(seconds: 0.25, preferredTimescale: 600)
        timeObserver = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) {
            [weak self] time in
            let seconds = time.seconds
            Task { @MainActor in
                guard let self, !self.isSeeking else { return }
                self.currentTime = seconds
                if self.duration <= 0,
                   let itemDuration = self.player?.currentItem?.duration.seconds,
                   itemDuration.isFinite, itemDuration > 0 {
                    self.duration = itemDuration
                }
                if (self.player?.rate ?? 0) > 0,
                   self.state == .paused || self.state == .loading {
                    self.state = .playing
                }
            }
        }
    }

    private func teardownPlayer() {
        if let timeObserver, let player {
            player.removeTimeObserver(timeObserver)
        }
        timeObserver = nil
        itemObservations.forEach { $0.invalidate() }
        itemObservations = []
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
        endObserver = nil
        player?.pause()
        player = nil
    }

    // MARK: - Audio session

    private func configureAudioSession() {
        #if os(iOS)
        do {
            let session = AVAudioSession.sharedInstance()
            // `.spokenAudio` tells the system this is speech: it ducks correctly
            // against navigation prompts and behaves properly in CarPlay.
            try session.setCategory(.playback, mode: .spokenAudio, options: [])
            try session.setActive(true)
        } catch {
            BrieflyLog.audio.error("audio session: \(String(describing: error))")
        }
        #endif
    }

    private func deactivateAudioSession() {
        #if os(iOS)
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
        #endif
    }

    private func observeInterruptions() {
        #if os(iOS)
        guard !observingSession else { return }
        observingSession = true

        sessionTokens.add(NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: AVAudioSession.sharedInstance(), queue: .main
        ) { [weak self] notification in
            let info = notification.userInfo
            let rawType = info?[AVAudioSessionInterruptionTypeKey] as? UInt
            let rawOptions = info?[AVAudioSessionInterruptionOptionKey] as? UInt
            Task { @MainActor in
                guard let self, let rawType,
                      let type = AVAudioSession.InterruptionType(rawValue: rawType) else { return }
                switch type {
                case .began:
                    self.wasPlayingBeforeInterruption = self.isPlaying
                    self.pause()
                case .ended:
                    let options = AVAudioSession.InterruptionOptions(rawValue: rawOptions ?? 0)
                    if options.contains(.shouldResume), self.wasPlayingBeforeInterruption {
                        self.play()
                    }
                @unknown default:
                    break
                }
            }
        })

        sessionTokens.add(NotificationCenter.default.addObserver(
            forName: AVAudioSession.routeChangeNotification,
            object: AVAudioSession.sharedInstance(), queue: .main
        ) { [weak self] notification in
            let rawReason = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
            Task { @MainActor in
                guard let rawReason,
                      let reason = AVAudioSession.RouteChangeReason(rawValue: rawReason) else { return }
                // Headphones pulled out: pause, exactly as every other audio app does.
                if reason == .oldDeviceUnavailable { self?.pause() }
            }
        })
        #endif
    }

    // MARK: - Now Playing / remote commands

    private func configureRemoteCommands() {
        guard !commandsConfigured else { return }
        commandsConfigured = true

        let center = MPRemoteCommandCenter.shared()

        center.playCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.play() }
            return .success
        }
        center.pauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.pause() }
            return .success
        }
        center.togglePlayPauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.togglePlayPause() }
            return .success
        }
        center.skipForwardCommand.preferredIntervals = [NSNumber(value: skipForwardInterval)]
        center.skipForwardCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.skipForward() }
            return .success
        }
        center.skipBackwardCommand.preferredIntervals = [NSNumber(value: skipBackwardInterval)]
        center.skipBackwardCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.skipBackward() }
            return .success
        }
        center.changePlaybackPositionCommand.addTarget { [weak self] event in
            guard let event = event as? MPChangePlaybackPositionCommandEvent else {
                return .commandFailed
            }
            Task { @MainActor in self?.seek(to: event.positionTime) }
            return .success
        }
    }

    private func updateNowPlayingInfo() {
        guard let episode else { return }
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: episode.title,
            MPMediaItemPropertyArtist: "Briefly",
            MPMediaItemPropertyAlbumTitle: episode.episodeKind.title,
            MPMediaItemPropertyPlaybackDuration: duration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: currentTime,
            MPNowPlayingInfoPropertyPlaybackRate: isPlaying ? Double(rate) : 0.0,
            MPNowPlayingInfoPropertyIsLiveStream: false
        ]
        if let chapter = currentChapter?.displayTitle {
            info[MPMediaItemPropertyAlbumTitle] = "\(episode.episodeKind.title) · \(chapter)"
        }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    private func clearNowPlayingInfo() {
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    }
}
