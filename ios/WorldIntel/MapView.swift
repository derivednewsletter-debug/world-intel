import SwiftUI
import MapKit
import Combine

@MainActor
final class MapModel: ObservableObject {
    @Published var events: [WorldEvent] = []

    func load(force: Bool = false) async {
        await fetch(force: force)
    }

    /// Unconditional refresh — called by the 30s foreground tick.
    func refreshNow() async {
        await fetch(force: true)
    }

    private func fetch(force: Bool) async {
        if let base = AppServer.baseURL {
            // Local-backend mode: includes FIRMS fires, NOAA weather and GDELT points.
            let all = await APIClient.shared.serverEvents(base: base, query: [
                URLQueryItem(name: "geo", value: "1"),
                URLQueryItem(name: "limit", value: "500"),
            ])
            let deduped = SourceFeeds.dedupe(all).filter { $0.geo != nil }
            events = deduped
            CacheStore.shared.save(deduped, key: "map")
            return
        }
        if !force {
            if let cached = CacheStore.shared.load([WorldEvent].self, key: "map") {
                events = cached
            }
            if let age = CacheStore.shared.age(of: "map"), age < TTL.map { return }
        }
        async let eonet = APIClient.shared.eonetEvents()
        async let usgs = APIClient.shared.usgsEvents()
        async let gdacs = APIClient.shared.gdacsEvents()
        async let points = APIClient.shared.gdeltPoints()
        let all = await [eonet, usgs, gdacs, points].flatMap { $0 }
        let deduped = SourceFeeds.dedupe(all).filter { $0.geo != nil }
        events = deduped
        CacheStore.shared.save(deduped, key: "map")
    }
}

struct MapView: View {
    @StateObject private var model = MapModel()
    @State private var camera: MapCameraPosition = .region(
        MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 20, longitude: 0),
            span: MKCoordinateSpan(latitudeDelta: 120, longitudeDelta: 180)
        )
    )

    var body: some View {
        ZStack(alignment: .top) {
            Map(position: $camera) {
                ForEach(model.events) { event in
                    if let geo = event.geo {
                        Annotation(event.title, coordinate: CLLocationCoordinate2D(latitude: geo.lat, longitude: geo.lon)) {
                            Circle()
                                .fill(Color(cv: event.category.color).opacity(0.85))
                                .frame(width: 9 + CGFloat(event.severity) * 4)
                                .overlay(Circle().stroke(Color.appBg, lineWidth: 1.5))
                        }
                    }
                }
            }
            .ignoresSafeArea(edges: .bottom)

            HStack(spacing: 8) {
                Text("\(model.events.count) geo events")
                    .font(.caption).bold()
                Spacer()
                Button("Refresh") { Task { await model.load(force: true) } }
                    .font(.caption).bold()
            }
            .padding(10)
            .background(.ultraThinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .padding(12)

            VStack(alignment: .leading, spacing: 4) {
                ForEach(Category.allCases) { c in
                    HStack(spacing: 6) {
                        Circle()
                            .fill(Color(cv: c.color))
                            .frame(width: 9, height: 9)
                        Text(c.label)
                            .font(.caption2)
                            .foregroundColor(.appMuted)
                    }
                }
            }
            .padding(10)
            .background(.ultraThinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .padding(12)
            .frame(maxHeight: .infinity, alignment: .bottomLeading)
        }
        .background(Color.appBg)
        .task { await model.load() }
        .refreshable { await model.refreshNow() }
        .onReceive(NotificationCenter.default.publisher(for: .dataTick)) { _ in
            Task { await model.refreshNow() }
        }
    }
}
