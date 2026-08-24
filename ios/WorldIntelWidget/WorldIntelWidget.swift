import WidgetKit
import SwiftUI
import Foundation

// ---------------------------------------------------------------------------
// World Intelligence — Home Screen widget.
//
// The widget is fully self-contained: it fetches the same core news feeds the
// app uses (no App Group / shared container needed, so there's zero setup and
// nothing to break on device). WidgetKit refreshes it periodically and the
// fetch is tiny (3 feeds), so it costs essentially no battery.
// ---------------------------------------------------------------------------

struct WidgetStory: Identifiable {
    let id: String
    let title: String
    let source: String
    let url: String?
    let published: Int
}

enum WidgetFetcher {
    /// The same core feeds the app's background refresh uses.
    static let coreFeeds: [(name: String, url: String)] = [
        ("Google News", "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"),
        ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ]

    static func stories() async -> [WidgetStory] {
        var all: [WidgetStory] = []
        for feed in coreFeeds {
            guard let url = URL(string: feed.url) else { continue }
            do {
                let (data, _) = try await URLSession.shared.data(from: url)
                let items = try RSSParser().parse(data: data)
                for it in items {
                    guard let title = it.title?.trimmingCharacters(in: .whitespacesAndNewlines),
                          !title.isEmpty else { continue }
                    all.append(WidgetStory(id: it.link ?? title, title: title,
                                           source: feed.name, url: it.link,
                                           published: Int(it.date ?? 0)))
                }
            } catch {
                // One feed failing shouldn't blank the widget.
                continue
            }
        }
        // Dedupe by normalized title, newest first, top 5.
        var seen = Set<String>()
        var out: [WidgetStory] = []
        for s in all.sorted(by: { $0.published > $1.published }) {
            guard seen.insert(s.title.lowercased()).inserted else { continue }
            out.append(s)
            if out.count >= 5 { break }
        }
        return out
    }
}

// MARK: - Timeline

struct WidgetEntry: TimelineEntry {
    let date: Date
    let stories: [WidgetStory]
    let failed: Bool
}

struct Provider: TimelineProvider {
    func placeholder(in context: Context) -> WidgetEntry {
        WidgetEntry(date: Date(), stories: [], failed: false)
    }

    func getSnapshot(in context: Context, completion: @escaping (WidgetEntry) -> Void) {
        completion(WidgetEntry(date: Date(), stories: [], failed: false))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<WidgetEntry>) -> Void) {
        Task {
            let stories = await WidgetFetcher.stories()
            let entry = WidgetEntry(date: Date(), stories: stories, failed: stories.isEmpty)
            // Refresh roughly every 20 minutes; WidgetKit also refreshes
            // opportunistically when the system wakes the phone.
            let next = Calendar.current.date(byAdding: .minute, value: 20, to: Date())
                ?? Date().addingTimeInterval(1200)
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }
}

// MARK: - View

struct WorldIntelWidgetEntryView: View {
    @Environment(\.widgetFamily) private var family
    var entry: WidgetEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("🌍 World Intelligence")
                    .font(.caption).bold().foregroundColor(.white)
                Spacer()
                Text(timeText).font(.caption2).foregroundColor(.gray)
            }
            if entry.stories.isEmpty {
                Spacer()
                Text(entry.failed ? "Can't reach the news right now — check back soon."
                                  : "Loading headlines…")
                    .font(.caption).foregroundColor(.gray)
                Spacer()
            } else {
                ForEach(entry.stories.prefix(family == .systemSmall ? 3 : 4)) { s in
                    VStack(alignment: .leading, spacing: 1) {
                        Text(s.title)
                            .font(family == .systemSmall ? .caption : .footnote)
                            .lineLimit(2).foregroundColor(.white)
                            .multilineTextAlignment(.leading)
                        Text("\(s.source) · \(ago(s.published))")
                            .font(.caption2).foregroundColor(.gray)
                    }
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(
            LinearGradient(colors: [Color(red: 0.07, green: 0.10, blue: 0.18),
                                    Color(red: 0.13, green: 0.18, blue: 0.30)],
                           startPoint: .top, endPoint: .bottom)
        )
        .widgetURL(entry.stories.first.flatMap { $0.url.flatMap { URL(string: $0) } })
    }

    private var timeText: String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f.string(from: entry.date)
    }

    private func ago(_ ms: Int) -> String {
        guard ms > 0 else { return "—" }
        let d = Date(timeIntervalSince1970: Double(ms) / 1000)
        let m = max(0, Int(Date().timeIntervalSince(d) / 60))
        if m < 1 { return "now" }
        if m < 60 { return "\(m)m" }
        return "\(m / 60)h"
    }
}

// MARK: - Widget declaration

struct WorldIntelWidget: Widget {
    let kind = "WorldIntelWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: Provider()) { entry in
            WorldIntelWidgetEntryView(entry: entry)
        }
        .configurationDisplayName("World Intelligence")
        .description("Top world headlines, refreshed automatically.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

@main
struct WorldIntelWidgetBundle: WidgetBundle {
    var body: some Widget {
        WorldIntelWidget()
    }
}
