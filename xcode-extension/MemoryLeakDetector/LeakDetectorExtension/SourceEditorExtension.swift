import Foundation
import XcodeKit

class SourceEditorExtension: NSObject, XCSourceEditorExtension {

    func extensionDidFinishLaunching() {
        // Extension launched
    }

    var commandDefinitions: [[XCSourceEditorCommandDefinitionKey: Any]] {
        return [
            [
                .classNameKey: "LeakDetectorExtension.AnalyzeCommand",
                .identifierKey: "com.yoonk.leak-detector.analyze",
                .nameKey: "Analyze for Memory Leaks"
            ],
            [
                .classNameKey: "LeakDetectorExtension.QuickFixCommand",
                .identifierKey: "com.yoonk.leak-detector.quickfix",
                .nameKey: "Quick Fix Leaks"
            ]
        ]
    }
}
