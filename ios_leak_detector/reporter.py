"""
Report Generator for Memory Leak Analysis Results
Enhanced with fix suggestions and diff display
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from .analyzer import AnalysisResult
from .patterns import LeakPattern, LeakSeverity, LeakType


class Reporter:
    """Generate reports from analysis results with fix suggestions."""

    SEVERITY_COLORS = {
        "critical": "\033[91m",  # Red
        "high": "\033[93m",      # Yellow
        "medium": "\033[94m",    # Blue
        "low": "\033[92m",       # Green
        "info": "\033[90m",      # Gray
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"

    SEVERITY_ICONS = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
        "info": "ℹ️",
    }

    TYPE_ICONS = {
        LeakType.STRONG_REFERENCE_CYCLE: "🔗",
        LeakType.MISSING_WEAK_SELF: "⚠️",
        LeakType.NON_WEAK_DELEGATE: "📎",
        LeakType.UNREMOVED_OBSERVER: "👁️",
        LeakType.UNREMOVED_TIMER: "⏱️",
        LeakType.RETAIN_CYCLE_BLOCK: "🔄",
        LeakType.MISSING_DEALLOC: "🗑️",
        LeakType.MISSING_DEINIT: "💀",
        LeakType.STRONG_IBOUTLET: "📱",
        LeakType.CLOSURE_CAPTURE: "📦",
        LeakType.DISPATCH_ASYNC_SELF: "🔀",
        LeakType.MAIN_THREAD_HANG: "🐢",
        LeakType.HEAVY_COMPUTATION_MAIN: "💻",
        LeakType.SYNC_MAIN_DISPATCH: "⚡",
    }

    def __init__(self, result: AnalysisResult, project_name: str = "iOS Project"):
        self.result = result
        self.project_name = project_name

    def print_console(self, verbose: bool = False, no_color: bool = False, show_fixes: bool = True):
        """Print report to console."""
        if no_color:
            self._print_console_plain(verbose, show_fixes)
        else:
            self._print_console_colored(verbose, show_fixes)

    def _print_console_colored(self, verbose: bool, show_fixes: bool = True):
        """Print colored console output with fix suggestions."""
        print()
        print(f"{self.BOLD}{'='*70}{self.RESET}")
        print(f"{self.BOLD}  iOS Memory Leak Analysis Report{self.RESET}")
        print(f"{self.BOLD}  Project: {self.project_name}{self.RESET}")
        print(f"{self.BOLD}{'='*70}{self.RESET}")
        print()

        # Summary
        print(f"{self.BOLD}📊 Summary{self.RESET}")
        print(f"  Files analyzed: {self.result.total_files}")
        print(f"    Swift: {self.result.swift_files}")
        print(f"    Objective-C: {self.result.objc_files}")
        print(f"    Headers: {self.result.header_files}")
        print(f"  Total issues: {self.result.total_issues}")
        print(f"  {self.GREEN}Auto-fixable: {self.result.fixable_issues}{self.RESET}")
        print(f"  Analysis time: {self.result.analysis_time:.2f}s")
        print()

        # Severity breakdown
        print(f"{self.BOLD}📈 Issues by Severity{self.RESET}")
        for severity in ["critical", "high", "medium", "low", "info"]:
            count = self.result.severity_counts.get(severity, 0)
            if count > 0:
                color = self.SEVERITY_COLORS.get(severity, "")
                icon = self.SEVERITY_ICONS.get(severity, "")
                print(f"  {icon} {color}{severity.upper()}{self.RESET}: {count}")
        print()

        # Type breakdown
        if self.result.type_counts:
            print(f"{self.BOLD}📋 Issues by Type{self.RESET}")
            sorted_types = sorted(
                self.result.type_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )
            for typ, count in sorted_types[:10]:  # Top 10
                try:
                    icon = self.TYPE_ICONS.get(LeakType(typ), "•")
                except ValueError:
                    icon = "•"
                display_name = typ.replace('_', ' ').title()
                print(f"  {icon} {display_name}: {count}")
            print()

        # Detailed issues
        if self.result.issues:
            print(f"{self.BOLD}🔍 Detailed Issues{self.RESET}")
            print("-" * 70)

            current_file = None
            for issue in self.result.issues:
                # Group by file
                if issue.file_path != current_file:
                    current_file = issue.file_path
                    relative_path = self._get_relative_path(issue.file_path)
                    print(f"\n📄 {self.BOLD}{relative_path}{self.RESET}")

                color = self.SEVERITY_COLORS.get(issue.severity.value, "")
                icon = self.SEVERITY_ICONS.get(issue.severity.value, "")
                type_icon = self.TYPE_ICONS.get(issue.type, "•")

                # Location info
                location_str = f"Line {issue.line_number}"
                if issue.column > 1:
                    location_str += f":{issue.column}"

                print(f"\n  {icon} {color}[{issue.severity.value.upper()}]{self.RESET} "
                      f"{location_str}")
                print(f"  {type_icon} {issue.message}")
                print(f"  💡 {issue.suggestion}")

                # Show code snippet
                if verbose and issue.code_snippet:
                    print(f"\n  {self.DIM}Code:{self.RESET}")
                    for line in issue.code_snippet.split('\n'):
                        if line.startswith('>>>'):
                            print(f"  {self.RED}{line}{self.RESET}")
                        else:
                            print(f"  {self.DIM}{line}{self.RESET}")

                # Show fix suggestion
                if show_fixes and issue.fix:
                    self._print_fix_suggestion(issue.fix, verbose)

        print()
        print(f"{self.BOLD}{'='*70}{self.RESET}")

        # Final verdict
        critical = self.result.severity_counts.get('critical', 0)
        high = self.result.severity_counts.get('high', 0)

        if critical > 0:
            print(f"{self.SEVERITY_COLORS['critical']}⚠️  CRITICAL issues found! "
                  f"Review immediately.{self.RESET}")
        elif high > 0:
            print(f"{self.SEVERITY_COLORS['high']}⚠️  HIGH severity issues found. "
                  f"Please review.{self.RESET}")
        elif self.result.total_issues > 0:
            print(f"{self.SEVERITY_COLORS['low']}✅ No critical issues. "
                  f"Some improvements suggested.{self.RESET}")
        else:
            print(f"{self.SEVERITY_COLORS['low']}✅ No memory leak issues detected!{self.RESET}")

        if self.result.fixable_issues > 0:
            print(f"\n{self.GREEN}💡 {self.result.fixable_issues} issues can be auto-fixed. "
                  f"Run with --fix to apply.{self.RESET}")
        print()

    def _print_fix_suggestion(self, fix, verbose: bool = False):
        """Print a fix suggestion."""
        if not fix.fixed_code:
            return

        fixable = "✓ Auto-fixable" if fix.is_auto_fixable else "Manual fix required"
        print(f"\n  {self.CYAN}🔧 Fix ({fixable}):{self.RESET}")

        if verbose or len(fix.original_code.split('\n')) <= 3:
            # Show full before/after
            print(f"  {self.DIM}Before:{self.RESET}")
            for line in fix.original_code.split('\n')[:5]:
                print(f"    {self.RED}- {line}{self.RESET}")

            print(f"  {self.DIM}After:{self.RESET}")
            for line in fix.fixed_code.split('\n')[:5]:
                print(f"    {self.GREEN}+ {line}{self.RESET}")
        else:
            # Show compact version
            print(f"    {fix.description}")

    def _print_console_plain(self, verbose: bool, show_fixes: bool = True):
        """Print plain text console output (no colors)."""
        print()
        print("=" * 70)
        print("  iOS Memory Leak Analysis Report")
        print(f"  Project: {self.project_name}")
        print("=" * 70)
        print()

        print("Summary:")
        print(f"  Files analyzed: {self.result.total_files}")
        print(f"  Total issues: {self.result.total_issues}")
        print(f"  Auto-fixable: {self.result.fixable_issues}")
        print()

        for issue in self.result.issues:
            location = f"{issue.file_path}:{issue.line_number}"
            if issue.column > 1:
                location += f":{issue.column}"

            print(f"[{issue.severity.value.upper()}] {location}")
            print(f"  {issue.message}")
            print(f"  Suggestion: {issue.suggestion}")

            if verbose and issue.code_snippet:
                print(f"  Code:\n{issue.code_snippet}")

            if show_fixes and issue.fix:
                fixable = "Auto-fixable" if issue.fix.is_auto_fixable else "Manual"
                print(f"  Fix ({fixable}):")
                print(f"    Before: {issue.fix.original_code[:50]}...")
                print(f"    After:  {issue.fix.fixed_code[:50]}...")
            print()

    def to_json(self, output_path: Optional[str] = None) -> str:
        """Generate JSON report with fix suggestions."""
        report = {
            "project": self.project_name,
            "generated_at": datetime.now().isoformat(),
            "analysis": self.result.to_dict()
        }

        json_str = json.dumps(report, indent=2, default=str)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            print(f"JSON report saved to: {output_path}")

        return json_str

    def to_html(self, output_path: str) -> str:
        """Generate HTML report with fix suggestions."""
        html = self._generate_html()

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"HTML report saved to: {output_path}")
        return html

    def to_markdown(self, output_path: Optional[str] = None) -> str:
        """Generate Markdown report with fix suggestions."""
        md = self._generate_markdown()

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(md)
            print(f"Markdown report saved to: {output_path}")

        return md

    def _generate_html(self) -> str:
        """Generate HTML report content with fix suggestions."""
        severity_colors = {
            "critical": "#dc3545",
            "high": "#fd7e14",
            "medium": "#ffc107",
            "low": "#28a745",
            "info": "#6c757d"
        }

        issues_html = ""
        current_file = None

        for issue in self.result.issues:
            if issue.file_path != current_file:
                if current_file:
                    issues_html += "</div>"
                current_file = issue.file_path
                relative_path = self._get_relative_path(issue.file_path)
                issues_html += f'<div class="file-group"><h3>📄 {relative_path}</h3>'

            color = severity_colors.get(issue.severity.value, "#6c757d")
            fix_html = ""

            if issue.fix:
                fixable_badge = '<span class="badge auto-fix">Auto-fixable</span>' if issue.fix.is_auto_fixable else '<span class="badge manual">Manual</span>'
                fix_html = f'''
                <div class="fix-suggestion">
                    <div class="fix-header">🔧 Suggested Fix {fixable_badge}</div>
                    <div class="fix-content">
                        <div class="before">
                            <strong>Before:</strong>
                            <pre>{issue.fix.original_code}</pre>
                        </div>
                        <div class="after">
                            <strong>After:</strong>
                            <pre>{issue.fix.fixed_code}</pre>
                        </div>
                    </div>
                </div>
                '''

            location = f"Line {issue.line_number}"
            if issue.column > 1:
                location += f":{issue.column}"

            issues_html += f'''
            <div class="issue" style="border-left: 4px solid {color};">
                <div class="issue-header">
                    <span class="severity" style="background: {color};">{issue.severity.value.upper()}</span>
                    <span class="location">{location}</span>
                </div>
                <p class="message">{issue.message}</p>
                <p class="suggestion">💡 {issue.suggestion}</p>
                <pre class="code">{issue.code_snippet}</pre>
                {fix_html}
            </div>
            '''

        if current_file:
            issues_html += "</div>"

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iOS Memory Leak Report - {self.project_name}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1, h2, h3 {{ color: #333; }}
        .header {{
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .stat-card h3 {{ margin: 0; font-size: 2em; }}
        .stat-card p {{ margin: 5px 0 0; color: #666; }}
        .stat-card.fixable {{ border-top: 4px solid #28a745; }}
        .file-group {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .issue {{
            background: #f8f9fa;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
        }}
        .issue-header {{
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
            align-items: center;
        }}
        .severity {{
            padding: 2px 8px;
            border-radius: 3px;
            color: white;
            font-size: 0.8em;
            font-weight: bold;
        }}
        .location {{ color: #666; font-family: monospace; }}
        .message {{ font-weight: 500; margin: 10px 0; }}
        .suggestion {{ color: #28a745; margin: 10px 0; }}
        .code {{
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            font-size: 0.9em;
            white-space: pre-wrap;
        }}
        .fix-suggestion {{
            background: #e8f5e9;
            border: 1px solid #4caf50;
            border-radius: 5px;
            padding: 15px;
            margin-top: 15px;
        }}
        .fix-header {{
            font-weight: bold;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .badge {{
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.8em;
        }}
        .badge.auto-fix {{
            background: #4caf50;
            color: white;
        }}
        .badge.manual {{
            background: #ff9800;
            color: white;
        }}
        .fix-content {{
            display: grid;
            gap: 10px;
        }}
        .before pre {{
            background: #ffebee;
            color: #c62828;
            padding: 10px;
            border-radius: 4px;
        }}
        .after pre {{
            background: #e8f5e9;
            color: #2e7d32;
            padding: 10px;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 iOS Memory Leak Analysis</h1>
        <p>Project: {self.project_name}</p>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="summary">
        <div class="stat-card">
            <h3>{self.result.total_files}</h3>
            <p>Files Analyzed</p>
        </div>
        <div class="stat-card">
            <h3>{self.result.total_issues}</h3>
            <p>Issues Found</p>
        </div>
        <div class="stat-card fixable">
            <h3>{self.result.fixable_issues}</h3>
            <p>Auto-fixable</p>
        </div>
        <div class="stat-card">
            <h3>{self.result.severity_counts.get('critical', 0) + self.result.severity_counts.get('high', 0)}</h3>
            <p>Critical/High</p>
        </div>
        <div class="stat-card">
            <h3>{self.result.analysis_time:.1f}s</h3>
            <p>Analysis Time</p>
        </div>
    </div>

    <h2>🔍 Detailed Issues</h2>
    {issues_html}

</body>
</html>'''

        return html

    def _generate_markdown(self) -> str:
        """Generate Markdown report content with fix suggestions."""
        md = f'''# iOS Memory Leak Analysis Report

**Project:** {self.project_name}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📊 Summary

| Metric | Value |
|--------|-------|
| Files Analyzed | {self.result.total_files} |
| Swift Files | {self.result.swift_files} |
| Objective-C Files | {self.result.objc_files} |
| Total Issues | {self.result.total_issues} |
| Auto-fixable | {self.result.fixable_issues} |
| Analysis Time | {self.result.analysis_time:.2f}s |

## 📈 Issues by Severity

| Severity | Count |
|----------|-------|
| 🔴 Critical | {self.result.severity_counts.get('critical', 0)} |
| 🟠 High | {self.result.severity_counts.get('high', 0)} |
| 🟡 Medium | {self.result.severity_counts.get('medium', 0)} |
| 🟢 Low | {self.result.severity_counts.get('low', 0)} |
| ℹ️ Info | {self.result.severity_counts.get('info', 0)} |

## 🔍 Detailed Issues

'''

        current_file = None
        for issue in self.result.issues:
            if issue.file_path != current_file:
                current_file = issue.file_path
                relative_path = self._get_relative_path(issue.file_path)
                md += f'\n### 📄 {relative_path}\n\n'

            icon = self.SEVERITY_ICONS.get(issue.severity.value, "•")
            location = f"Line {issue.line_number}"
            if issue.column > 1:
                location += f":{issue.column}"

            md += f'''
#### {icon} [{issue.severity.value.upper()}] {location}

**Issue:** {issue.message}

**Suggestion:** {issue.suggestion}

```
{issue.code_snippet}
```
'''

            if issue.fix:
                fixable = "✅ Auto-fixable" if issue.fix.is_auto_fixable else "⚠️ Manual fix"
                md += f'''
**🔧 Fix ({fixable}):**

Before:
```
{issue.fix.original_code}
```

After:
```
{issue.fix.fixed_code}
```
'''

            md += '\n---\n'

        return md

    def _get_relative_path(self, file_path: str) -> str:
        """Get a shorter relative path for display."""
        parts = Path(file_path).parts
        # Keep last 3 parts max
        if len(parts) > 3:
            return '/'.join(parts[-3:])
        return file_path
