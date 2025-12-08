"""
iOS Memory Leak Detector v2.0

A powerful static analysis tool for detecting memory leaks and performance issues
in iOS projects (Swift, SwiftUI, Objective-C).

Features:
- Detect strong reference cycles and retain cycles
- Find missing [weak self] in closures and blocks
- Identify non-weak delegates
- Check for unremoved timers and observers
- Analyze SwiftUI-specific patterns
- Main thread performance analysis
- Auto-fix suggestions with diff preview
- Multiple output formats (console, JSON, HTML, Markdown)

Usage:
    from ios_leak_detector import MemoryLeakAnalyzer

    analyzer = MemoryLeakAnalyzer()
    result = analyzer.analyze_directory('/path/to/ios/project')

    for issue in result.issues:
        print(f"{issue.severity}: {issue.message}")
        print(f"  File: {issue.file_path}:{issue.line_number}")
        if issue.fix:
            print(f"  Fix: {issue.fix.description}")
"""

__version__ = "2.0.0"
__author__ = "yoon-k"
__license__ = "MIT"

from .analyzer import MemoryLeakAnalyzer, AnalysisResult
from .patterns import (
    LeakPattern,
    LeakType,
    LeakSeverity,
    FixSuggestion,
    SWIFT_PATTERNS,
    SWIFTUI_PATTERNS,
    OBJC_PATTERNS,
    PERFORMANCE_PATTERNS
)
from .fixer import CodeFixer, FileFix, SwiftFixer, ObjCFixer
from .reporter import Reporter

__all__ = [
    # Core classes
    'MemoryLeakAnalyzer',
    'AnalysisResult',
    'Reporter',

    # Pattern types
    'LeakPattern',
    'LeakType',
    'LeakSeverity',
    'FixSuggestion',

    # Fix classes
    'CodeFixer',
    'FileFix',
    'SwiftFixer',
    'ObjCFixer',

    # Pattern dictionaries
    'SWIFT_PATTERNS',
    'SWIFTUI_PATTERNS',
    'OBJC_PATTERNS',
    'PERFORMANCE_PATTERNS',
]
