import SwiftUI

/// Tab 5.
struct SettingsView: View {
    @Environment(AppSettings.self) private var settings
    @Environment(BookmarkStore.self) private var bookmarks
    @Environment(AppEnvironment.self) private var appEnvironment

    @State private var serverURL: String = ""
    @State private var clientKey: String = ""
    @State private var showClearConfirmation = false
    @State private var saveNotice: String?

    var body: some View {
        @Bindable var settings = settings

        NavigationStack {
            Form {
                Section {
                    Picker("Appearance", selection: $settings.appearance) {
                        ForEach(AppearanceOption.allCases) { option in
                            Text(option.label).tag(option)
                        }
                    }
                    Toggle("Show confidence on cards", isOn: $settings.showConfidenceOnCards)
                    Toggle("Haptics", isOn: $settings.hapticsEnabled)
                } header: {
                    Text("Reading")
                } footer: {
                    Text("The confidence chip says whether a story is corroborated, "
                         + "contested, or reported by a single outlet.")
                }

                Section {
                    Toggle("Keep playing in the background", isOn: $settings.backgroundAudioEnabled)
                        .onChange(of: settings.backgroundAudioEnabled) { _, value in
                            appEnvironment.player.setBackgroundAudio(value)
                        }
                    HStack {
                        Text("Default speed")
                        Spacer()
                        Text(String(format: "%g×", settings.playbackRate))
                            .foregroundStyle(BrieflyColor.inkMuted)
                    }
                } header: {
                    Text("Audio")
                }

                Section {
                    TextField("https://briefly.example.com", text: $serverURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    SecureField("Client key (optional)", text: $clientKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Button("Save server") { saveServer() }
                        .disabled(serverURL.trimmingCharacters(in: .whitespaces).isEmpty)

                    if appEnvironment.settings.apiConfiguration.isConfigured {
                        Button("Use sample stories instead", role: .destructive) {
                            settings.clearServer()
                            appEnvironment.rebuildRepository()
                            serverURL = ""
                            clientKey = ""
                            saveNotice = "Now showing the bundled sample stories."
                        }
                    }

                    if let saveNotice {
                        Text(saveNotice)
                            .font(BrieflyFont.caption)
                            .foregroundStyle(BrieflyColor.accent)
                    }
                } header: {
                    Text("Briefly server")
                } footer: {
                    Text("Point the app at your own Briefly backend. Without one it shows a "
                         + "bundled set of sample stories, clearly marked as samples. "
                         + "No AI, text-to-speech or database credential is ever stored in "
                         + "the app — those live only on your server.")
                }

                Section {
                    HStack {
                        Text("Saved stories")
                        Spacer()
                        Text("\(bookmarks.count)").foregroundStyle(BrieflyColor.inkMuted)
                    }
                    Button("Clear saved stories", role: .destructive) {
                        showClearConfirmation = true
                    }
                    .disabled(bookmarks.isEmpty)
                } header: {
                    Text("Storage")
                } footer: {
                    Text("Saved stories are kept on this device only.")
                }

                Section {
                    NavigationLink("How Briefly works") { AboutView() }
                    NavigationLink("Editorial standards") { EditorialStandardsView() }
                    HStack {
                        Text("Version")
                        Spacer()
                        Text(Bundle.main.shortVersionString).foregroundStyle(BrieflyColor.inkMuted)
                    }
                } header: {
                    Text("About")
                }
            }
            .scrollContentBackground(.hidden)
            .background(BrieflyColor.paper)
            .navigationTitle("Settings")
            .confirmationDialog(
                "Remove all saved stories?",
                isPresented: $showClearConfirmation,
                titleVisibility: .visible
            ) {
                Button("Remove all", role: .destructive) { bookmarks.removeAll() }
                Button("Cancel", role: .cancel) {}
            }
            .onAppear {
                serverURL = settings.apiConfiguration.baseURL?.absoluteString ?? ""
                clientKey = settings.apiConfiguration.clientKey ?? ""
            }
        }
    }

    private func saveServer() {
        settings.updateServer(baseURL: serverURL, clientKey: clientKey)
        appEnvironment.rebuildRepository()
        saveNotice = settings.apiConfiguration.isConfigured
            ? "Saved. Pull to refresh the feed."
            : "That doesn't look like a valid address."
    }
}

extension Bundle {
    var shortVersionString: String {
        let version = object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
        let build = object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "1"
        return "\(version) (\(build))"
    }
}
