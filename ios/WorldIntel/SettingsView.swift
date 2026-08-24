import SwiftUI

struct SettingsView: View {
    @AppStorage("refreshOnOpen") private var refreshOnOpen = true
    @AppStorage("backgroundRefreshEnabled") private var backgroundRefreshEnabled = true
    @AppStorage("notificationsEnabled") private var notificationsEnabled = true
    @AppStorage("pushEnabled") private var pushEnabled = false
    @AppStorage("pushServerURL") private var pushServerURL = ""
    @State private var cacheSize = ""

    private func freshness(_ key: String) -> String {
        guard let age = CacheStore.shared.age(of: key) else { return "never" }
        let m = Int(age / 60)
        if m < 1 { return "just now" }
        if m < 60 { return "\(m)m ago" }
        return "\(m / 60)h ago"
    }

    var body: some View {
        Form {
            Section("AI Briefing") {
                Text("The Briefing tab is generated on-device from cached headlines — clustering, trend detection and watchlist alerts. No network, no battery cost.")
                    .font(.caption)
                    .foregroundColor(.appMuted)
            }

            Section("Notifications") {
                Toggle("Alerts for major events", isOn: $notificationsEnabled)
                    .onChange(of: notificationsEnabled) { _, on in
                        if on { NotificationManager.shared.requestPermissionIfNeeded() }
                    }
                Text("When you open the app, if something major (severity 4-5) happened since your last visit, you get an instant alert. Fires only while the app is open — zero background cost.")
                    .font(.caption)
                    .foregroundColor(.appMuted)

                Toggle("Real push notifications (beta)", isOn: $pushEnabled)
                    .onChange(of: pushEnabled) { _, on in
                        if on {
                            NotificationManager.shared.enableRemotePush()
                        }
                    }
                TextField("Local server URL (e.g. http://192.168.1.5:4173)", text: $pushServerURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                Text("Point this at the dashboard on your Mac (same Wi-Fi) to unlock richer data — the full aggregated feed, live FRED indicators, satellite fires and the AI world summary. Real push needs APNs configured (paid account, see README). Leave empty for fully standalone mode.")
                    .font(.caption)
                    .foregroundColor(.appMuted)
            }

            Section("Refresh behavior") {
                Toggle("Live refresh while open (every 30s)", isOn: $refreshOnOpen)
                Text("While the app is open, everything updates every 30 seconds.")
                    .font(.caption)
                    .foregroundColor(.appMuted)

                Toggle("Background refresh (best-effort)", isOn: $backgroundRefreshEnabled)
                    .onChange(of: backgroundRefreshEnabled) { _, on in
                        if on { BackgroundRefresh.schedule() } else { BackgroundRefresh.cancel() }
                    }
                Text("iOS decides when background refreshes run — usually every 15-30 minutes, more often on Wi-Fi/charging. This is the platform's maximum for a free Apple ID; the system manages the schedule so battery impact stays minimal.")
                    .font(.caption)
                    .foregroundColor(.appMuted)
            }

            Section("Cache") {
                HStack {
                    Text("Stored data")
                    Spacer()
                    Text(cacheSize.isEmpty ? "—" : cacheSize).foregroundColor(.appMuted)
                }
                Button("Clear cache") {
                    CacheStore.shared.clearAll()
                    cacheSize = "cleared"
                }
            }

            Section("Cache freshness") {
                let items: [(String, String)] = [
                    ("Live feed", "feed"),
                    ("Disasters", "disasters"),
                    ("Supply chain", "supplychain"),
                    ("Markets", "markets"),
                    ("World map", "map"),
                ]
                ForEach(items, id: \.1) { name, key in
                    HStack {
                        Text(name)
                        Spacer()
                        Text(freshness(key)).foregroundColor(.appMuted)
                    }
                }
            }

            Section("Sources") {
                Text("RSS: Google News, BBC, Al Jazeera, Reuters, AP, CNN, Bloomberg, FT")
                Text("Disasters: NASA EONET, USGS, GDACS, NASA FIRMS fires")
                Text("Events & map: GDELT")
                Text("All sources are free, keyless APIs — the app runs fully standalone.")
                    .font(.caption)
                    .foregroundColor(.appMuted)
            }

            Section("About") {
                Text("World Intelligence v1.3")
                Text("Personal intelligence dashboard with an on-device AI briefing engine, 30s live refresh, and best-effort background updates. No tracking, no ads, no server dependency.")
                    .font(.caption)
                    .foregroundColor(.appMuted)
            }
        }
        .navigationTitle("Settings")
        .onAppear {
            let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
            let cache = dir.appendingPathComponent("WorldIntelCache", isDirectory: true)
            if let size = try? FileManager.default.attributesOfItem(atPath: cache.path)[.size] as? NSNumber {
                cacheSize = String(format: "%.1f MB", size.doubleValue / 1_048_576)
            } else {
                cacheSize = "0 KB"
            }
        }
    }
}
