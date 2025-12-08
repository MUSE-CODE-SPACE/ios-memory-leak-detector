"""
Report Generator for Memory Leak Analysis Results
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from .analyzer import AnalysisResult
from .patterns import LeakPattern, LeakSeverity, LeakType


class Reporter:
    """Generate reports from analysis results."""

    SEVERITY_COLORS = {
        "critical": "\033[91m",  # Red
        "high": "\033[93m",      # Yellow
        "medium": "\033[94m",    # Blue
        "low": "\033[92m",       # Green
        "info": "\033[90m",      # Gray
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

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

    def print_console(self, verbose: bool = False, no_color: bool = False):
        """Print report to console."""
        if no_color:
            self._print_console_plain(verbose)
        else:
            self._print_console_colored(verbose)

    def _print_console_colored(self, verbose: bool):
        """Print colored console output."""
        print()
        print(f"{self.BOLD}{'='*60}{self.RESET}")
        print(f"{self.BOLD}  iOS Memory Leak Analysis Report{self.RESET}")
        print(f"{self.BOLD}  Project: {self.project_name}{self.RESET}")
        print(f"{self.BOLD}{'='*60}{self.RESET}")
        print()

        # Summary
        print(f"{self.BOLD}📊 Summary{self.RESET}")
        print(f"  Files analyzed: {self.result.total_files}")
        print(f"    Swift: {self.result.swift_files}")
        print(f"    Objective-C: {self.result.objc_files}")
        print(f"    Headers: {self.result.header_files}")
        print(f"  Total issues: {self.result.total_issues}")
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
                icon = self.TYPE_ICONS.get(LeakType(typ), "•")
                display_name = typ.replace('_', ' ').title()
                print(f"  {icon} {display_name}: {count}")
            print()

        # Detailed issues
        if self.result.issues:
            print(f"{self.BOLD}🔍 Detailed Issues{self.RESET}")
            print("-" * 60)

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

                print(f"\n  {icon} {color}[{issue.severity.value.upper()}]{self.RESET} "
                      f"Line {issue.line_number}")
                print(f"  {type_icon} {issue.message}")
                print(f"  💡 {issue.suggestion}")

                if verbose and issue.code_snippet:
                    print(f"\n  Code:")
                    for line in issue.code_snippet.split('\n'):
                        print(f"    {line}")

        print()
        print(f"{self.BOLD}{'='*60}{self.RESET}")

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
        print()

    def _print_console_plain(self, verbose: bool):
        """Print plain text console output (no colors)."""
        print()
        print("=" * 60)
        print("  iOS Memory Leak Analysis Report")
        print(f"  Project: {self.project_name}")
        print("=" * 60)
        print()

        print("Summary:")
        print(f"  Files analyzed: {self.result.total_files}")
        print(f"  Total issues: {self.result.total_issues}")
        print()

        for issue in self.result.issues:
            print(f"[{issue.severity.value.upper()}] {issue.file_path}:{issue.line_number}")
            print(f"  {issue.message}")
            print(f"  Suggestion: {issue.suggestion}")
            if verbose and issue.code_snippet:
                print(f"  Code:\n{issue.code_snippet}")
            print()

    def to_json(self, output_path: Optional[str] = None) -> str:
        """Generate JSON report."""
        report = {
            "project": self.project_name,
            "generated_at": datetime.now().isoformat(),
            "analysis": self.result.to_dict()
        }

        json_str = json.dumps(report, indent=2)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            print(f"JSON report saved to: {output_path}")

        return json_str

    def to_html(self, output_path: str) -> str:
        """Generate HTML report."""
        html = self._generate_html()

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"HTML report saved to: {output_path}")
        return html

    def to_markdown(self, output_path: Optional[str] = None) -> str:
        """Generate Markdown report."""
        md = self._generate_markdown()

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(md)
            print(f"Markdown report saved to: {output_path}")

        return md

    def _generate_html(self) -> str:
        """Generate HTML report content."""
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
            issues_html += f'''
            <div class="issue" style="border-left: 4px solid {color};">
                <div class="issue-header">
                    <span class="severity" style="background: {color};">{issue.severity.value.upper()}</span>
                    <span class="line">Line {issue.line_number}</span>
                </div>
                <p class="message">{issue.message}</p>
                <p class="suggestion">💡 {issue.suggestion}</p>
                <pre class="code">{issue.code_snippet}</pre>
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
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
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
        .severity-chart {{
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
        }}
        .severity-bar {{
            padding: 10px 20px;
            border-radius: 5px;
            color: white;
            font-weight: bold;
        }}
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
        }}
        .severity {{
            padding: 2px 8px;
            border-radius: 3px;
            color: white;
            font-size: 0.8em;
            font-weight: bold;
        }}
        .line {{ color: #666; }}
        .message {{ font-weight: 500; margin: 10px 0; }}
        .suggestion {{ color: #28a745; margin: 10px 0; }}
        .code {{
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            font-size: 0.9em;
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
        <div class="stat-card">
            <h3>{self.result.severity_counts.get('critical', 0) + self.result.severity_counts.get('high', 0)}</h3>
            <p>Critical/High</p>
        </div>
        <div class="stat-card">
            <h3>{self.result.analysis_time:.1f}s</h3>
            <p>Analysis Time</p>
        </div>
    </div>

    <h2>📊 Severity Distribution</h2>
    <div class="severity-chart">
        <div class="severity-bar" style="background: #dc3545;">
            Critical: {self.result.severity_counts.get('critical', 0)}
        </div>
        <div class="severity-bar" style="background: #fd7e14;">
            High: {self.result.severity_counts.get('high', 0)}
        </div>
        <div class="severity-bar" style="background: #ffc107; color: #333;">
            Medium: {self.result.severity_counts.get('medium', 0)}
        </div>
        <div class="severity-bar" style="background: #28a745;">
            Low: {self.result.severity_counts.get('low', 0)}
        </div>
    </div>

    <h2>🔍 Detailed Issues</h2>
    {issues_html}

</body>
</html>'''

        return html

    def _generate_markdown(self) -> str:
        """Generate Markdown report content."""
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
            md += f'''
#### {icon} [{issue.severity.value.upper()}] Line {issue.line_number}

**Issue:** {issue.message}

**Suggestion:** {issue.suggestion}

```swift
{issue.code_snippet}
```

---
'''

        return md

    def _get_relative_path(self, file_path: str) -> str:
        """Get a shorter relative path for display."""
        parts = Path(file_path).parts
        # Keep last 3 parts max
        if len(parts) > 3:
            return '/'.join(parts[-3:])
        return file_path
