import SwiftUI
import Combine

@MainActor
final class BriefingModel: ObservableObject {
    @Published var briefing: Briefing?
    @Published var summary: WorldSummary?

    /// Prefers the local backend's richer AI when a server URL is set; otherwise
    /// computes on-device from cached events (zero network, zero battery).
    func load() async {
        if let base = AppServer.baseURL {
            async let br = APIClient.shared.serverBriefing(base: base)
            async let su = APIClient.shared.serverSummary(base: base)
            let (b, s) = await (br, su)
            if b != nil || s != nil {
                if let b { briefing = b }
                if let s { summary = s }
                return
            }
        }
        loadLocal()
    }

    /// Computed locally from cached events — no network, no battery cost.
    func loadLocal() {
        var all: [WorldEvent] = []
        for key in ["feed", "disasters", "supplychain", "markets", "map"] {
            if let cached = CacheStore.shared.load([WorldEvent].self, key: key) { all += cached }
        }
        let pool = SourceFeeds.dedupe(all)
        briefing = generateBriefing(events: pool, hours: 24)
        summary = generateWorldSummary(events: pool, hours: 24)
    }
}

struct BriefingView: View {
    @StateObject private var model = BriefingModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Your AI briefing — generated on-device from what's already loaded. No network, no battery cost.")
                    .font(.caption)
                    .foregroundColor(.appMuted)

                if let summary = model.summary {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 6) {
                            Image(systemName: "globe.americas")
                                .font(.caption2).foregroundColor(.appOk)
                            Text("WORLD SUMMARY").font(.caption2).bold().foregroundColor(.appOk)
                        }
                        Text(summary.opening).font(.subheadline).lineSpacing(3)
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(summary.categories) { c in
                                    Text("\(c.category.label): \(c.count)")
                                        .font(.caption)
                                        .padding(.horizontal, 10).padding(.vertical, 4)
                                        .background(Color(cv: c.category.color).opacity(0.15))
                                        .foregroundColor(Color(cv: c.category.color))
                                        .clipShape(Capsule())
                                }
                            }
                        }
                        ForEach(summary.regions) { region in
                            VStack(alignment: .leading, spacing: 3) {
                                HStack {
                                    Text(region.name).font(.subheadline).bold()
                                    Spacer()
                                    Text("\(region.count)").font(.subheadline).bold().foregroundColor(.appMuted)
                                }
                                ForEach(region.top) { item in
                                    Text(item.title).font(.caption).foregroundColor(.appMuted).lineLimit(1)
                                }
                            }
                            .padding(10)
                            .panel()
                        }
                    }
                    .padding(12)
                    .panel()
                }

                if let briefing = model.briefing {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 6) {
                            Image(systemName: "sparkles")
                                .font(.caption2).foregroundColor(.appAccent)
                            Text("AI HEADLINE").font(.caption2).bold().foregroundColor(.appAccent)
                        }
                        Text(briefing.headline).font(.title3).bold().lineSpacing(2)
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        LinearGradient(colors: [Color.appAccent.opacity(0.16), Color.appPanel],
                                       startPoint: .topLeading, endPoint: .bottomTrailing)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.appAccent.opacity(0.35), lineWidth: 1))

                    ForEach(briefing.sections) { section in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(section.title.uppercased())
                                .font(.caption).bold()
                                .foregroundColor(.appAccent)
                                .padding(.horizontal, 2)
                            ForEach(section.items) { item in
                                HStack(spacing: 10) {
                                    RoundedRectangle(cornerRadius: 2)
                                        .fill(severityColor(item.severity))
                                        .frame(width: 4)
                                    VStack(alignment: .leading, spacing: 2) {
                                        if let url = item.url, let u = URL(string: url) {
                                            Link(destination: u) {
                                                Text(item.title).fontWeight(.medium).multilineTextAlignment(.leading)
                                            }
                                        } else {
                                            Text(item.title).fontWeight(.medium).multilineTextAlignment(.leading)
                                        }
                                        Text(item.detail).font(.caption).foregroundColor(.appMuted)
                                    }
                                }
                                .padding(10)
                                .panel()
                            }
                        }
                    }
                } else {
                    EmptyState(text: "Open the other tabs first so the AI has news to brief you on.")
                }
            }
            .padding(12)
        }
        .background(Color.appBg)
        .navigationTitle("AI Briefing")
        .onAppear { Task { await model.load() } }
        .refreshable { await model.load() }
        .onReceive(NotificationCenter.default.publisher(for: .appBecameActive)) { _ in
            Task { await model.load() }
        }
        .onReceive(NotificationCenter.default.publisher(for: .dataTick)) { note in
            guard note.object as? String == "briefing" else { return }
            Task { await model.load() }
        }
    }
}
