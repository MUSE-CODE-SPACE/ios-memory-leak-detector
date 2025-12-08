"""
Command Line Interface for iOS Memory Leak Detector
"""

import argparse
import sys
import os
from pathlib import Path

from .analyzer import MemoryLeakAnalyzer
from .reporter import Reporter
from . import __version__


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog='ios-leak-detector',
        description='Detect memory leaks and performance issues in iOS projects (Swift, SwiftUI, Objective-C)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  ios-leak-detector /path/to/ios/project
  ios-leak-detector . --format html --output report.html
  ios-leak-detector src/ --severity high --verbose
  ios-leak-detector MyApp.xcodeproj --exclude Pods --json

Supported file types:
  - Swift (.swift)
  - Objective-C (.m, .mm)
  - Headers (.h)

Detection includes:
  - Strong reference cycles
  - Missing [weak self] in closures
  - Non-weak delegates
  - Unremoved timers/observers
  - Main thread performance issues
  - SwiftUI-specific patterns
        '''
    )

    parser.add_argument(
        'path',
        help='Path to iOS project directory or file to analyze'
    )

    parser.add_argument(
        '-o', '--output',
        help='Output file path for report'
    )

    parser.add_argument(
        '-f', '--format',
        choices=['console', 'json', 'html', 'markdown'],
        default='console',
        help='Output format (default: console)'
    )

    parser.add_argument(
        '-s', '--severity',
        choices=['critical', 'high', 'medium', 'low', 'info'],
        default='info',
        help='Minimum severity level to report (default: info)'
    )

    parser.add_argument(
        '--exclude',
        nargs='+',
        default=[],
        help='Directories to exclude (e.g., --exclude Pods Carthage)'
    )

    parser.add_argument(
        '--no-swiftui',
        action='store_true',
        help='Disable SwiftUI-specific pattern detection'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed output including code snippets'
    )

    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )

    parser.add_argument(
        '-j', '--json',
        action='store_true',
        help='Output as JSON (shortcut for --format json)'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of parallel workers (default: 4)'
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'ios-leak-detector {__version__}'
    )

    parser.add_argument(
        '--list-patterns',
        action='store_true',
        help='List all detection patterns and exit'
    )

    args = parser.parse_args()

    # List patterns mode
    if args.list_patterns:
        _list_patterns()
        return 0

    # Validate path
    target_path = Path(args.path)
    if not target_path.exists():
        print(f"Error: Path does not exist: {args.path}", file=sys.stderr)
        return 1

    # Determine project name
    if target_path.is_file():
        project_name = target_path.parent.name
    else:
        project_name = target_path.name

    # Build configuration
    default_excludes = ['Pods', 'Carthage', '.build', 'DerivedData', 'build', '.git']
    exclude_dirs = list(set(default_excludes + args.exclude))

    config = {
        'exclude_dirs': exclude_dirs,
        'severity_threshold': args.severity,
        'include_swiftui': not args.no_swiftui,
        'max_workers': args.workers
    }

    # Run analysis
    try:
        analyzer = MemoryLeakAnalyzer(config)

        print(f"🔍 Analyzing: {args.path}")
        print(f"   Severity threshold: {args.severity}")
        print(f"   Excluding: {', '.join(exclude_dirs)}")
        print()

        if target_path.is_file():
            issues = analyzer.analyze_file(str(target_path))
            # Create a simple result for single file
            from .analyzer import AnalysisResult
            result = AnalysisResult()
            result.total_files = 1
            result.swift_files = 1 if target_path.suffix == '.swift' else 0
            result.objc_files = 1 if target_path.suffix in ('.m', '.mm') else 0
            result.issues = issues
            result.total_issues = len(issues)
            for issue in issues:
                sev = issue.severity.value
                typ = issue.type.value
                result.severity_counts[sev] = result.severity_counts.get(sev, 0) + 1
                result.type_counts[typ] = result.type_counts.get(typ, 0) + 1
        else:
            result = analyzer.analyze_directory(str(target_path))

        # Generate report
        reporter = Reporter(result, project_name)

        output_format = 'json' if args.json else args.format

        if output_format == 'console':
            reporter.print_console(verbose=args.verbose, no_color=args.no_color)

        elif output_format == 'json':
            output_path = args.output or f"{project_name}_leak_report.json"
            json_str = reporter.to_json(output_path)
            if not args.output:
                print(json_str)

        elif output_format == 'html':
            output_path = args.output or f"{project_name}_leak_report.html"
            reporter.to_html(output_path)

        elif output_format == 'markdown':
            output_path = args.output or f"{project_name}_leak_report.md"
            md_str = reporter.to_markdown(output_path)
            if not args.output:
                print(md_str)

        # Return exit code based on issues found
        critical_count = result.severity_counts.get('critical', 0)
        high_count = result.severity_counts.get('high', 0)

        if critical_count > 0:
            return 2  # Critical issues
        elif high_count > 0:
            return 1  # High severity issues
        return 0  # Success

    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def _list_patterns():
    """Print all available detection patterns."""
    from .patterns import (
        SWIFT_PATTERNS, SWIFTUI_PATTERNS, OBJC_PATTERNS, PERFORMANCE_PATTERNS
    )

    print("\n🔍 iOS Memory Leak Detection Patterns\n")
    print("=" * 60)

    print("\n📱 Swift Patterns:")
    print("-" * 40)
    for name, data in SWIFT_PATTERNS.items():
        print(f"  • {name}")
        print(f"    Severity: {data['severity'].value}")
        print(f"    {data['message']}")
        print()

    print("\n🎨 SwiftUI Patterns:")
    print("-" * 40)
    for name, data in SWIFTUI_PATTERNS.items():
        print(f"  • {name}")
        print(f"    Severity: {data['severity'].value}")
        print(f"    {data['message']}")
        print()

    print("\n📦 Objective-C Patterns:")
    print("-" * 40)
    for name, data in OBJC_PATTERNS.items():
        print(f"  • {name}")
        print(f"    Severity: {data['severity'].value}")
        print(f"    {data['message']}")
        print()

    print("\n⚡ Performance Patterns:")
    print("-" * 40)
    for name, data in PERFORMANCE_PATTERNS.items():
        print(f"  • {name}")
        print(f"    Severity: {data['severity'].value}")
        print(f"    {data['message']}")
        print()


if __name__ == '__main__':
    sys.exit(main())
