import SwiftUI
import Combine

@MainActor
final class SearchModel: ObservableObject {
    @Published var query = ""
    @Published var results: [WorldEvent] = []
    private var debounceTask: Task<Void, Never>?

    /// Debounced search-as-you-type — fires 350ms after the user stops typing.
    func queryChanged() {
        debounceTask?.cancel()
        debounceTask = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: 350_000_000)
                guard !Task.isCancelled else { return }
                self?.search()
            } catch { return }
        }
    }

    /// Searches everything currently cached on device — instant and free.
    func search() {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { results = []; return }

        var all: [WorldEvent] = []
        for key in ["feed", "disasters", "supplychain", "markets", "map"] {
            if let cached = CacheStore.shared.load([WorldEvent].self, key: key) { all += cached }
        }
        let pool = SourceFeeds.dedupe(all)
        results = pool.filter {
            $0.title.lowercased().contains(q) ||
            ($0.summary ?? "").lowercased().contains(q) ||
            $0.source.lowercased().contains(q) ||
            ($0.geo?.place ?? "").lowercased().contains(q)
        }
        .sorted { $0.published > $1.published }
    }
}

struct SearchView: View {
    @StateObject private var model = SearchModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                TextField("Search headlines, places, sources…", text: $model.query)
                    .textFieldStyle(.roundedBorder)
                    .padding(.horizontal, 2)
                    .onChange(of: model.query) { _, _ in model.queryChanged() }
                    .onSubmit { model.search() }
                Button("Search") { model.search() }
                    .buttonStyle(.borderedProminent)
                    .tint(.appAccent)
                    .frame(maxWidth: .infinity)

                Text("Searches everything already loaded on your phone — no extra data cost.")
                    .font(.caption)
                    .foregroundColor(.appMuted)

                if !model.query.isEmpty && model.results.isEmpty {
                    EmptyState(text: "No matches in cached data. Pull to refresh other tabs first, then search again.")
                }
                ForEach(model.results) { event in
                    EventRow(event: event)
                }
            }
            .padding(12)
        }
        .background(Color.appBg)
        .navigationTitle("Search")
    }
}
