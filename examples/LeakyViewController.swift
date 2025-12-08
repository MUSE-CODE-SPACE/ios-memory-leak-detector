// Example Swift file with common memory leak patterns
// Used for testing ios-leak-detector

import UIKit

protocol MyDelegate: AnyObject {
    func didComplete()
}

class LeakyViewController: UIViewController {

    // ❌ Non-weak delegate - LEAK!
    var delegate: MyDelegate?

    // ❌ Strong IBOutlet - should be weak
    @IBOutlet var headerLabel: UILabel!

    // ✅ Correct - weak IBOutlet
    @IBOutlet weak var footerLabel: UILabel?

    // Timer that may cause leak
    var timer: Timer?

    // Closure that captures self strongly
    var completionHandler: (() -> Void)?

    override func viewDidLoad() {
        super.viewDidLoad()

        // ❌ Closure captures self without [weak self]
        completionHandler = {
            self.updateUI()
        }

        // ❌ Timer without proper cleanup
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
            self.tick()
        }

        // ❌ NotificationCenter observer without removal
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleNotification),
            name: .someNotification,
            object: nil
        )

        // ❌ Dispatch async captures self strongly
        DispatchQueue.main.async {
            self.updateUI()
        }
    }

    @objc func handleNotification() {
        print("Notification received")
    }

    func tick() {
        print("Timer tick")
    }

    func updateUI() {
        headerLabel.text = "Updated"
    }

    // ❌ No deinit - can't verify cleanup
}

extension Notification.Name {
    static let someNotification = Notification.Name("someNotification")
}


// ===== FIXED VERSION =====

class FixedViewController: UIViewController {

    // ✅ Weak delegate
    weak var delegate: MyDelegate?

    // ✅ Weak IBOutlet
    @IBOutlet weak var headerLabel: UILabel?

    // Timer reference for cleanup
    var timer: Timer?

    // Closure with weak self
    var completionHandler: (() -> Void)?

    override func viewDidLoad() {
        super.viewDidLoad()

        // ✅ Closure with [weak self]
        completionHandler = { [weak self] in
            self?.updateUI()
        }

        // ✅ Timer with weak self
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.tick()
        }

        // ✅ Observer will be removed in deinit
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleNotification),
            name: .someNotification,
            object: nil
        )

        // ✅ Dispatch with weak self
        DispatchQueue.main.async { [weak self] in
            self?.updateUI()
        }
    }

    @objc func handleNotification() {
        print("Notification received")
    }

    func tick() {
        print("Timer tick")
    }

    func updateUI() {
        headerLabel?.text = "Updated"
    }

    // ✅ Proper cleanup in deinit
    deinit {
        timer?.invalidate()
        timer = nil
        NotificationCenter.default.removeObserver(self)
        print("\(type(of: self)) deallocated")
    }
}
