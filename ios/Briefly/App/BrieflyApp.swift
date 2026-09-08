import SwiftUI

@main
@MainActor
struct BrieflyApp: App {
    @State private var appEnvironment: AppEnvironment

    init() {
        let settings = AppSettings()
        _appEnvironment = State(initialValue: AppEnvironment(settings: settings))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appEnvironment)
                .environment(appEnvironment.settings)
                .environment(appEnvironment.bookmarks)
                .environment(appEnvironment.player)
                .preferredColorScheme(appEnvironment.settings.appearance.colorScheme)
                .tint(BrieflyColor.accent)
        }
    }
}
