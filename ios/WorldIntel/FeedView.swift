import SwiftUI
import Combine

@MainActor
final class FeedModel: ObservableObject {
    @Published var events: [WorldEvent] = []
    @Published var loading = false

    func load() async {
        if let cached = CacheStore.shared.load([WorldEvent].self, key: "feed") {
            events = cached
        }
        if let age = CacheStore.shared.age(of: "feed"), age < TTL.news { return }
        await refreshNow()
    }

    /// Unconditional refresh — called by the 30s foreground tick.
    func refreshNow() async {
        loading = true
        var fresh: [WorldEvent] = []
        if let base = AppServer.baseURL {
            // Local-backend mode: the full aggregated feed (all sources, deduped).
            fresh = await APIClient.shared.serverEvents(base: base, query: [URLQueryItem(name: "limit", value: "100")])
        } else {
            fresh = await APIClient.shared.rssEvents(feeds: SourceFeeds.newsAll)
        }
        let deduped = SourceFeeds.dedupe(fresh)
        events = deduped
        CacheStore.shared.save(deduped, key: "feed")
        NotificationManager.shared.checkAndNotify(events: deduped)
        loading = false
    }
}

struct FeedView: View {
    @StateObject private var model = FeedModel()
    @State private var selected = Set<Category>()
    @State private var majorOnly = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    categoryChips
                    Button(majorOnly ? "Major only ✓" : "Major only") { majorOnly.toggle() }
                        .font(.caption).bold()
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .background(majorOnly ? Color.appErr.opacity(0.2) : Color.appPanel)
                        .foregroundColor(majorOnly ? .appErr : .appMuted)
                        .clipShape(Capsule())
                        .overlay(Capsule().stroke(Color.appBorder, lineWidth: 1))
                        .buttonStyle(.plain)
                }
                FreshnessLabel(key: "feed")
                if model.loading && model.events.isEmpty {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 30)
                }
                if model.events.isEmpty && !model.loading {
                    EmptyState(text: "No events yet — pull to refresh.")
                }
                ForEach(filtered) { event in
                    EventRow(event: event)
                }
            }
            .padding(12)
        }
        .background(Color.appBg)
        .task { await model.load() }
        .refreshable { await model.refreshNow() }
        .onReceive(NotificationCenter.default.publisher(for: .appBecameActive)) { _ in
            Task { await model.refreshNow() }
        }
        .onReceive(NotificationCenter.default.publisher(for: .dataTick)) { note in
            guard note.object as? String == "live" else { return }
            Task { await model.refreshNow() }
        }
    }

    private var filtered: [WorldEvent] {
        var list = selected.isEmpty ? model.events : model.events.filter { selected.contains($0.category) }
        if majorOnly { list = list.filter { $0.severity >= 3 } }
        return list
    }

    private var categoryChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                chip("All", isOn: selected.isEmpty) {
                    selected = []
                }
                ForEach(Category.allCases) { c in
                    chip(c.label, isOn: selected.contains(c)) {
                        if selected.contains(c) { selected.remove(c) } else { selected.insert(c) }
                    }
                }
            }
            .padding(.vertical, 2)
        }
    }

    private func chip(_ label: String, isOn: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.caption)
                .padding(.horizontal, 10).padding(.vertical, 5)
                .background(isOn ? Color.appPanel2 : Color.appPanel)
                .foregroundColor(isOn ? .appText : .appMuted)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(isOn ? Color.appAccent : Color.appBorder, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}
