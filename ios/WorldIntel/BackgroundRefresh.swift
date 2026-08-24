import Foundation
import BackgroundTasks

/// All RSS feeds the app can fetch, grouped by purpose.
enum SourceFeeds {
    static let newsCore: [(name: String, url: String, category: Category)] = [
        ("google-news", "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en", .news),
        ("bbc-world", "https://feeds.bbci.co.uk/news/world/rss.xml", .news),
        ("aljazeera", "https://www.aljazeera.com/xml/rss/all.xml", .news),
    ]

    static let newsAll: [(name: String, url: String, category: Category)] = newsCore + [
        ("gn-conflict", "https://news.google.com/rss/search?q=war%20OR%20conflict%20OR%20missile%20OR%20invasion&hl=en-US&gl=US&ceid=US:en", .conflict),
        ("gn-markets", "https://news.google.com/rss/search?q=stock%20market%20OR%20inflation%20OR%20%22interest%20rate%22&hl=en-US&gl=US&ceid=US:en", .markets),
        ("gn-energy", "https://news.google.com/rss/search?q=oil%20price%20OR%20natural%20gas%20OR%20OPEC&hl=en-US&gl=US&ceid=US:en", .energy),
        ("gn-tech", "https://news.google.com/rss/search?q=cyberattack%20OR%20ransomware%20OR%20outage&hl=en-US&gl=US&ceid=US:en", .tech),
        ("gn-sc", "https://news.google.com/rss/search?q=port%20congestion%20OR%20%22supply%20chain%22%20OR%20freight%20rates&hl=en-US&gl=US&ceid=US:en", .supplychain),
        ("gn-disaster", "https://news.google.com/rss/search?q=earthquake%20OR%20wildfire%20OR%20flood%20OR%20cyclone&hl=en-US&gl=US&ceid=US:en", .disaster),
    ]

    static let supply: [(name: String, url: String, category: Category)] = [
        ("gn-sc", "https://news.google.com/rss/search?q=port%20congestion%20OR%20%22supply%20chain%22%20OR%20freight%20rates%20OR%20shipping&hl=en-US&gl=US&ceid=US:en", .supplychain),
        ("gn-suez", "https://news.google.com/rss/search?q=Suez%20OR%20Panama%20Canal%20OR%20Red%20Sea%20shipping&hl=en-US&gl=US&ceid=US:en", .supplychain),
        ("gn-ports", "https://news.google.com/rss/search?q=port%20strike%20OR%20port%20closure%20OR%20container%20ship&hl=en-US&gl=US&ceid=US:en", .supplychain),
    ]

    static let markets: [(name: String, url: String, category: Category)] = [
        ("bbc-business", "https://feeds.bbci.co.uk/news/business/rss.xml", .markets),
        ("gn-business", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en", .markets),
        ("gn-markets", "https://news.google.com/rss/search?q=stock%20market%20OR%20inflation%20OR%20%22interest%20rate%22%20OR%20recession&hl=en-US&gl=US&ceid=US:en", .markets),
        ("gn-energy", "https://news.google.com/rss/search?q=oil%20price%20OR%20natural%20gas%20OR%20OPEC%20OR%20energy%20crisis&hl=en-US&gl=US&ceid=US:en", .energy),
    ]

    static func dedupe(_ events: [WorldEvent]) -> [WorldEvent] {
        // Dictionary(uniqueKeysWithValues:) traps on duplicate IDs — dedupe safely.
        var seen = Set<String>()
        var out: [WorldEvent] = []
        for e in events.sorted(by: { $0.published > $1.published }) {
            if seen.insert(e.id).inserted { out.append(e) }
        }
        return out
    }
}

/// Best-effort background refresh via iOS BackgroundTasks.
/// iOS decides when these run (typically every ~15-30 min) — this is the
/// platform's maximum for a free account, and it costs minimal battery
/// because the system manages the schedule.
enum BackgroundRefresh {
    static let identifier = "com.worldintel.refresh"

    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: nil) { task in
            guard let task = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            handle(task: task)
        }
    }

    static func schedule() {
        guard UserDefaults.standard.bool(forKey: "backgroundRefreshEnabled") else { return }
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        // Ask for 5 minutes; iOS schedules at its own discretion.
        request.earliestBeginDate = Date(timeIntervalSinceNow: 5 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    static func cancel() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: identifier)
    }

    private static func handle(task: BGAppRefreshTask) {
        schedule() // queue the next wake
        // setTaskCompleted must be called exactly once — guard against the
        // expiration handler and the work completing both firing.
        var completed = false
        func finish(success: Bool) {
            guard !completed else { return }
            completed = true
            task.setTaskCompleted(success: success)
        }
        task.expirationHandler = { finish(success: false) }
        Task {
            await refreshAllCaches()
            finish(success: true)
        }
    }

    /// Fast refresh of the essential caches — used in the short background window.
    /// GDELT is skipped (its 1-req/5s limit makes it too slow for background wakes).
    static func refreshAllCaches() async {
        async let feed = APIClient.shared.rssEvents(feeds: SourceFeeds.newsCore)
        async let supply = APIClient.shared.rssEvents(feeds: SourceFeeds.supply)
        async let markets = APIClient.shared.rssEvents(feeds: SourceFeeds.markets)
        async let eonet = APIClient.shared.eonetEvents()
        async let usgs = APIClient.shared.usgsEvents()
        async let gdacs = APIClient.shared.gdacsEvents()

        let (f, s, m, en, us, gd) = await (feed, supply, markets, eonet, usgs, gdacs)

        // Background window is short, so only the core feeds are fetched — merge
        // them into whatever is already cached so the feed never shrinks.
        let existing = CacheStore.shared.load([WorldEvent].self, key: "feed") ?? []
        let feedEvents = SourceFeeds.dedupe(f + existing)
        let disasterEvents = SourceFeeds.dedupe(en + us + gd)

        CacheStore.shared.save(feedEvents, key: "feed")
        CacheStore.shared.save(SourceFeeds.dedupe(s), key: "supplychain")
        CacheStore.shared.save(SourceFeeds.dedupe(m), key: "markets")
        CacheStore.shared.save(disasterEvents, key: "disasters")

        NotificationManager.shared.checkAndNotify(events: feedEvents + disasterEvents)
    }
}
