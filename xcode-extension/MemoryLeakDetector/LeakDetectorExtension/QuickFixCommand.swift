import Foundation
import XcodeKit

class QuickFixCommand: NSObject, XCSourceEditorCommand {

    func perform(with invocation: XCSourceEditorCommandInvocation, completionHandler: @escaping (Error?) -> Void) {
        let buffer = invocation.buffer
        let lines = buffer.lines as! [String]

        // Determine file type
        let uti = buffer.contentUTI
        let isSwift = uti.contains("swift")
        let isObjC = uti.contains("objective-c") || uti.contains("objc")

        var fixCount = 0

        if isSwift {
            fixCount = fixSwift(buffer: buffer, lines: lines)
        } else if isObjC {
            fixCount = fixObjC(buffer: buffer, lines: lines)
        }

        // Add summary comment
        if fixCount > 0 {
            buffer.lines.insert("// Auto-fixed \(fixCount) potential memory leak issue(s)", at: 0)
        } else {
            buffer.lines.insert("// No auto-fixable issues found", at: 0)
        }

        completionHandler(nil)
    }

    // MARK: - Swift Fixes

    private func fixSwift(buffer: XCSourceTextBuffer, lines: [String]) -> Int {
        var fixCount = 0
        let mutableLines = buffer.lines

        for i in (0..<mutableLines.count).reversed() {
            guard let line = mutableLines[i] as? String else { continue }

            // Fix: Add weak to delegate
            if line.contains("var") && line.contains("delegate") && line.contains(":") && !line.contains("weak") {
                let fixed = line.replacingOccurrences(of: "var ", with: "weak var ")
                mutableLines[i] = fixed
                fixCount += 1
            }

            // Fix: Add weak to IBOutlet
            if line.contains("@IBOutlet") && line.contains("var") && !line.contains("weak") {
                let fixed = line.replacingOccurrences(of: "@IBOutlet var", with: "@IBOutlet weak var")
                    .replacingOccurrences(of: "@IBOutlet  var", with: "@IBOutlet weak var")
                mutableLines[i] = fixed
                fixCount += 1
            }

            // Fix: Add [weak self] to closures
            if shouldAddWeakSelf(line: line, lines: lines, index: i) {
                if let range = line.range(of: "{") {
                    var fixed = line
                    let insertIndex = line.index(after: range.lowerBound)
                    fixed.insert(contentsOf: " [weak self] in", at: insertIndex)

                    // Also need to change self. to self?. in the closure
                    mutableLines[i] = fixed
                    fixCount += 1

                    // Fix self references in following lines (simplified)
                    fixSelfReferences(buffer: buffer, startIndex: i + 1)
                }
            }
        }

        return fixCount
    }

    private func shouldAddWeakSelf(line: String, lines: [String], index: Int) -> Bool {
        // Check if this looks like a closure that captures self
        guard line.contains("{") else { return false }
        guard !line.contains("[weak self]") && !line.contains("[unowned self]") else { return false }

        // Skip if it's a class/struct/func definition
        if line.contains("class ") || line.contains("struct ") ||
           line.contains("func ") || line.contains("init(") {
            return false
        }

        // Check for patterns that indicate closures
        let closurePatterns = ["= {", "completion:", "handler:", ".sink", ".map", ".filter",
                               "DispatchQueue", "Timer.", "URLSession", "animate"]

        let hasClosurePattern = closurePatterns.contains { line.contains($0) }
        guard hasClosurePattern else { return false }

        // Check if self is used in the next few lines
        let endIndex = min(index + 10, lines.count)
        for i in index..<endIndex {
            if lines[i].contains("self.") {
                return true
            }
            if lines[i].contains("}") && !lines[i].contains("{") {
                break // End of closure
            }
        }

        return false
    }

    private func fixSelfReferences(buffer: XCSourceTextBuffer, startIndex: Int) {
        // Fix self. to self?. for the next few lines until we hit closing brace
        var braceCount = 1
        for i in startIndex..<buffer.lines.count {
            guard var line = buffer.lines[i] as? String else { continue }

            braceCount += line.components(separatedBy: "{").count - 1
            braceCount -= line.components(separatedBy: "}").count - 1

            if braceCount <= 0 { break }

            // Replace self. with self?.
            if line.contains("self.") && !line.contains("self?.") {
                line = line.replacingOccurrences(of: "self.", with: "self?.")
                buffer.lines[i] = line
            }
        }
    }

    // MARK: - Objective-C Fixes

    private func fixObjC(buffer: XCSourceTextBuffer, lines: [String]) -> Int {
        var fixCount = 0
        let mutableLines = buffer.lines

        for i in (0..<mutableLines.count).reversed() {
            guard let line = mutableLines[i] as? String else { continue }

            // Fix: Change strong delegate to weak
            if line.contains("@property") && line.contains("delegate") && line.contains("strong") {
                let fixed = line.replacingOccurrences(of: "strong", with: "weak")
                mutableLines[i] = fixed
                fixCount += 1
            }

            // Fix: Change strong IBOutlet to weak
            if line.contains("@property") && line.contains("IBOutlet") && line.contains("strong") {
                let fixed = line.replacingOccurrences(of: "strong", with: "weak")
                mutableLines[i] = fixed
                fixCount += 1
            }

            // Fix: Add __weak self before block
            if (line.contains("^{") || line.contains("^ {")) && !hasWeakSelfDeclaration(lines: lines, beforeIndex: i) {
                // Check if self is used
                if usesSelfinBlock(lines: lines, startIndex: i) {
                    // Insert __weak declaration before this line
                    let indent = String(line.prefix(while: { $0 == " " || $0 == "\t" }))
                    let weakDecl = "\(indent)__weak typeof(self) weakSelf = self;"
                    mutableLines.insert(weakDecl, at: i)
                    fixCount += 1

                    // Also replace self with weakSelf in the block
                    fixObjCSelfReferences(buffer: buffer, startIndex: i + 1)
                }
            }
        }

        return fixCount
    }

    private func hasWeakSelfDeclaration(lines: [String], beforeIndex: Int) -> Bool {
        let startIndex = max(0, beforeIndex - 5)
        for i in startIndex..<beforeIndex {
            if lines[i].contains("__weak") && lines[i].contains("weakSelf") {
                return true
            }
        }
        return false
    }

    private func usesSelfinBlock(lines: [String], startIndex: Int) -> Bool {
        var braceCount = 0
        for i in startIndex..<min(startIndex + 15, lines.count) {
            let line = lines[i]
            braceCount += line.components(separatedBy: "{").count - 1
            braceCount -= line.components(separatedBy: "}").count - 1

            if line.contains("[self ") || (line.contains("self.") && !line.contains("weakSelf")) {
                return true
            }

            if braceCount <= 0 { break }
        }
        return false
    }

    private func fixObjCSelfReferences(buffer: XCSourceTextBuffer, startIndex: Int) {
        var braceCount = 1
        for i in startIndex..<buffer.lines.count {
            guard var line = buffer.lines[i] as? String else { continue }

            braceCount += line.components(separatedBy: "{").count - 1
            braceCount -= line.components(separatedBy: "}").count - 1

            if braceCount <= 0 { break }

            // Replace self with weakSelf
            if line.contains("[self ") {
                line = line.replacingOccurrences(of: "[self ", with: "[weakSelf ")
                buffer.lines[i] = line
            }
            if line.contains("self.") && !line.contains("weakSelf") {
                line = line.replacingOccurrences(of: "self.", with: "weakSelf.")
                buffer.lines[i] = line
            }
        }
    }
}
