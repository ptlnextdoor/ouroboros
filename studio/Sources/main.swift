// FORGE Studio -- a slim native macOS window that docks beside Fusion 360.
//
// Single-file Swift (swiftc, no Xcode project). A WKWebView pinned edge to edge
// pointing at the Studio server (studio/server.py). The app starts the server
// itself on launch if the port is free and stops it on quit. The window is sized
// like ChatGPT desktop / Cursor's agent panel: narrow and full height, meant to
// sit on the right while Fusion 360 fills the left.

import Cocoa
import WebKit

let bundleInfo = Bundle.main.infoDictionary ?? [:]

func repoRoot() -> String {
    if let baked = bundleInfo["FORGERepoRoot"] as? String,
       FileManager.default.fileExists(atPath: baked + "/studio/server.py") {
        return baked
    }
    var url = Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent()
    if FileManager.default.fileExists(atPath: url.appendingPathComponent("studio/server.py").path) {
        return url.path
    }
    url = Bundle.main.executableURL ?? Bundle.main.bundleURL
    for _ in 0..<6 {
        url = url.deletingLastPathComponent()
        if FileManager.default.fileExists(atPath: url.appendingPathComponent("studio/server.py").path) {
            return url.path
        }
    }
    return FileManager.default.currentDirectoryPath
}

let REPO = repoRoot()
let PORT = 8010
let BASE = "http://127.0.0.1:\(PORT)"

func pythonBin() -> String {
    if let baked = bundleInfo["FORGEPython"] as? String,
       FileManager.default.fileExists(atPath: baked) { return baked }
    for p in ["/opt/miniconda3/bin/python3", "/usr/bin/python3", "/opt/homebrew/bin/python3"] {
        if FileManager.default.fileExists(atPath: p) { return p }
    }
    return "/usr/bin/python3"
}
let PY = pythonBin()

func portInUse(_ port: Int) -> Bool {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    if fd < 0 { return false }
    defer { close(fd) }
    var addr = sockaddr_in()
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = in_port_t(UInt16(port).bigEndian)
    addr.sin_addr.s_addr = inet_addr("127.0.0.1")
    let rc = withUnsafePointer(to: &addr) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    return rc == 0
}

final class Server {
    private var proc: Process?
    private var started = false

    func start() {
        if portInUse(PORT) { started = false; return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: PY)
        p.arguments = ["-u", "studio/server.py", "--port", "\(PORT)"]
        p.currentDirectoryURL = URL(fileURLWithPath: REPO)
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do { try p.run(); proc = p; started = true } catch { NSLog("studio server: \(error)") }
    }
    func stop() { if started { proc?.terminate() } }
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    let server = Server()
    var tries = 0

    func applicationDidFinishLaunching(_ note: Notification) {
        server.start()

        let rect = NSRect(x: 0, y: 0, width: 480, height: 1000)
        window = NSWindow(contentRect: rect,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.title = "FORGE Studio"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = NSColor(srgbRed: 6/255, green: 8/255, blue: 13/255, alpha: 1)
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 380, height: 560)

        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .nonPersistent()
        web = WKWebView(frame: rect, configuration: cfg)
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")  // let the dark window show through on load
        window.contentView = web

        // dock to the right third of the main screen
        if let screen = NSScreen.main {
            let vf = screen.visibleFrame
            let w: CGFloat = max(440, min(520, vf.width * 0.30))
            window.setFrame(NSRect(x: vf.maxX - w, y: vf.minY, width: w, height: vf.height), display: true)
        }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        load()
    }

    func load() {
        let auto = ProcessInfo.processInfo.environment["FORGE_AUTO"] == "1" ? "?auto=1" : ""
        web.load(URLRequest(url: URL(string: BASE + "/" + auto)!))
    }

    func webView(_ w: WKWebView, didFail nav: WKNavigation!, withError error: Error) { retry() }
    func webView(_ w: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError error: Error) { retry() }

    func retry() {
        tries += 1
        if tries > 40 { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { [weak self] in self?.load() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ note: Notification) { server.stop() }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
