"""
Command Line Interface for iOS Memory Leak Detector
Enhanced with --fix, --diff, and advanced options
"""

import argparse
import sys
import os
from pathlib import Path

from .analyzer import MemoryLeakAnalyzer
from .reporter import Reporter
from .fixer import CodeFixer, apply_all_fixes
from . import __version__


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog='ios-leak-detector',
        description='Detect memory leaks and performance issues in iOS projects (Swift, SwiftUI, Objective-C)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic analysis
  ios-leak-detector /path/to/ios/project

  # Verbose with code snippets and fixes
  ios-leak-detector . --verbose

  # Show diff of suggested fixes
  ios-leak-detector src/ --diff

  # Apply auto-fixes (creates backups)
  ios-leak-detector src/ --fix

  # Generate HTML report
  ios-leak-detector . --format html --output report.html

  # Only high severity issues
  ios-leak-detector MyApp.xcodeproj --severity high

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

Fix modes:
  --fix       Apply auto-fixable changes (with backup)
  --diff      Show diff of proposed changes (dry-run)
  --fix-all   Apply all fixes including manual ones (interactive)
        '''
    )

    parser.add_argument(
        'path',
        help='Path to iOS project directory or file to analyze'
    )

    # Output options
    output_group = parser.add_argument_group('Output options')
    output_group.add_argument(
        '-o', '--output',
        help='Output file path for report'
    )
    output_group.add_argument(
        '-f', '--format',
        choices=['console', 'json', 'html', 'markdown'],
        default='console',
        help='Output format (default: console)'
    )
    output_group.add_argument(
        '-j', '--json',
        action='store_true',
        help='Output as JSON (shortcut for --format json)'
    )

    # Fix options
    fix_group = parser.add_argument_group('Fix options')
    fix_group.add_argument(
        '--fix',
        action='store_true',
        help='Apply auto-fixable changes to files (creates backups)'
    )
    fix_group.add_argument(
        '--diff',
        action='store_true',
        help='Show diff of proposed fixes without applying them'
    )
    fix_group.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip backup creation when using --fix'
    )

    # Filter options
    filter_group = parser.add_argument_group('Filter options')
    filter_group.add_argument(
        '-s', '--severity',
        choices=['critical', 'high', 'medium', 'low', 'info'],
        default='info',
        help='Minimum severity level to report (default: info)'
    )
    filter_group.add_argument(
        '--exclude',
        nargs='+',
        default=[],
        help='Directories to exclude (e.g., --exclude Pods Carthage)'
    )
    filter_group.add_argument(
        '--no-swiftui',
        action='store_true',
        help='Disable SwiftUI-specific pattern detection'
    )

    # Display options
    display_group = parser.add_argument_group('Display options')
    display_group.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed output including code snippets and fixes'
    )
    display_group.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    display_group.add_argument(
        '--no-fixes',
        action='store_true',
        help='Hide fix suggestions in output'
    )

    # Performance options
    perf_group = parser.add_argument_group('Performance options')
    perf_group.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of parallel workers (default: 4)'
    )

    # Info options
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
            result.fixable_issues = sum(1 for i in issues if i.fix and i.fix.is_auto_fixable)
            for issue in issues:
                sev = issue.severity.value
                typ = issue.type.value
                result.severity_counts[sev] = result.severity_counts.get(sev, 0) + 1
                result.type_counts[typ] = result.type_counts.get(typ, 0) + 1
        else:
            result = analyzer.analyze_directory(str(target_path))

        # Handle diff mode
        if args.diff:
            _show_diff(result, args.no_color)
            return 0

        # Handle fix mode
        if args.fix:
            return _apply_fixes(result, args.no_backup, args.verbose)

        # Generate report
        reporter = Reporter(result, project_name)
        output_format = 'json' if args.json else args.format

        if output_format == 'console':
            reporter.print_console(
                verbose=args.verbose,
                no_color=args.no_color,
                show_fixes=not args.no_fixes
            )

        elif output_format == 'json':
            output_path = args.output or f"{project_name}_leak_report.json"
            json_str = reporter.to_json(output_path if args.output else None)
            if not args.output:
                print(json_str)

        elif output_format == 'html':
            output_path = args.output or f"{project_name}_leak_report.html"
            reporter.to_html(output_path)

        elif output_format == 'markdown':
            output_path = args.output or f"{project_name}_leak_report.md"
            md_str = reporter.to_markdown(output_path if args.output else None)
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


def _show_diff(result, no_color: bool = False):
    """Show diff of proposed fixes."""
    from .fixer import CodeFixer

    fixer = CodeFixer(dry_run=True, backup=False)

    # Group issues by file
    issues_by_file = result.get_issues_by_file()

    total_fixes = 0

    print("\n📋 Proposed Fixes (Dry Run)\n")
    print("=" * 70)

    for file_path, issues in issues_by_file.items():
        file_fix = fixer.fix_file(file_path, issues)

        if file_fix.has_changes():
            # Get relative path
            parts = Path(file_path).parts
            rel_path = '/'.join(parts[-3:]) if len(parts) > 3 else file_path

            print(f"\n📄 {rel_path}")
            print(f"   Fixes: {len(file_fix.fixes)}")
            print("-" * 50)

            diff = fixer.generate_diff_output([file_fix], colored=not no_color)
            print(diff)

            total_fixes += len(file_fix.fixes)

    if total_fixes == 0:
        print("\n✅ No auto-fixable issues found.")
    else:
        print(f"\n📊 Total: {total_fixes} fixes available")
        print("💡 Run with --fix to apply these changes")


def _apply_fixes(result, no_backup: bool, verbose: bool):
    """Apply auto-fixes to files."""
    from .fixer import CodeFixer

    fixable = result.get_fixable_issues()

    if not fixable:
        print("✅ No auto-fixable issues found.")
        return 0

    print(f"🔧 Found {len(fixable)} auto-fixable issues")

    if not no_backup:
        print("📦 Creating backups before applying fixes...")

    fixer = CodeFixer(dry_run=False, backup=not no_backup)

    # Group issues by file
    issues_by_file = result.get_issues_by_file()

    file_fixes = []
    for file_path, issues in issues_by_file.items():
        file_fix = fixer.fix_file(file_path, issues)
        if file_fix.has_changes():
            file_fixes.append(file_fix)

    if not file_fixes:
        print("✅ No changes to apply.")
        return 0

    # Apply fixes
    summary = fixer.apply_fixes(file_fixes)

    print()
    print("=" * 50)
    print(f"✅ Applied {summary['fixes_applied']} fixes to {summary['files_modified']} files")

    if summary['backups_created']:
        print(f"\n📦 Backups created in:")
        for backup in summary['backups_created'][:5]:
            print(f"   {backup}")
        if len(summary['backups_created']) > 5:
            print(f"   ... and {len(summary['backups_created']) - 5} more")

    if summary['errors']:
        print(f"\n⚠️  Errors occurred:")
        for error in summary['errors']:
            print(f"   {error['file']}: {error['error']}")
        return 1

    if verbose:
        print("\n📋 Fix Report:")
        report = fixer.generate_fix_report(file_fixes)
        print(report)

    return 0


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
        if 'fix_example' in data:
            print(f"    Auto-fix: Available")
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
        if 'fix_example' in data:
            print(f"    Auto-fix: Available")
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
