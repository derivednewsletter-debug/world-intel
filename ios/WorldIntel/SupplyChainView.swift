import SwiftUI
import Combine

@MainActor
final class SupplyChainModel: ObservableObject {
    @Published var events: [WorldEvent] = []
    @Published var loading = false

    func load() async {
        if let cached = CacheStore.shared.load([WorldEvent].self, key: "supplychain") {
            events = cached
        }
        if let age = CacheStore.shared.age(of: "supplychain"), age < TTL.news { return }
        await refreshNow()
    }

    /// Unconditional refresh — called by the 30s foreground tick.
    func refreshNow() async {
        loading = true
        let fresh = await APIClient.shared.rssEvents(feeds: SourceFeeds.supply)
        let deduped = SourceFeeds.dedupe(fresh)
        events = deduped
        CacheStore.shared.save(deduped, key: "supplychain")
        NotificationManager.shared.checkAndNotify(events: deduped)
        loading = false
    }
}

struct SupplyChainView: View {
    @StateObject private var model = SupplyChainModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("Live tracking of port congestion, freight rates, shipping disruptions and trade chokepoints (Suez, Panama, Red Sea).")
                    .font(.caption)
                    .foregroundColor(.appMuted)
                FreshnessLabel(key: "supplychain")
                if model.loading && model.events.isEmpty {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 30)
                }
                ForEach(model.events) { event in
                    EventRow(event: event)
                }
                if model.events.isEmpty && !model.loading {
                    EmptyState(text: "No supply-chain alerts right now.")
                }
            }
            .padding(12)
        }
        .background(Color.appBg)
        .navigationTitle("Supply Chain")
        .task { await model.load() }
        .refreshable { await model.refreshNow() }
        .onReceive(NotificationCenter.default.publisher(for: .dataTick)) { _ in
            Task { await model.refreshNow() }
        }
    }
}
