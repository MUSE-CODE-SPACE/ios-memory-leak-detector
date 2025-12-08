// Example SwiftUI file with common issues
// Used for testing ios-leak-detector

import SwiftUI
import Combine

// ❌ ViewModel with potential retain cycle
class LeakyViewModel: ObservableObject {
    @Published var items: [String] = []
    var cancellables = Set<AnyCancellable>()

    init() {
        // ❌ Closure captures self strongly
        fetchData { result in
            self.items = result
        }

        // ❌ Sink without [weak self] - potential retain cycle
        Timer.publish(every: 1, on: .main, in: .common)
            .autoconnect()
            .sink { _ in
                self.tick()
            }
            .store(in: &cancellables)
    }

    func fetchData(completion: @escaping ([String]) -> Void) {
        // Simulated network call
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
            completion(["Item 1", "Item 2"])
        }
    }

    func tick() {
        print("Tick")
    }
}

// ❌ View with issues
struct LeakyView: View {
    @StateObject var viewModel = LeakyViewModel()

    var body: some View {
        // ❌ Heavy computation in body
        let _ = (0..<1000).map { $0 * 2 }

        VStack {
            // ❌ Synchronous image loading
            Image(uiImage: UIImage(named: "large_image")!)

            ForEach(viewModel.items, id: \.self) { item in
                Text(item)
            }
        }
        .onAppear {
            // ❌ Network in onAppear without cancellation handling
            URLSession.shared.dataTask(with: URL(string: "https://api.example.com")!) { _, _, _ in
                // Handle response
            }.resume()
        }
    }
}


// ===== FIXED VERSION =====

// ✅ ViewModel with proper memory management
class FixedViewModel: ObservableObject {
    @Published var items: [String] = []
    private var cancellables = Set<AnyCancellable>()

    init() {
        // ✅ Closure with [weak self]
        fetchData { [weak self] result in
            self?.items = result
        }

        // ✅ Sink with [weak self]
        Timer.publish(every: 1, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                self?.tick()
            }
            .store(in: &cancellables)
    }

    func fetchData(completion: @escaping ([String]) -> Void) {
        DispatchQueue.global().async {
            // Background processing
            let result = ["Item 1", "Item 2"]
            DispatchQueue.main.async {
                completion(result)
            }
        }
    }

    func tick() {
        print("Tick")
    }

    deinit {
        print("\(type(of: self)) deallocated")
    }
}

// ✅ View with proper patterns
struct FixedView: View {
    @StateObject private var viewModel = FixedViewModel()
    @State private var loadedImage: UIImage?

    var body: some View {
        VStack {
            // ✅ Async image loading
            if let image = loadedImage {
                Image(uiImage: image)
            } else {
                ProgressView()
            }

            ForEach(viewModel.items, id: \.self) { item in
                Text(item)
            }
        }
        .task {
            // ✅ Async task with proper cancellation
            await loadImage()
        }
    }

    private func loadImage() async {
        // Check for cancellation
        guard !Task.isCancelled else { return }

        // Load image in background
        if let url = URL(string: "https://example.com/image.jpg"),
           let data = try? await URLSession.shared.data(from: url).0,
           let image = UIImage(data: data) {
            await MainActor.run {
                loadedImage = image
            }
        }
    }
}
