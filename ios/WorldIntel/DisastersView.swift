import SwiftUI
import Combine

@MainActor
final class DisastersModel: ObservableObject {
    @Published var events: [WorldEvent] = []
    @Published var loading = false

    func load() async {
        if let cached = CacheStore.shared.load([WorldEvent].self, key: "disasters") {
            events = cached
        }
        if let age = CacheStore.shared.age(of: "disasters"), age < TTL.disasters { return }
        await refreshNow()
    }

    /// Unconditional refresh — called by the 30s foreground tick.
    func refreshNow() async {
        loading = true
        var deduped: [WorldEvent] = []
        if let base = AppServer.baseURL {
            // Local-backend mode: includes NASA FIRMS satellite fires + NOAA weather.
            deduped = await APIClient.shared.serverDisasters(base: base)
        } else {
            async let eonet = APIClient.shared.eonetEvents()
            async let usgs = APIClient.shared.usgsEvents()
            async let gdacs = APIClient.shared.gdacsEvents()
            let all = await [eonet, usgs, gdacs].flatMap { $0 }
            deduped = SourceFeeds.dedupe(all)
        }
        events = deduped
        CacheStore.shared.save(deduped, key: "disasters")
        NotificationManager.shared.checkAndNotify(events: deduped)
        loading = false
    }
}

struct DisastersView: View {
    @StateObject private var model = DisastersModel()

    private var counts: [String: Int] {
        model.events.reduce(into: [:]) { acc, e in acc[e.source, default: 0] += 1 }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    StatCard(value: "\(model.events.count)", label: "Active alerts")
                    StatCard(value: "\(counts["usgs"] ?? 0)", label: "Quakes 24h")
                    StatCard(value: "\(counts["gdacs"] ?? 0)", label: "GDACS alerts")
                }
                FreshnessLabel(key: "disasters")
                if model.loading && model.events.isEmpty {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 30)
                }
                ForEach(model.events) { event in
                    EventRow(event: event)
                }
            }
            .padding(12)
        }
        .background(Color.appBg)
        .navigationTitle("Disasters")
        .task { await model.load() }
        .refreshable { await model.refreshNow() }
        .onReceive(NotificationCenter.default.publisher(for: .dataTick)) { note in
            guard note.object as? String == "disasters" else { return }
            Task { await model.refreshNow() }
        }
    }
}
