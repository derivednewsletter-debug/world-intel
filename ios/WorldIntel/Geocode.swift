import Foundation

/// Offline headline geocoder: matches country / city / region names in event
/// titles & summaries and attaches approximate coordinates — no network needed,
/// so news (not just disasters) lands on the map instantly.
enum GeoCoder {

    /// Longest names first so "south korea" wins over "korea", "papua new guinea" over "guinea".
    private static let places: [(String, Double, Double)] = [
        // Regions & chokepoints (check first — specific wins over general)
        ("middle east", 27, 45), ("red sea", 19, 38.5), ("suez canal", 30.5, 32.3),
        ("panama canal", 9.1, -79.7), ("persian gulf", 26.5, 51.5), ("strait of hormuz", 26.6, 56.3),
        ("south china sea", 12, 114), ("black sea", 43.5, 34), ("baltic sea", 58, 20),
        ("mediterranean", 35, 18), ("caribbean", 15, -72), ("gulf of mexico", 25.5, -90),
        ("english channel", 50.5, 0), ("strait of malacca", 2.5, 101.5),
        ("cape of good hope", -34.4, 18.5), ("horn of africa", 10, 51),
        ("south china", 12, 114), ("east china", 28, 125),
        ("indo pacific", 0, 100), ("europe", 50, 15), ("africa", 2, 20),
        ("asia", 34, 100), ("latin america", -15, -60), ("middle-east", 27, 45),
        ("north atlantic", 45, -30), ("south atlantic", -20, -20),
        ("north pacific", 40, -160), ("south pacific", -20, -160),
        ("arctic", 75, -40), ("antarctica", -80, 0),

        // Multi-word countries / territories
        ("papua new guinea", -6.5, 145), ("united arab emirates", 24, 54),
        ("united kingdom", 54, -2), ("united states", 39, -98),
        ("south africa", -29, 24), ("south korea", 36.5, 128),
        ("north korea", 40, 127), ("south sudan", 7.5, 30),
        ("costa rica", 9.9, -84.1), ("el salvador", 13.7, -89.2),
        ("honduras", 15.2, -86.2), ("guatemala", 15.5, -90),
        ("dominican republic", 19, -70.7), ("trinidad and tobago", 10.5, -61.3),
        ("saudi arabia", 24, 45), ("sierra leone", 8.5, -11.8),
        ("burkina faso", 12.3, -1.7), ("sri lanka", 7.5, 80.7),
        ("ivory coast", 7.5, -5.5), ("new zealand", -42, 172),
        ("puerto rico", 18.2, -66.4), ("west bank", 32, 35.3),

        // Major cities
        ("hong kong", 22.3, 114.2), ("mexico city", 19.43, -99.13),
        ("new york", 40.71, -74.01), ("san francisco", 37.77, -122.42),
        ("los angeles", 34.05, -118.24), ("buenos aires", -34.6, -58.38),
        ("rio de janeiro", -22.9, -43.2), ("sao paulo", -23.55, -46.63),
        ("new delhi", 28.6, 77.2), ("tel aviv", 32.08, 34.78),
        ("gaza city", 31.5, 34.47), ("gaza strip", 31.4, 34.36),
        ("kyiv", 50.45, 30.52), ("kiev", 50.45, 30.52),
        ("moscow", 55.75, 37.6), ("beijing", 39.9, 116.4),
        ("shanghai", 31.2, 121.5), ("tokyo", 35.7, 139.7),
        ("seoul", 37.57, 126.98), ("pyongyang", 39, 125.7),
        ("mumbai", 19.08, 72.88), ("delhi", 28.6, 77.2),
        ("islamabad", 33.7, 73.05), ("karachi", 24.86, 67),
        ("tehran", 35.7, 51.4), ("jerusalem", 31.78, 35.22),
        ("baghdad", 33.3, 44.4), ("damascus", 33.5, 36.3),
        ("beirut", 33.9, 35.5), ("riyadh", 24.7, 46.7),
        ("dubai", 25.2, 55.3), ("doha", 25.3, 51.5),
        ("istanbul", 41, 28.97), ("ankara", 39.93, 32.85),
        ("cairo", 30.04, 31.24), ("tripoli", 32.9, 13.2),
        ("khartoum", 15.5, 32.6), ("nairobi", -1.29, 36.82),
        ("lagos", 6.5, 3.4), ("abuja", 9.06, 7.49),
        ("johannesburg", -26.2, 28.04), ("cape town", -33.93, 18.42),
        ("london", 51.5, -0.12), ("paris", 48.85, 2.35),
        ("berlin", 52.52, 13.4), ("madrid", 40.42, -3.7),
        ("rome", 41.9, 12.5), ("brussels", 50.85, 4.35),
        ("amsterdam", 52.37, 4.9), ("vienna", 48.2, 16.37),
        ("warsaw", 52.23, 21), ("prague", 50.08, 14.44),
        ("athens", 37.98, 23.73), ("stockholm", 59.33, 18.06),
        ("oslo", 59.91, 10.75), ("helsinki", 60.17, 24.94),
        ("copenhagen", 55.68, 12.57), ("budapest", 47.5, 19.04),
        ("bucharest", 44.43, 26.1), ("sofia", 42.7, 23.32),
        ("zagreb", 45.81, 15.98), ("belgrade", 44.79, 20.47),
        ("washington", 38.9, -77.03), ("chicago", 41.88, -87.63),
        ("ottawa", 45.42, -75.7), ("toronto", 43.65, -79.38),
        ("bogota", 4.71, -74.07), ("caracas", 10.5, -66.9),
        ("brasilia", -15.79, -47.88), ("santiago", -33.45, -70.66),
        ("lima", -12.05, -77.04), ("taipei", 25.03, 121.57),
        ("manila", 14.6, 120.98), ("jakarta", -6.2, 106.85),
        ("bangkok", 13.75, 100.5), ("hanoi", 21.02, 105.83),
        ("kabul", 34.53, 69.17), ("addis ababa", 9.03, 38.74),
        ("casablanca", 33.57, -7.59), ("tunis", 36.81, 10.18),
        ("algiers", 36.75, 3.04), ("amman", 31.95, 35.93),
        ("kuwait city", 29.38, 47.99), ("manama", 26.23, 50.58),
        ("muscat", 23.59, 58.54), ("abu dhabi", 24.47, 54.37),
        ("singapore", 1.35, 103.8), ("kuala lumpur", 3.14, 101.69),
        ("yangon", 16.87, 96.2), ("dhaka", 23.81, 90.41),
        ("colombo", 6.93, 79.85), ("kathmandu", 27.72, 85.32),
        ("ulaanbaatar", 47.91, 106.91), ("astana", 51.17, 71.43),
        ("tashkent", 41.3, 69.28), ("bishkek", 42.87, 74.59),
        ("dushanbe", 38.56, 68.77), ("kabul", 34.53, 69.17),
        ("taipei", 25.03, 121.57), ("osaka", 34.69, 135.5),
        ("nagasaki", 32.75, 129.88), ("okinawa", 26.34, 127.77),
        ("guam", 13.44, 144.79), ("diego garcia", -7.32, 72.41),

        // Countries
        ("ukraine", 49, 32), ("russia", 61, 90), ("iran", 32, 53),
        ("iraq", 33, 44), ("syria", 35, 38), ("lebanon", 33.9, 35.5),
        ("jordan", 31, 36), ("yemen", 15.5, 48), ("oman", 21, 57),
        ("qatar", 25.3, 51.2), ("kuwait", 29.3, 47.5), ("turkey", 39, 35),
        ("egypt", 26, 30), ("taiwan", 23.7, 121), ("china", 35, 105),
        ("japan", 36, 138), ("india", 21, 78), ("pakistan", 30, 70),
        ("afghanistan", 34, 66), ("bangladesh", 24, 90), ("nepal", 28, 84),
        ("myanmar", 21, 96), ("burma", 21, 96), ("thailand", 15, 101),
        ("vietnam", 16, 106), ("cambodia", 12.5, 105), ("laos", 18, 104),
        ("malaysia", 4, 102), ("indonesia", -2, 118), ("philippines", 12, 122),
        ("singapore", 1.35, 103.8), ("australia", -25, 134),
        ("france", 46, 2), ("germany", 51, 10), ("italy", 42.8, 12.5),
        ("spain", 40, -4), ("portugal", 39.5, -8), ("britain", 54, -2),
        ("england", 52.5, -1.5), ("scotland", 56.5, -4), ("wales", 52, -3.5),
        ("ireland", 53, -8), ("netherlands", 52.2, 5.3), ("belgium", 50.6, 4.5),
        ("switzerland", 46.8, 8.2), ("austria", 47.6, 14.1), ("poland", 52, 19),
        ("hungary", 47.2, 19.4), ("romania", 46, 25), ("bulgaria", 43, 25),
        ("greece", 39, 22), ("serbia", 44, 21), ("croatia", 45.2, 16.4),
        ("bosnia", 44, 18), ("belarus", 53.7, 28), ("finland", 64, 26),
        ("sweden", 62, 15), ("norway", 61, 9), ("denmark", 56, 10),
        ("estonia", 58.7, 25), ("latvia", 56.9, 24.9), ("lithuania", 55.3, 23.9),
        ("moldova", 47.2, 28.5), ("iceland", 65, -18), ("albania", 41, 20),
        ("montenegro", 42.5, 19.3), ("macedonia", 41.5, 21.7),
        ("kosovo", 42.6, 20.9), ("cyprus", 35, 33),
        ("america", 39, -98), ("canada", 56, -106), ("mexico", 23, -102),
        ("haiti", 19, -72.5), ("cuba", 21.5, -79.5), ("panama", 8.5, -80),
        ("colombia", 4, -73), ("venezuela", 7, -66), ("brazil", -10, -52),
        ("argentina", -34, -64), ("chile", -33, -71), ("peru", -9, -75),
        ("bolivia", -17, -64), ("ecuador", -1.8, -78), ("paraguay", -23, -58),
        ("uruguay", -32.8, -56), ("nigeria", 9, 8), ("ghana", 7.9, -1),
        ("kenya", 0.5, 37.8), ("ethiopia", 9, 40), ("somalia", 6, 46),
        ("sudan", 15, 30), ("mali", 17, -4), ("niger", 17, 9),
        ("chad", 15, 19), ("libya", 27, 17), ("tunisia", 34, 9),
        ("algeria", 28, 2), ("morocco", 31.8, -7), ("congo", -2, 23),
        ("cameroon", 5.7, 12.7), ("tanzania", -6, 35), ("uganda", 1.4, 32.3),
        ("rwanda", -2, 29.9), ("mozambique", -18, 35), ("zimbabwe", -19, 29.8),
        ("zambia", -13.5, 27.8), ("angola", -11.5, 17.9), ("senegal", 14.5, -14.5),
        ("eritrea", 15.2, 39.8), ("kazakhstan", 48, 68), ("uzbekistan", 41.4, 64.6),
        ("armenia", 40.1, 45), ("azerbaijan", 40.3, 47.7), ("georgia", 42.3, 43.4),
        ("mongolia", 47, 104), ("uzbekistan", 41.4, 64.6),
        ("turkmenistan", 39, 58), ("kyrgyzstan", 41.2, 74.8),
        ("tajikistan", 39, 71),
        ("palestine", 31.9, 35.2), ("gaza", 31.4, 34.36),

        // US states (common in headlines)
        ("texas", 31, -99), ("florida", 27.8, -81.6), ("california", 36.7, -119.4),
        ("new york state", 43, -75), ("chicago", 41.88, -87.63),
        ("hawaii", 20.5, -157.5), ("alaska", 64, -153),

        // Common news shorthand
        ("gaza", 31.4, 34.36), ("west bank", 32, 35.3),
        ("crimea", 45.3, 34.1), ("donbas", 48.5, 38),
        ("kashmir", 34.5, 76), ("taiwan strait", 24, 119),
        ("spratly", 10, 114), ("paracel", 16, 112),
        ("golan heights", 33.1, 35.8),
    ]

    static func placeName(for coordinate: Geo) -> String {
        for (name, lat, lon) in places where abs(lat - coordinate.lat) < 0.01 && abs(lon - coordinate.lon) < 0.01 {
            return name.capitalized
        }
        return coordinate.place ?? ""
    }

    /// Returns coordinates guessed from free text, or nil if nothing recognizable.
    static func guess(in rawText: String) -> Geo? {
        let normalized = rawText.lowercased()
            .replacingOccurrences(of: "[^a-z0-9]+", with: " ", options: .regularExpression)
        let padded = " \(normalized) "
        for (name, lat, lon) in places {
            if padded.contains(" \(name) ") {
                return Geo(lat: lat, lon: lon, place: name.capitalized)
            }
        }
        return nil
    }

    /// Fills in missing geo on events using their title + summary.
    static func attach(_ events: [WorldEvent]) -> [WorldEvent] {
        events.map { e in
            guard e.geo == nil else { return e }
            guard let g = guess(in: "\(e.title) \(e.summary ?? "")") else { return e }
            return WorldEvent(
                id: e.id, source: e.source, category: e.category, severity: e.severity,
                title: e.title, url: e.url, summary: e.summary, image: e.image,
                published: e.published, geo: g
            )
        }
    }
}
