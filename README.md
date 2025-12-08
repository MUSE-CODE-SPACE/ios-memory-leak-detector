# iOS Memory Leak Detector 🔍

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)]()

A powerful static analysis tool to detect memory leaks, retain cycles, and performance issues in iOS projects. Supports **Swift**, **SwiftUI**, and **Objective-C**.

![Demo](https://via.placeholder.com/800x400?text=iOS+Memory+Leak+Detector+Demo)

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

## Quick Start

### Analyze a project

```bash
# Analyze entire iOS project
ios-leak-detector /path/to/MyApp.xcodeproj

# Analyze specific directory
ios-leak-detector /path/to/MyApp/Sources

# Analyze single file
ios-leak-detector /path/to/ViewController.swift
```

### Output formats

```bash
# Console output (default)
ios-leak-detector MyApp/

# JSON report
ios-leak-detector MyApp/ --format json --output report.json

# HTML report
ios-leak-detector MyApp/ --format html --output report.html

# Markdown report
ios-leak-detector MyApp/ --format markdown --output report.md
```

### Filter by severity

```bash
# Only critical and high severity issues
ios-leak-detector MyApp/ --severity high

# Include all issues (including info)
ios-leak-detector MyApp/ --severity info
```

### Exclude directories

```bash
# Exclude Pods and generated code
ios-leak-detector MyApp/ --exclude Pods Generated ThirdParty
```

## Usage Examples

### Basic Usage

```bash
$ ios-leak-detector ./MyiOSApp

🔍 Analyzing: ./MyiOSApp
   Severity threshold: info
   Excluding: Pods, Carthage, .build, DerivedData

============================================================
  iOS Memory Leak Analysis Report
  Project: MyiOSApp
============================================================

📊 Summary
  Files analyzed: 47
    Swift: 42
    Objective-C: 5
    Headers: 3
  Total issues: 12
  Analysis time: 1.23s

📈 Issues by Severity
  🟠 HIGH: 4
  🟡 MEDIUM: 5
  🟢 LOW: 3

🔍 Detailed Issues
------------------------------------------------------------

📄 ViewControllers/HomeViewController.swift

  🟠 [HIGH] Line 45
  ⚠️ Closure captures 'self' without [weak self] or [unowned self]
  💡 Add [weak self] at the start of the closure

  🟡 [MEDIUM] Line 78
  ⏱️ Timer may not be invalidated in deinit
  💡 Store timer and call timer.invalidate() in deinit
```

### Python API

```python
from ios_leak_detector import MemoryLeakAnalyzer, Reporter

# Create analyzer with configuration
analyzer = MemoryLeakAnalyzer({
    'exclude_dirs': ['Pods', 'Carthage'],
    'severity_threshold': 'medium',
    'include_swiftui': True
})

# Analyze project
result = analyzer.analyze_directory('/path/to/project')

# Generate report
reporter = Reporter(result, 'MyApp')
reporter.print_console(verbose=True)
reporter.to_html('report.html')
reporter.to_json('report.json')

# Access issues programmatically
for issue in result.issues:
    print(f"{issue.file_path}:{issue.line_number} - {issue.message}")
```

## Detection Patterns

### Swift Patterns

| Pattern | Severity | Description |
|---------|----------|-------------|
| `closure_self_capture` | HIGH | Closure captures `self` without `[weak self]` |
| `non_weak_delegate` | HIGH | Delegate property not declared as `weak` |
| `timer_creation` | MEDIUM | Timer created without tracking invalidation |
| `notification_observer` | MEDIUM | NotificationCenter observer without removal |
| `dispatch_async_self` | MEDIUM | Dispatch block captures self strongly |
| `strong_iboutlet` | MEDIUM | IBOutlet not declared as weak |

### SwiftUI Patterns

| Pattern | Severity | Description |
|---------|----------|-------------|
| `viewmodel_closure_self` | HIGH | ViewModel closure captures self strongly |
| `combine_sink_no_store` | HIGH | Sink without storing cancellable |
| `network_in_body` | HIGH | Network call in View body |
| `heavy_body_computation` | HIGH | Loop in View body |
| `swiftui_timer` | LOW | Timer publisher lifecycle |

### Objective-C Patterns

| Pattern | Severity | Description |
|---------|----------|-------------|
| `block_self_capture` | HIGH | Block captures `self` without `__weak` |
| `non_weak_delegate_objc` | HIGH | Delegate not declared weak |
| `kvo_objc` | HIGH | KVO observer not removed |
| `nstimer_creation` | MEDIUM | NSTimer without invalidation |
| `notification_observer_objc` | MEDIUM | Observer not removed |

### List all patterns

```bash
ios-leak-detector --list-patterns
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
          ios-leak-detector . --severity high --format json --output leak-report.json

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: leak-report
          path: leak-report.json

      - name: Fail on critical issues
        run: |
          ios-leak-detector . --severity critical
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

## Configuration

Create `.ios-leak-detector.json` in your project root:

```json
{
  "exclude_dirs": ["Pods", "Carthage", "Generated"],
  "exclude_files": ["*Generated*", "*Mock*"],
  "severity_threshold": "medium",
  "include_swiftui": true,
  "max_workers": 4
}
```

## Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success, no high/critical issues |
| 1 | High severity issues found |
| 2 | Critical issues found |

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

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

Inspired by SwiftLint, Clang Static Analyzer, and the iOS developer community's best practices for memory management.

---

**Found a bug or have a feature request?** [Open an issue](https://github.com/yoon-k/ios-memory-leak-detector/issues)
