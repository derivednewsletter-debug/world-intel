import SwiftUI
import Combine

@MainActor
final class MarketsModel: ObservableObject {
    @Published var events: [WorldEvent] = []
    @Published var indicators: [Indicator] = []
    @Published var loading = false

    func load() async {
        if let cached = CacheStore.shared.load([WorldEvent].self, key: "markets") {
            events = cached
        }
        if let cached = CacheStore.shared.load([Indicator].self, key: "indicators") {
            indicators = cached
        }
        // Standalone: keyless FX + crypto are always live, even on fresh cache.
        if AppServer.baseURL == nil {
            await refreshMoney()
        }
        if let age = CacheStore.shared.age(of: "markets"), age < TTL.news { return }
        await refreshNow()
    }

    private func refreshMoney() async {
        let money = await APIClient.shared.moneyIndicators()
        if !money.isEmpty {
            indicators = money
            CacheStore.shared.save(money, key: "indicators")
        }
    }

    /// Unconditional refresh — called by the 30s foreground tick.
    func refreshNow() async {
        loading = true
        if let base = AppServer.baseURL {
            // Local-backend mode: live FRED indicators + classified market news.
            let (inds, evs) = await APIClient.shared.serverMarketData(base: base)
            if !inds.isEmpty {
                indicators = inds
                CacheStore.shared.save(inds, key: "indicators")
            }
            if !evs.isEmpty {
                events = evs
                CacheStore.shared.save(evs, key: "markets")
            }
            loading = false
            return
        }
        let fresh = await APIClient.shared.rssEvents(feeds: SourceFeeds.markets)
        let deduped = SourceFeeds.dedupe(fresh)
        events = deduped
        CacheStore.shared.save(deduped, key: "markets")
        NotificationManager.shared.checkAndNotify(events: deduped)
        await refreshMoney()
        loading = false
    }
}

struct MarketsView: View {
    @StateObject private var model = MarketsModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if !model.indicators.isEmpty {
                    Text("LIVE MONEY & MARKETS")
                        .font(.caption2).bold()
                        .foregroundColor(.appAccent)
                        .padding(.horizontal, 12)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 10) {
                            ForEach(model.indicators) { ind in
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(ind.name)
                                        .font(.caption)
                                        .foregroundColor(.appMuted)
                                        .lineLimit(1)
                                    Text(ind.latest_value.map { String(format: "%.2f", $0) } ?? "—")
                                        .font(.title3).bold()
                                        .foregroundColor(.appText)
                                    Text(ind.latest_date.map { "as of " + $0 } ?? "")
                                        .font(.caption2)
                                        .foregroundColor(.appMuted)
                                }
                                .frame(width: 170, alignment: .leading)
                                .padding(10)
                                .panel()
                            }
                        }
                        .padding(.horizontal, 12)
                    }
                }
                Text("Market and energy headlines — set a Local server URL in Settings for live CPI, rates and oil.")
                    .font(.caption)
                    .foregroundColor(.appMuted)
                FreshnessLabel(key: "markets")
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
        .navigationTitle("Markets")
        .task { await model.load() }
        .refreshable { await model.refreshNow() }
        .onReceive(NotificationCenter.default.publisher(for: .dataTick)) { note in
            guard note.object as? String == "markets" else { return }
            Task { await model.refreshNow() }
        }
    }
}
