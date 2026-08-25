import SwiftUI
import MapKit
import Combine

@MainActor
final class MapModel: ObservableObject {
    @Published var events: [WorldEvent] = []
    @Published var aircraft: [Aircraft] = []
    @Published var vessels: [Vessel] = []
    @Published var showFlights = true
    @Published var showShips = true
    @Published var showEvents = true

    func load(force: Bool = false) async {
        await fetch(force: force)
    }

    func refreshNow() async {
        await fetch(force: true)
    }

    func toggleFlights() { showFlights.toggle() }
    func toggleShips() { showShips.toggle() }
    func toggleEvents() { showEvents.toggle() }

    private func fetch(force: Bool) async {
        if let base = AppServer.baseURL {
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
        // Fetch everything in parallel: ALL news feeds + disasters + conflict points + planes + ships.
        async let news = APIClient.shared.rssEvents(feeds: SourceFeeds.newsAll)
        async let eonet = APIClient.shared.eonetEvents()
        async let usgs = APIClient.shared.usgsEvents()
        async let gdacs = APIClient.shared.gdacsEvents()
        async let points = APIClient.shared.gdeltPoints()
        async let planes = APIClient.shared.aircraft(limit: 250)
        async let ships = APIClient.shared.vessels(limit: 250)
        let (n, e, u, g, p, pl, sh) = await (news, eonet, usgs, gdacs, points, planes, ships)
        let all = [n, e, u, g, p].flatMap { $0 }
        let geoed = GeoCoder.attach(SourceFeeds.dedupe(all)).filter { $0.geo != nil }
        events = geoed
        aircraft = pl
        vessels = sh
        CacheStore.shared.save(geoed, key: "map")
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
            // Satellite map with all layers.
            Map(position: $camera) {
                // Events — colored dots by category, sized by severity.
                if model.showEvents {
                    let shown = model.events
                        .sorted { ($0.severity, $0.published) > ($1.severity, $1.published) }
                        .prefix(400)
                    ForEach(Array(shown)) { event in
                        if let geo = event.geo {
                            Annotation(event.title, coordinate: CLLocationCoordinate2D(latitude: geo.lat, longitude: geo.lon)) {
                                Circle()
                                    .fill(Color(cv: event.category.color).opacity(0.85))
                                    .frame(width: 8 + CGFloat(event.severity) * 3)
                                    .overlay(Circle().stroke(Color.white.opacity(0.3), lineWidth: 1))
                            }
                        }
                    }
                }

                // Aircraft — airplane emoji, sized by altitude.
                if model.showFlights {
                    ForEach(model.aircraft) { plane in
                        Annotation(plane.callsign.isEmpty ? plane.id : plane.callsign,
                                   coordinate: CLLocationCoordinate2D(latitude: plane.lat, longitude: plane.lon)) {
                            let sz = min(22, max(10, CGFloat(plane.altitude / 500)))
                            Text("✈️")
                                .font(.system(size: sz))
                                .rotationEffect(.degrees(plane.heading))
                                .shadow(color: .black.opacity(0.5), radius: 1)
                        }
                    }
                }

                // Vessels — ship emoji.
                if model.showShips {
                    ForEach(model.vessels) { vessel in
                        Annotation(vessel.name.isEmpty ? vessel.id : vessel.name,
                                   coordinate: CLLocationCoordinate2D(latitude: vessel.lat, longitude: vessel.lon)) {
                            Text("🚢")
                                .font(.system(size: 12))
                                .rotationEffect(.degrees(vessel.course))
                                .shadow(color: .black.opacity(0.5), radius: 1)
                        }
                    }
                }
            }
            .mapStyle(.hybrid) // satellite + labels
            .ignoresSafeArea(edges: .bottom)

            // Status bar + refresh.
            HStack(spacing: 8) {
                Text("\(model.events.count) events")
                    .font(.caption).bold()
                if model.aircraft.count > 0 {
                    Text("· \(model.aircraft.count) ✈️")
                        .font(.caption)
                }
                if model.vessels.count > 0 {
                    Text("· \(model.vessels.count) 🚢")
                        .font(.caption)
                }
                Spacer()
                Button("Refresh") { Task { await model.load(force: true) } }
                    .font(.caption).bold()
            }
            .padding(10)
            .background(.ultraThinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .padding(12)

            // Toggle controls.
            VStack(alignment: .leading, spacing: 6) {
                ToggleRow(icon: "circle.fill", color: .blue, label: "Events", isOn: $model.showEvents)
                ToggleRow(icon: "airplane", color: .white, label: "Flights", isOn: $model.showFlights)
                ToggleRow(icon: "ferry", color: .cyan, label: "Ships", isOn: $model.showShips)

                Divider().background(Color.white.opacity(0.3))

                // Category legend.
                ForEach(Category.allCases) { c in
                    HStack(spacing: 6) {
                        Circle()
                            .fill(Color(cv: c.color))
                            .frame(width: 8, height: 8)
                        Text(c.label)
                            .font(.caption2)
                            .foregroundColor(.white.opacity(0.7))
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
        .onReceive(NotificationCenter.default.publisher(for: .dataTick)) { note in
            guard note.object as? String == "map" else { return }
            Task { await model.refreshNow() }
        }
    }
}

private struct ToggleRow: View {
    let icon: String
    let color: Color
    let label: String
    @Binding var isOn: Bool

    var body: some View {
        Button { isOn.toggle() } label: {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .foregroundColor(isOn ? color : .gray)
                    .frame(width: 16)
                Text(label)
                    .font(.caption)
                    .foregroundColor(isOn ? .white : .gray)
            }
        }
        .buttonStyle(.plain)
    }
}
