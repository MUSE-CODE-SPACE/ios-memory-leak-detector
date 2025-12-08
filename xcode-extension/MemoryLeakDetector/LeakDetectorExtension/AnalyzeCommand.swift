import Foundation
import XcodeKit

class AnalyzeCommand: NSObject, XCSourceEditorCommand {

    func perform(with invocation: XCSourceEditorCommandInvocation, completionHandler: @escaping (Error?) -> Void) {
        let buffer = invocation.buffer
        let lines = buffer.lines as! [String]
        let content = lines.joined(separator: "\n")

        // Determine file type
        let uti = buffer.contentUTI
        let isSwift = uti.contains("swift")
        let isObjC = uti.contains("objective-c") || uti.contains("objc")

        var issues: [LeakIssue] = []

        if isSwift {
            issues = analyzeSwift(content: content)
        } else if isObjC {
            issues = analyzeObjC(content: content)
        }

        if issues.isEmpty {
            // No issues found - add comment at top
            buffer.lines.insert("// No memory leak issues detected", at: 0)
        } else {
            // Add comments for each issue
            var insertedLines = 0
            for issue in issues.sorted(by: { $0.line > $1.line }) {
                let comment = "// WARNING: \(issue.message)"
                let insertIndex = issue.line - 1 + insertedLines
                if insertIndex >= 0 && insertIndex < buffer.lines.count {
                    buffer.lines.insert(comment, at: insertIndex)
                    insertedLines += 1
                }
            }
        }

        completionHandler(nil)
    }

    // MARK: - Swift Analysis

    private func analyzeSwift(content: String) -> [LeakIssue] {
        var issues: [LeakIssue] = []
        let lines = content.components(separatedBy: "\n")

        for (index, line) in lines.enumerated() {
            let lineNum = index + 1

            // Check for closure without [weak self]
            if line.contains("{") && !line.contains("[weak self]") && !line.contains("[unowned self]") {
                // Look ahead for self usage
                let nextLines = lines.dropFirst(index).prefix(10).joined(separator: "\n")
                if nextLines.contains("self.") || nextLines.contains("self?.") {
                    // Check if it's a likely closure
                    if line.contains("=") || line.contains("->") || line.contains("in") {
                        issues.append(LeakIssue(
                            line: lineNum,
                            message: "Closure may capture self strongly. Consider [weak self]"
                        ))
                    }
                }
            }

            // Check for non-weak delegate
            if line.contains("delegate") && line.contains("var") && !line.contains("weak") {
                issues.append(LeakIssue(
                    line: lineNum,
                    message: "Delegate property should be weak to avoid retain cycles"
                ))
            }

            // Check for strong IBOutlet
            if line.contains("@IBOutlet") && !line.contains("weak") {
                issues.append(LeakIssue(
                    line: lineNum,
                    message: "IBOutlet should typically be weak"
                ))
            }

            // Check for Timer without [weak self]
            if line.contains("Timer.") && line.contains("{") && !line.contains("[weak self]") {
                issues.append(LeakIssue(
                    line: lineNum,
                    message: "Timer closure should use [weak self] to avoid retain cycle"
                ))
            }

            // Check for DispatchQueue without [weak self]
            if line.contains("DispatchQueue") && line.contains("{") && !line.contains("[weak self]") {
                let nextLines = lines.dropFirst(index).prefix(5).joined(separator: "\n")
                if nextLines.contains("self.") {
                    issues.append(LeakIssue(
                        line: lineNum,
                        message: "Dispatch block captures self. Consider [weak self]"
                    ))
                }
            }

            // Check for sync on main queue (potential deadlock)
            if line.contains("DispatchQueue.main.sync") {
                issues.append(LeakIssue(
                    line: lineNum,
                    message: "CRITICAL: sync on main queue can cause deadlock"
                ))
            }
        }

        return issues
    }

    // MARK: - Objective-C Analysis

    private func analyzeObjC(content: String) -> [LeakIssue] {
        var issues: [LeakIssue] = []
        let lines = content.components(separatedBy: "\n")

        for (index, line) in lines.enumerated() {
            let lineNum = index + 1

            // Check for block without __weak
            if line.contains("^{") || line.contains("^ {") {
                // Look at surrounding context for __weak declaration
                let prevLines = lines.prefix(index).suffix(5).joined(separator: "\n")
                if !prevLines.contains("__weak") && !prevLines.contains("weakSelf") {
                    let nextLines = lines.dropFirst(index).prefix(5).joined(separator: "\n")
                    if nextLines.contains("self") {
                        issues.append(LeakIssue(
                            line: lineNum,
                            message: "Block captures self without __weak. Add: __weak typeof(self) weakSelf = self;"
                        ))
                    }
                }
            }

            // Check for strong delegate property
            if line.contains("@property") && line.contains("delegate") {
                if line.contains("strong") || (!line.contains("weak") && !line.contains("assign")) {
                    issues.append(LeakIssue(
                        line: lineNum,
                        message: "Delegate property should use weak, not strong"
                    ))
                }
            }

            // Check for strong IBOutlet
            if line.contains("IBOutlet") && line.contains("strong") {
                issues.append(LeakIssue(
                    line: lineNum,
                    message: "IBOutlet should typically be weak"
                ))
            }

            // Check for NSTimer
            if line.contains("NSTimer") && line.contains("scheduledTimer") {
                issues.append(LeakIssue(
                    line: lineNum,
                    message: "NSTimer retains its target. Ensure invalidation in dealloc"
                ))
            }
        }

        return issues
    }
}

struct LeakIssue {
    let line: Int
    let message: String
}
