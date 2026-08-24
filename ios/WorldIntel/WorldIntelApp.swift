import SwiftUI
import Combine
import BackgroundTasks

extension Notification.Name {
    static let appBecameActive = Notification.Name("appBecameActive")
    /// Fired every 30s while the app is in the foreground — views refresh on this.
    static let dataTick = Notification.Name("dataTick")
}

/// Handles APNs registration (real push, requires paid account) and the
/// best-effort background refresh task (free account).
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        BackgroundRefresh.register()
        return true
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        BackgroundRefresh.schedule()
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        guard UserDefaults.standard.bool(forKey: "pushEnabled"),
              let base = UserDefaults.standard.string(forKey: "pushServerURL"), !base.isEmpty,
              let url = URL(string: base.hasSuffix("/") ? base : base + "/")?.appendingPathComponent("api/push/register")
        else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["token": token])
        URLSession.shared.dataTask(with: req).resume()
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {}
}

@main
struct WorldIntelApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .preferredColorScheme(.dark)
                .onAppear {
                    NotificationManager.shared.requestPermissionIfNeeded()
                }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active && UserDefaults.standard.bool(forKey: "refreshOnOpen") {
                        NotificationCenter.default.post(name: .appBecameActive, object: nil)
                    }
                    if phase == .background {
                        BackgroundRefresh.schedule()
                    }
                }
        }
    }
}

struct RootView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var tab: Tab = .briefing

    enum Tab: Hashable {
        case briefing, live, map, disasters, supplyChain, markets, watch, search, settings
    }

    var body: some View {
        TabView(selection: $tab) {
            NavigationStack { BriefingView() }
                .tabItem { Label("Briefing", systemImage: "brain.head.profile") }
                .tag(Tab.briefing)

            NavigationStack { FeedView().navigationTitle("Live Feed") }
                .tabItem { Label("Live", systemImage: "bolt.fill") }
                .tag(Tab.live)

            NavigationStack { MapView().navigationTitle("World Map") }
                .tabItem { Label("Map", systemImage: "globe") }
                .tag(Tab.map)

            NavigationStack { DisastersView() }
                .tabItem { Label("Disasters", systemImage: "flame.fill") }
                .tag(Tab.disasters)

            NavigationStack { SupplyChainView() }
                .tabItem { Label("Supply Chain", systemImage: "shippingbox.fill") }
                .tag(Tab.supplyChain)

            NavigationStack { MarketsView() }
                .tabItem { Label("Markets", systemImage: "chart.line.uptrend.xyaxis") }
                .tag(Tab.markets)

            NavigationStack { WatchView() }
                .tabItem { Label("Watch", systemImage: "play.rectangle.fill") }
                .tag(Tab.watch)

            NavigationStack { SearchView() }
                .tabItem { Label("Search", systemImage: "magnifyingglass") }
                .tag(Tab.search)

            NavigationStack { SettingsView() }
                .tabItem { Label("Settings", systemImage: "gearshape.fill") }
                .tag(Tab.settings)
        }
        .tint(.appAccent)
        .onReceive(Timer.publish(every: 30, on: .main, in: .common).autoconnect()) { _ in
            // Foreground loop: everything refreshes every 30s while the app is open.
            guard scenePhase == .active else { return }
            NotificationCenter.default.post(name: .dataTick, object: nil)
        }
    }
}
