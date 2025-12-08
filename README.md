# iOS Memory Leak Detector 🔍

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)]()
[![Version](https://img.shields.io/badge/Version-2.0.0-orange.svg)]()

A powerful static analysis tool to detect memory leaks, retain cycles, and performance issues in iOS projects. Supports **Swift**, **SwiftUI**, and **Objective-C**.

## ✨ What's New in v2.0

- 🔧 **Auto-Fix Suggestions**: Get exact code fixes with before/after diff
- 📍 **Precise Locations**: Line and column numbers for IDE integration
- 🔄 **--fix Mode**: Apply auto-fixable changes with backup
- 📋 **--diff Mode**: Preview changes before applying
- 📊 **Fixable Count**: See how many issues can be auto-fixed

## Features

### 🔍 Memory Leak Detection

| Category | Swift | SwiftUI | Objective-C |
|----------|:-----:|:-------:|:-----------:|
| Strong reference cycles | ✅ | ✅ | ✅ |
| Missing `[weak self]` in closures | ✅ | ✅ | - |
| Block retain cycles | - | - | ✅ |
| Non-weak delegates | ✅ | ✅ | ✅ |
| Unremoved timers | ✅ | ✅ | ✅ |
| Unremoved notification observers | ✅ | ✅ | ✅ |
| KVO not removed | ✅ | - | ✅ |
| Missing `deinit`/`dealloc` | ✅ | - | ✅ |
| Strong IBOutlet | ✅ | - | ✅ |

### 🎨 SwiftUI-Specific Detection

- `@StateObject` misuse
- `@ObservedObject` reference cycles
- Combine sink without storing cancellable
- ViewModel closure capture issues
- Timer publisher lifecycle issues
- Async task cancellation checks

### ⚡ Performance Issue Detection

- Main thread blocking operations
- Synchronous dispatch to main queue (deadlock risk)
- Heavy computation on main thread
- Synchronous network calls
- Large image processing on main thread
- Core Data operations on main context

### 🔧 Auto-Fix Support (NEW in v2.0)

| Issue Type | Auto-fixable |
|------------|:------------:|
| Missing `[weak self]` | ✅ |
| Non-weak delegate | ✅ |
| Strong IBOutlet | ✅ |
| Dispatch without weak self | ✅ |
| Block without __weak (Obj-C) | ✅ |
| Combine sink without store | ✅ |
| Sync main dispatch | ✅ |

## Installation

### Using pip

```bash
pip install ios-leak-detector
```

### From source

```bash
git clone https://github.com/yoon-k/ios-memory-leak-detector.git
cd ios-memory-leak-detector
pip install -e .
```

## Web UI (New!)

A beautiful web interface is available for browser-based analysis:

```bash
# Start the web UI
./run_web.sh

# Or with Python directly
python web_app.py

# Custom port
python web_app.py --port 8080
```

The web UI automatically opens at `http://localhost:5050` with features:
- Visual project analysis with severity filtering
- Real-time issue display with code snippets
- One-click fix preview and apply
- Export reports in HTML/JSON/Markdown formats
- All detection patterns in one view

## Quick Start

### Basic Analysis

```bash
# Analyze entire iOS project
ios-leak-detector /path/to/MyApp.xcodeproj

# Analyze with verbose output (shows code and fixes)
ios-leak-detector /path/to/MyApp --verbose
```

### Preview Fixes (--diff)

```bash
# See what changes would be made without applying them
ios-leak-detector MyApp/ --diff
```

Output:
```diff
📄 ViewControllers/HomeViewController.swift
   Fixes: 3
--------------------------------------------------
--- a/HomeViewController.swift
+++ b/HomeViewController.swift
@@ -45,6 +45,6 @@
-    completionHandler = {
-        self.updateUI()
+    completionHandler = { [weak self] in
+        self?.updateUI()
     }
```

### Apply Fixes (--fix)

```bash
# Apply auto-fixable changes (creates backups automatically)
ios-leak-detector MyApp/ --fix

# Apply without backup (use with caution)
ios-leak-detector MyApp/ --fix --no-backup
```

Output:
```
🔧 Found 12 auto-fixable issues
📦 Creating backups before applying fixes...

==================================================
✅ Applied 12 fixes to 5 files

📦 Backups created in:
   .leak_detector_backups/HomeViewController.swift.20241208_143022.bak
   ...
```

### Output Formats

```bash
# Console output (default) with fixes shown
ios-leak-detector MyApp/

# JSON report with fix details
ios-leak-detector MyApp/ --format json --output report.json

# HTML report (beautiful web page)
ios-leak-detector MyApp/ --format html --output report.html

# Markdown report
ios-leak-detector MyApp/ --format markdown --output report.md
```

### Filter Options

```bash
# Only critical and high severity issues
ios-leak-detector MyApp/ --severity high

# Exclude directories
ios-leak-detector MyApp/ --exclude Pods Generated ThirdParty

# Disable SwiftUI patterns
ios-leak-detector MyApp/ --no-swiftui

# Hide fix suggestions in output
ios-leak-detector MyApp/ --no-fixes
```

## Usage Examples

### Basic Usage Output

```bash
$ ios-leak-detector ./MyiOSApp --verbose

🔍 Analyzing: ./MyiOSApp
   Severity threshold: info
   Excluding: Pods, Carthage, .build, DerivedData

======================================================================
  iOS Memory Leak Analysis Report
  Project: MyiOSApp
======================================================================

📊 Summary
  Files analyzed: 47
    Swift: 42
    Objective-C: 5
    Headers: 3
  Total issues: 31
  Auto-fixable: 17          ← NEW: Shows fixable count
  Analysis time: 0.04s

📈 Issues by Severity
  🟠 HIGH: 15
  🟡 MEDIUM: 10
  🟢 LOW: 3
  ℹ️ INFO: 3

🔍 Detailed Issues
----------------------------------------------------------------------

📄 ViewControllers/HomeViewController.swift

  🟠 [HIGH] Line 45:5
  ⚠️ Closure captures 'self' without [weak self] or [unowned self]
  💡 Add [weak self] at the start of the closure

  Code:
      43 |
      44 |     // Setup completion handler
  >>> 45 |     completionHandler = {
      46 |         self.updateUI()
      47 |     }

  🔧 Fix (✓ Auto-fixable):              ← NEW: Shows exact fix
  Before:
    - completionHandler = {
    -     self.updateUI()
  After:
    + completionHandler = { [weak self] in
    +     self?.updateUI()
```

### Python API

```python
from ios_leak_detector import MemoryLeakAnalyzer, Reporter, CodeFixer

# Create analyzer with configuration
analyzer = MemoryLeakAnalyzer({
    'exclude_dirs': ['Pods', 'Carthage'],
    'severity_threshold': 'medium',
    'include_swiftui': True
})

# Analyze project
result = analyzer.analyze_directory('/path/to/project')

# Print summary
print(f"Total issues: {result.total_issues}")
print(f"Auto-fixable: {result.fixable_issues}")

# Generate reports
reporter = Reporter(result, 'MyApp')
reporter.print_console(verbose=True)
reporter.to_html('report.html')

# Access fix suggestions
for issue in result.issues:
    print(f"{issue.file_path}:{issue.line_number}:{issue.column}")
    print(f"  {issue.message}")
    if issue.fix:
        print(f"  Fix: {issue.fix.description}")
        print(f"  Before: {issue.fix.original_code}")
        print(f"  After: {issue.fix.fixed_code}")

# Apply fixes programmatically
fixer = CodeFixer(dry_run=False, backup=True)
issues_by_file = result.get_issues_by_file()
for file_path, issues in issues_by_file.items():
    file_fix = fixer.fix_file(file_path, issues)
    if file_fix.has_changes():
        print(file_fix.get_diff())  # Show diff
```

## Detection Patterns

### Swift Patterns

| Pattern | Severity | Auto-fix | Description |
|---------|----------|:--------:|-------------|
| `closure_self_capture` | HIGH | ✅ | Closure captures `self` without `[weak self]` |
| `non_weak_delegate` | HIGH | ✅ | Delegate property not declared as `weak` |
| `strong_iboutlet` | MEDIUM | ✅ | IBOutlet not declared as weak |
| `timer_creation` | HIGH | ✅ | Timer closure captures self strongly |
| `dispatch_async_self` | MEDIUM | ✅ | Dispatch block captures self |
| `notification_observer` | MEDIUM | - | NotificationCenter observer without removal |

### SwiftUI Patterns

| Pattern | Severity | Auto-fix | Description |
|---------|----------|:--------:|-------------|
| `viewmodel_closure_self` | HIGH | ✅ | ViewModel closure captures self strongly |
| `combine_sink_no_store` | HIGH | ✅ | Sink without storing cancellable |
| `network_in_body` | HIGH | - | Network call in View body |
| `heavy_body_computation` | HIGH | - | Loop in View body |
| `swiftui_timer` | LOW | - | Timer publisher lifecycle |

### Objective-C Patterns

| Pattern | Severity | Auto-fix | Description |
|---------|----------|:--------:|-------------|
| `block_self_capture` | HIGH | ✅ | Block captures `self` without `__weak` |
| `non_weak_delegate_objc` | HIGH | ✅ | Delegate not declared weak |
| `strong_iboutlet_objc` | MEDIUM | ✅ | IBOutlet not weak |
| `kvo_objc` | HIGH | - | KVO observer not removed |
| `nstimer_creation` | HIGH | - | NSTimer without invalidation |

### Performance Patterns

| Pattern | Severity | Auto-fix | Description |
|---------|----------|:--------:|-------------|
| `sync_main_dispatch` | CRITICAL | ✅ | Synchronous dispatch to main (deadlock!) |
| `heavy_main_thread` | HIGH | - | Loop in main dispatch |
| `sync_network` | HIGH | - | Synchronous network call |

### List all patterns

```bash
ios-leak-detector --list-patterns
```

## CLI Reference

```
ios-leak-detector [OPTIONS] PATH

Arguments:
  PATH                      Path to iOS project or file

Output options:
  -o, --output PATH         Output file path
  -f, --format FORMAT       Output format: console, json, html, markdown
  -j, --json                Output as JSON (shortcut)

Fix options:
  --fix                     Apply auto-fixable changes
  --diff                    Show diff of proposed fixes
  --no-backup               Skip backup creation with --fix

Filter options:
  -s, --severity LEVEL      Minimum severity: critical, high, medium, low, info
  --exclude DIR [DIR ...]   Directories to exclude
  --no-swiftui              Disable SwiftUI patterns

Display options:
  -v, --verbose             Show code snippets and detailed fixes
  --no-color                Disable colored output
  --no-fixes                Hide fix suggestions

Other:
  --workers N               Parallel workers (default: 4)
  --list-patterns           List all detection patterns
  --version                 Show version
```

## CI/CD Integration

### GitHub Actions

```yaml
name: iOS Memory Leak Check

on: [push, pull_request]

jobs:
  leak-check:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install ios-leak-detector
        run: pip install ios-leak-detector

      - name: Run memory leak analysis
        run: |
          ios-leak-detector . --severity high --format html --output leak-report.html

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: leak-report
          path: leak-report.html

      - name: Fail on critical issues
        run: ios-leak-detector . --severity critical
```

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: ios-leak-detector
        name: iOS Memory Leak Check
        entry: ios-leak-detector
        args: ['--severity', 'high']
        language: python
        types: [swift]
        pass_filenames: false
```

## Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success, no high/critical issues |
| 1 | High severity issues found |
| 2 | Critical issues found |

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

```bash
git clone https://github.com/yoon-k/ios-memory-leak-detector.git
cd ios-memory-leak-detector
pip install -e ".[dev]"
pytest
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

Created by [yoon-k](https://github.com/yoon-k)

---

**Found a bug or have a feature request?** [Open an issue](https://github.com/yoon-k/ios-memory-leak-detector/issues)
