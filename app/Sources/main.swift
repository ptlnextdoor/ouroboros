// FORGE.app  -- native macOS shell for the FORGE live demo.
//
// Single-file Swift (swiftc, no Xcode project). An NSSplitViewController with a
// vibrant source-list sidebar and a WKWebView content pane pinned edge to edge.
// The sidebar switches the webview between the live loop, the SQ-2 showcase, and
// the offline replay, and starts a new forge.loop job from a typed goal.
//
// The app starts ui/serve.py itself on launch (if port 8008 is free) and stops
// it, plus any running forge.loop, on quit.

import Cocoa
import WebKit

// MARK: - repo + tool paths

let bundleInfo = Bundle.main.infoDictionary ?? [:]

func repoRoot() -> String {
    if let baked = bundleInfo["FORGERepoRoot"] as? String,
       FileManager.default.fileExists(atPath: baked + "/ui/serve.py") {
        return baked
    }
    var url = Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent()
    if FileManager.default.fileExists(atPath: url.appendingPathComponent("ui/serve.py").path) {
        return url.path
    }
    url = Bundle.main.executableURL ?? Bundle.main.bundleURL
    for _ in 0..<6 {
        url = url.deletingLastPathComponent()
        if FileManager.default.fileExists(atPath: url.appendingPathComponent("ui/serve.py").path) {
            return url.path
        }
    }
    return FileManager.default.currentDirectoryPath
}

let REPO = repoRoot()
let PORT = 8008
let BASE = "http://localhost:\(PORT)"

func pythonBin() -> String {
    if let baked = bundleInfo["FORGEPython"] as? String,
       FileManager.default.fileExists(atPath: baked) { return baked }
    for p in ["/opt/miniconda3/bin/python3", "/usr/bin/python3", "/opt/homebrew/bin/python3"] {
        if FileManager.default.fileExists(atPath: p) { return p }
    }
    return "/usr/bin/python3"
}
let PY = pythonBin()

// MARK: - palette (matches ui/index.html tokens)

enum C {
    static func rgb(_ r: Int, _ g: Int, _ b: Int, _ a: CGFloat = 1) -> NSColor {
        NSColor(srgbRed: CGFloat(r)/255, green: CGFloat(g)/255, blue: CGFloat(b)/255, alpha: a)
    }
    static let bg    = rgb(6, 8, 13)       // content surface #06080d
    static let fg    = rgb(0xe8, 0xee, 0xf7)
    static let dim   = rgb(0x8d, 0xa0, 0xb8)
    static let faint = rgb(0x55, 0x66, 0x7a)
    static let pass  = rgb(0x2e, 0xe6, 0xa6)  // physics passed (green)
    static let acc   = rgb(0x4a, 0xa8, 0xff)  // accent (blue)
}

// MARK: - port check

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

// MARK: - task catalogue (New part -> closest known task)

struct Task { let id: String; let prompt: String }
let TASKS: [Task] = [
    Task(id: "br01", prompt: "hold a 1 kg sensor 60 mm off a wall, aluminium, survive 3 g"),
    Task(id: "br02", prompt: "mount a 2 kg motor 80 mm off a wall in aluminium, 3 g rating"),
    Task(id: "br03", prompt: "cantilever a 0.5 kg camera 100 mm out, aluminium, 3 g"),
    Task(id: "br04", prompt: "hold a 3 kg gearbox 70 mm off a wall, aluminium, 3 g"),
    Task(id: "br05", prompt: "support a 1.5 kg light 120 mm off a wall in aluminium, 2.5 g"),
    Task(id: "br06", prompt: "bracket a 0.8 kg pump 50 mm off a wall, PETG printed, 2 g"),
    Task(id: "br07", prompt: "hold a 2.5 kg motor 90 mm off a wall, aluminium, 3 g"),
    Task(id: "br08", prompt: "cantilever a 1 kg antenna 140 mm out, aluminium, 2.5 g"),
    Task(id: "br09", prompt: "mount a 4 kg actuator 60 mm off a wall, aluminium, 3 g"),
    Task(id: "br10", prompt: "hold a 0.6 kg controller 45 mm off a wall, PETG printed, 2 g"),
    Task(id: "br11", prompt: "mount a 2 kg motor 110 mm off a wall, aluminium, 3 g"),
    Task(id: "br12", prompt: "hold a 5 kg winch 65 mm off a wall, aluminium, 3 g"),
    Task(id: "br13", prompt: "cantilever a 1.2 kg speaker 130 mm out, aluminium, 2.5 g"),
    Task(id: "br14", prompt: "support a 3.5 kg battery 75 mm off a wall, aluminium, 3 g"),
    Task(id: "br15", prompt: "hold a 0.9 kg valve 55 mm off a wall, PETG printed, 2 g"),
    Task(id: "br16", prompt: "mount a 1.8 kg fan 150 mm off a wall, aluminium, 2.5 g"),
]

func tokens(_ s: String) -> Set<String> {
    var out = Set<String>(); var cur = ""
    for ch in s.lowercased() {
        if ch.isLetter || ch.isNumber || ch == "." { cur.append(ch) }
        else if !cur.isEmpty { out.insert(cur); cur = "" }
    }
    if !cur.isEmpty { out.insert(cur) }
    return out
}

func closestTask(_ goal: String) -> Task {
    let g = goal.lowercased()
    for t in TASKS where g.contains(t.id) { return t }
    let gt = tokens(goal)
    var best = TASKS[1]; var bestScore = -1.0
    for t in TASKS {
        let tt = tokens(t.prompt)
        let uni = Double(gt.union(tt).count)
        let score = uni > 0 ? Double(gt.intersection(tt).count) / uni : 0
        if score > bestScore { bestScore = score; best = t }
    }
    return best
}

// MARK: - process manager

final class Procs {
    private var server: Process?
    private var startedServer = false
    private var job: Process?

    func startServer() {
        if portInUse(PORT) { startedServer = false; return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: PY)
        p.arguments = ["ui/serve.py", "--port", "\(PORT)"]
        p.currentDirectoryURL = URL(fileURLWithPath: REPO)
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do { try p.run(); server = p; startedServer = true } catch { NSLog("FORGE server: \(error)") }
    }

    @discardableResult
    func startJob(taskID: String, playbook: String = "playbook/v2.md", budget: Double = 1.0) -> String {
        job?.terminate()
        let p = Process()
        p.executableURL = URL(fileURLWithPath: PY)
        p.arguments = ["-m", "forge.loop", "--task", taskID, "--playbook", playbook, "--budget", "\(budget)"]
        p.currentDirectoryURL = URL(fileURLWithPath: REPO)
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do { try p.run(); job = p } catch { NSLog("FORGE job: \(error)") }
        return taskID
    }

    func shutdown() {
        job?.terminate()
        if startedServer { server?.terminate() }
    }
}

// MARK: - source-list row (modern rounded selection pill)

final class SidebarRow: NSView {
    let key: String
    private let pill = NSView()
    private let icon = NSImageView()
    private let label = NSTextField(labelWithString: "")
    var onClick: ((String) -> Void)?

    init(key: String, title: String, symbol: String) {
        self.key = key
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false

        pill.wantsLayer = true
        pill.layer?.cornerRadius = 6
        pill.layer?.backgroundColor = NSColor.clear.cgColor
        pill.translatesAutoresizingMaskIntoConstraints = false
        addSubview(pill)

        let cfg = NSImage.SymbolConfiguration(pointSize: 13, weight: .regular)
        icon.image = NSImage(systemSymbolName: symbol, accessibilityDescription: title)?
            .withSymbolConfiguration(cfg)
        icon.contentTintColor = C.dim
        icon.translatesAutoresizingMaskIntoConstraints = false
        addSubview(icon)

        label.stringValue = title
        label.font = .systemFont(ofSize: 13, weight: .regular)
        label.textColor = C.fg
        label.translatesAutoresizingMaskIntoConstraints = false
        addSubview(label)

        NSLayoutConstraint.activate([
            heightAnchor.constraint(equalToConstant: 28),
            pill.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 6),
            pill.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -6),
            pill.topAnchor.constraint(equalTo: topAnchor, constant: 1),
            pill.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -1),
            icon.leadingAnchor.constraint(equalTo: pill.leadingAnchor, constant: 9),
            icon.centerYAnchor.constraint(equalTo: centerYAnchor),
            icon.widthAnchor.constraint(equalToConstant: 17),
            label.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 7),
            label.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])

        let click = NSClickGestureRecognizer(target: self, action: #selector(tapped))
        addGestureRecognizer(click)
    }
    required init?(coder: NSCoder) { fatalError() }

    @objc private func tapped() { onClick?(key) }

    func setSelected(_ on: Bool) {
        pill.layer?.backgroundColor = on
            ? NSColor.selectedContentBackgroundColor.withAlphaComponent(0.9).cgColor
            : NSColor.clear.cgColor
        icon.contentTintColor = on ? .white : C.dim
        label.textColor = on ? .white : C.fg
        label.font = .systemFont(ofSize: 13, weight: on ? .medium : .regular)
    }
}

// MARK: - sidebar view controller

final class SidebarVC: NSViewController, NSTextFieldDelegate {
    var onNavigate: ((String) -> Void)?
    var onForge: ((String) -> Void)?

    private var rows: [SidebarRow] = []
    let goalField = NSTextField()
    let statusLabel = NSTextField(labelWithString: "")

    override func loadView() {
        let v = NSVisualEffectView()
        v.material = .sidebar
        v.blendingMode = .behindWindow
        v.state = .active
        view = v
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        // wordmark
        let mark = NSTextField(labelWithString: "FORGE")
        mark.font = .systemFont(ofSize: 15, weight: .semibold)
        mark.textColor = C.fg
        let tag = NSTextField(labelWithString: "AI hardware engineer")
        tag.font = .systemFont(ofSize: 11, weight: .regular)
        tag.textColor = C.dim

        // new-part label
        let npLabel = sectionLabel("NEW PART")

        // goal field (rounded, search-field register)
        goalField.placeholderString = "Describe a part"
        goalField.font = .systemFont(ofSize: 12)
        goalField.bezelStyle = .roundedBezel
        goalField.isBordered = true
        goalField.focusRingType = .default
        goalField.lineBreakMode = .byTruncatingTail
        goalField.cell?.usesSingleLineMode = true
        goalField.cell?.wraps = false
        goalField.delegate = self

        // forge button: small, native prominent (accent fill when window is key)
        let forge = NSButton(title: "Forge part", target: self, action: #selector(forgeTapped))
        forge.bezelStyle = .rounded
        forge.controlSize = .regular
        forge.keyEquivalent = "\r"
        forge.font = .systemFont(ofSize: 12, weight: .medium)
        if #available(macOS 11.0, *) { forge.hasDestructiveAction = false }
        forge.bezelColor = C.acc

        statusLabel.font = .systemFont(ofSize: 10, weight: .regular)
        statusLabel.textColor = C.dim
        statusLabel.lineBreakMode = .byTruncatingTail
        statusLabel.cell?.usesSingleLineMode = true
        statusLabel.maximumNumberOfLines = 1

        // nav section
        let viewsLabel = sectionLabel("VIEWS")
        let navItems: [(String, String, String)] = [
            ("live",   "Live loop",      "waveform.path.ecg"),
            ("sq2",    "SQ-2 showcase",  "cube"),
            ("replay", "Replay",         "play.rectangle"),
        ]
        for (key, title, symbol) in navItems {
            let row = SidebarRow(key: key, title: title, symbol: symbol)
            row.onClick = { [weak self] k in self?.select(k); self?.onNavigate?(k) }
            rows.append(row)
        }

        let footer = NSTextField(labelWithString: "localhost:\(PORT)")
        footer.font = .monospacedSystemFont(ofSize: 10, weight: .regular)
        footer.textColor = C.faint

        // stack layout
        let navStack = NSStackView(views: rows)
        navStack.orientation = .vertical
        navStack.spacing = 2
        navStack.alignment = .leading
        navStack.distribution = .fill
        for r in rows { r.widthAnchor.constraint(equalTo: navStack.widthAnchor).isActive = true }

        let col = NSStackView(views: [mark, tag, npLabel, goalField, forge, statusLabel,
                                      viewsLabel, navStack])
        col.orientation = .vertical
        col.alignment = .leading
        col.spacing = 6
        col.translatesAutoresizingMaskIntoConstraints = false
        col.setCustomSpacing(2, after: mark)
        col.setCustomSpacing(18, after: tag)
        col.setCustomSpacing(6, after: npLabel)
        col.setCustomSpacing(8, after: goalField)
        col.setCustomSpacing(6, after: forge)
        col.setCustomSpacing(20, after: statusLabel)
        col.setCustomSpacing(6, after: viewsLabel)

        view.addSubview(col)
        view.addSubview(footer)
        footer.translatesAutoresizingMaskIntoConstraints = false

        let pad: CGFloat = 14
        NSLayoutConstraint.activate([
            // leave room under the transparent title bar
            col.topAnchor.constraint(equalTo: view.topAnchor, constant: 48),
            col.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: pad),
            col.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -pad),
            goalField.widthAnchor.constraint(equalTo: col.widthAnchor),
            navStack.widthAnchor.constraint(equalTo: col.widthAnchor),
            footer.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: pad + 2),
            footer.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -14),
        ])

        select("live")
    }

    private func sectionLabel(_ s: String) -> NSTextField {
        let l = NSTextField(labelWithString: s)
        l.font = .systemFont(ofSize: 10, weight: .semibold)
        l.textColor = C.faint
        return l
    }

    func select(_ key: String) {
        for r in rows { r.setSelected(r.key == key) }
    }

    @objc private func forgeTapped() {
        onForge?(goalField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    func control(_ c: NSControl, textView: NSTextView, doCommandBy sel: Selector) -> Bool {
        if sel == #selector(NSResponder.insertNewline(_:)) { forgeTapped(); return true }
        return false
    }
}

// MARK: - content view controller (WKWebView, edge to edge)

final class ContentVC: NSViewController, WKNavigationDelegate {
    private(set) var web: WKWebView!
    private var retries = 0

    override func loadView() {
        let container = NSView()
        container.wantsLayer = true
        container.layer?.backgroundColor = C.bg.cgColor

        let cfg = WKWebViewConfiguration()
        cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        web.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(web)
        NSLayoutConstraint.activate([
            web.topAnchor.constraint(equalTo: container.topAnchor),
            web.bottomAnchor.constraint(equalTo: container.bottomAnchor),
            web.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: container.trailingAnchor),
        ])
        view = container
    }

    func load(_ s: String) {
        retries = 0
        guard let u = URL(string: s) else { return }
        web.load(URLRequest(url: u))
    }

    func webView(_ wv: WKWebView, didFail n: WKNavigation!, withError e: Error) { retry(wv) }
    func webView(_ wv: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) { retry(wv) }
    private func retry(_ wv: WKWebView) {
        guard retries < 25, let u = wv.url else { return }
        retries += 1
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { wv.load(URLRequest(url: u)) }
    }
}

// MARK: - app delegate

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let procs = Procs()
    let sidebar = SidebarVC()
    let content = ContentVC()

    func applicationDidFinishLaunching(_ n: Notification) {
        procs.startServer()

        let split = NSSplitViewController()
        let sideItem = NSSplitViewItem(sidebarWithViewController: sidebar)
        sideItem.minimumThickness = 208
        sideItem.maximumThickness = 248
        sideItem.canCollapse = false
        let mainItem = NSSplitViewItem(viewController: content)
        split.addSplitViewItem(sideItem)
        split.addSplitViewItem(mainItem)

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1600, height: 1000),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.title = "FORGE"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .visible
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = C.bg
        window.minSize = NSSize(width: 1120, height: 720)
        window.contentViewController = split
        window.setContentSize(NSSize(width: 1600, height: 1000))
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        sidebar.onNavigate = { [weak self] key in self?.navigate(key) }
        sidebar.onForge = { [weak self] goal in self?.forge(goal) }

        content.load(BASE + "/")
    }

    private func navigate(_ key: String) {
        switch key {
        case "live":   content.load(BASE + "/")
        case "sq2":    content.load(BASE + "/ui/sq2/")
        case "replay": content.load(BASE + "/?replay=ui/fixture/br02&speed=8")
        default: break
        }
    }

    private func forge(_ goal: String) {
        let t = goal.isEmpty ? TASKS[1] : closestTask(goal)
        procs.startJob(taskID: t.id)
        sidebar.statusLabel.stringValue = "forging \(t.id)"
        sidebar.select("live")
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) { self.content.load(BASE + "/") }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ n: Notification) { procs.shutdown() }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
