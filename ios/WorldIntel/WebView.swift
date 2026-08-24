import SwiftUI
import WebKit

struct WebView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView(frame: .zero)
        webView.backgroundColor = .black
        webView.isOpaque = false
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        uiView.load(URLRequest(url: url))
    }
}

struct StreamPlayerView: View {
    let stream: LiveStream
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            WebView(url: URL(string: stream.url)!)
                .aspectRatio(16 / 9, contentMode: .fit)
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Text(stream.name).font(.title3).bold()
                    Text(stream.note).font(.caption).foregroundColor(.appMuted)
                    Text("Tap ▶ to start the live stream. The player loads only when you open this screen — no background streaming.")
                        .font(.caption)
                        .foregroundColor(.appMuted)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(Color.appBg)
        .navigationTitle(stream.name)
        .navigationBarTitleDisplayMode(.inline)
    }
}
