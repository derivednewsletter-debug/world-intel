import SwiftUI

struct WatchView: View {
    private let streams: [LiveStream] = [
        LiveStream(name: "Al Jazeera English", url: "https://www.youtube.com/embed/live_stream?channel=UCNye-wNBqNL5ZzHSJj3l8Bg", note: "24/7 international news"),
        LiveStream(name: "DW News", url: "https://www.youtube.com/embed/live_stream?channel=UCknLrEdhRCp1aegoMqRaCZg", note: "24/7 news from Germany"),
        LiveStream(name: "France 24 English", url: "https://www.youtube.com/embed/live_stream?channel=UCQfwfsi5VrQ8yKZ-UWmAEFg", note: "24/7 international news"),
        LiveStream(name: "Sky News", url: "https://www.youtube.com/embed/live_stream?channel=UCoMdktPbSTixAyNGwb-UYkQ", note: "24/7 UK news"),
        LiveStream(name: "Reuters", url: "https://www.youtube.com/embed/live_stream?channel=UChqUTb7kYRX8-EiaN3XFrSQ", note: "Breaking coverage"),
        LiveStream(name: "ABC News Live", url: "https://www.youtube.com/embed/live_stream?channel=UCBi2mrWuNuyYy4gbM6fU18Q", note: "24/7 US news"),
        LiveStream(name: "CNBC", url: "https://www.youtube.com/embed/live_stream?channel=UCrp_UI8XtuYfpiqluWLD7Lw", note: "24/7 business & markets"),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("Free official news streams. Players load only when you open a channel — nothing runs in the background.")
                    .font(.caption)
                    .foregroundColor(.appMuted)
                ForEach(streams) { stream in
                    NavigationLink(destination: StreamPlayerView(stream: stream)) {
                        HStack {
                            Image(systemName: "play.circle.fill")
                                .font(.title2)
                                .foregroundColor(.appErr)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(stream.name).fontWeight(.medium)
                                Text(stream.note).font(.caption).foregroundColor(.appMuted)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption).foregroundColor(.appMuted)
                        }
                        .padding(12)
                        .panel()
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(12)
        }
        .background(Color.appBg)
        .navigationTitle("Watch Live")
    }
}
