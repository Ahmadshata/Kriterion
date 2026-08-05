import AppKit
import WebKit

guard CommandLine.arguments.count == 3 else {
    fputs("usage: swift designs/render_previews.swift <concept-html> <output-dir>\n", stderr)
    exit(2)
}

let sourceURL = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
let outputDirectory = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
try FileManager.default.createDirectory(
    at: outputDirectory,
    withIntermediateDirectories: true
)

final class PreviewRenderer: NSObject, WKNavigationDelegate {
    private struct Target {
        let concept: String
        let filename: String
        let width: CGFloat
        let maximumHeight: Double
    }

    private let targets = [
        Target(concept: "clarity", filename: "clarity", width: 1440, maximumHeight: 3400),
        Target(concept: "signal", filename: "signal", width: 1440, maximumHeight: 3400),
        Target(concept: "folio", filename: "folio", width: 1440, maximumHeight: 3400),
        Target(concept: "spectral", filename: "spectral", width: 1440, maximumHeight: 3800),
        Target(concept: "clarity", filename: "clarity-mobile", width: 390, maximumHeight: 5200),
        Target(concept: "signal", filename: "signal-mobile", width: 390, maximumHeight: 5200),
        Target(concept: "folio", filename: "folio-mobile", width: 390, maximumHeight: 5200),
        Target(concept: "spectral", filename: "spectral-mobile", width: 390, maximumHeight: 5400),
    ]
    private let sourceURL: URL
    private let outputDirectory: URL
    private var targetIndex = 0
    private let webView: WKWebView

    init(sourceURL: URL, outputDirectory: URL) {
        self.sourceURL = sourceURL
        self.outputDirectory = outputDirectory
        self.webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 1440, height: 1200))
        super.init()
        webView.navigationDelegate = self
    }

    func start() {
        renderCurrentConcept()
    }

    private func renderCurrentConcept() {
        let target = targets[targetIndex]
        webView.setFrameSize(NSSize(width: target.width, height: 1200))
        var components = URLComponents(url: sourceURL, resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "concept", value: target.concept)]
        webView.loadFileURL(
            components.url!,
            allowingReadAccessTo: sourceURL.deletingLastPathComponent().deletingLastPathComponent()
        )
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        let target = targets[targetIndex]
        webView.evaluateJavaScript("Math.min(document.documentElement.scrollHeight, \(target.maximumHeight))") { result, error in
            guard error == nil, let pageHeight = result as? Double else {
                self.fail("could not measure \(self.targets[self.targetIndex].concept)")
                return
            }

            let currentTarget = self.targets[self.targetIndex]
            webView.setFrameSize(NSSize(width: currentTarget.width, height: max(1200, pageHeight)))
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                let configuration = WKSnapshotConfiguration()
                configuration.rect = webView.bounds
                configuration.snapshotWidth = NSNumber(value: Double(currentTarget.width))
                webView.takeSnapshot(with: configuration) { image, snapshotError in
                    guard snapshotError == nil,
                          let image,
                          let tiff = image.tiffRepresentation,
                          let bitmap = NSBitmapImageRep(data: tiff),
                          let png = bitmap.representation(using: .png, properties: [:]) else {
                        self.fail("could not capture \(self.targets[self.targetIndex].concept)")
                        return
                    }

                    let destination = self.outputDirectory.appendingPathComponent("\(currentTarget.filename).png")
                    do {
                        try png.write(to: destination, options: .atomic)
                        print("rendered \(destination.path)")
                    } catch {
                        self.fail("could not write \(destination.path): \(error)")
                        return
                    }

                    self.targetIndex += 1
                    if self.targetIndex == self.targets.count {
                        NSApplication.shared.terminate(nil)
                    } else {
                        self.renderCurrentConcept()
                    }
                }
            }
        }
    }

    private func fail(_ message: String) {
        fputs("\(message)\n", stderr)
        exit(1)
    }
}

let renderer = PreviewRenderer(sourceURL: sourceURL, outputDirectory: outputDirectory)
renderer.start()
NSApplication.shared.run()
