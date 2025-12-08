"""
Memory Leak Analyzer - Main Analysis Engine
Enhanced with fix generation support
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .patterns import LeakPattern, LeakSeverity, LeakType, FixSuggestion, get_all_patterns, SWIFTUI_PATTERNS
from .swift_parser import SwiftParser
from .objc_parser import ObjCParser


@dataclass
class AnalysisResult:
    """Result of analyzing a project or file."""
    total_files: int = 0
    swift_files: int = 0
    objc_files: int = 0
    header_files: int = 0
    total_issues: int = 0
    fixable_issues: int = 0
    issues: List[LeakPattern] = field(default_factory=list)
    file_summaries: List[Dict] = field(default_factory=list)
    severity_counts: Dict[str, int] = field(default_factory=dict)
    type_counts: Dict[str, int] = field(default_factory=dict)
    analysis_time: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "summary": {
                "total_files": self.total_files,
                "swift_files": self.swift_files,
                "objc_files": self.objc_files,
                "header_files": self.header_files,
                "total_issues": self.total_issues,
                "fixable_issues": self.fixable_issues,
                "analysis_time_seconds": round(self.analysis_time, 2)
            },
            "by_severity": self.severity_counts,
            "by_type": self.type_counts,
            "issues": [issue.to_dict() for issue in self.issues],
            "file_summaries": self.file_summaries
        }

    def get_issues_by_file(self) -> Dict[str, List[LeakPattern]]:
        """Group issues by file path."""
        by_file: Dict[str, List[LeakPattern]] = {}
        for issue in self.issues:
            if issue.file_path not in by_file:
                by_file[issue.file_path] = []
            by_file[issue.file_path].append(issue)
        return by_file

    def get_fixable_issues(self) -> List[LeakPattern]:
        """Get only issues that can be auto-fixed."""
        return [
            issue for issue in self.issues
            if issue.fix and issue.fix.is_auto_fixable
        ]


class MemoryLeakAnalyzer:
    """Main analyzer for iOS memory leak detection."""

    SWIFT_EXTENSIONS = {'.swift'}
    OBJC_EXTENSIONS = {'.m', '.mm'}
    HEADER_EXTENSIONS = {'.h'}

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize analyzer with optional configuration.

        Args:
            config: Optional configuration dict with:
                - exclude_dirs: List of directory names to skip
                - exclude_files: List of file patterns to skip
                - severity_threshold: Minimum severity to report
                - include_swiftui: Whether to check SwiftUI patterns
                - max_workers: Number of parallel workers
                - generate_fixes: Whether to generate fix suggestions
        """
        self.config = config or {}
        self.exclude_dirs = set(self.config.get('exclude_dirs', [
            'Pods', 'Carthage', '.build', 'DerivedData',
            'build', '.git', 'vendor', 'node_modules'
        ]))
        self.exclude_files = set(self.config.get('exclude_files', [
            'Pods-', 'Generated', '.generated'
        ]))
        self.severity_threshold = LeakSeverity(
            self.config.get('severity_threshold', 'info')
        )
        self.include_swiftui = self.config.get('include_swiftui', True)
        self.max_workers = self.config.get('max_workers', 4)
        self.generate_fixes = self.config.get('generate_fixes', True)

        self.swift_parser = SwiftParser()
        self.objc_parser = ObjCParser()

    def analyze_directory(self, directory: str) -> AnalysisResult:
        """
        Analyze all iOS source files in a directory.

        Args:
            directory: Path to the directory to analyze

        Returns:
            AnalysisResult with all detected issues
        """
        import time
        start_time = time.time()

        result = AnalysisResult()
        files_to_analyze = self._collect_files(directory)

        # Separate files by type
        swift_files = [f for f in files_to_analyze if f.suffix in self.SWIFT_EXTENSIONS]
        objc_files = [f for f in files_to_analyze if f.suffix in self.OBJC_EXTENSIONS]
        header_files = [f for f in files_to_analyze if f.suffix in self.HEADER_EXTENSIONS]

        result.swift_files = len(swift_files)
        result.objc_files = len(objc_files)
        result.header_files = len(header_files)
        result.total_files = len(files_to_analyze)

        # Analyze files in parallel
        all_issues = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit Swift files
            swift_futures = {
                executor.submit(self._analyze_swift_file, str(f)): f
                for f in swift_files
            }

            # Submit Objective-C files
            objc_futures = {
                executor.submit(self._analyze_objc_file, str(f)): f
                for f in objc_files + header_files
            }

            # Collect results
            for future in as_completed({**swift_futures, **objc_futures}):
                try:
                    issues, summary = future.result()
                    all_issues.extend(issues)
                    if summary:
                        result.file_summaries.append(summary)
                except Exception as e:
                    file_path = swift_futures.get(future) or objc_futures.get(future)
                    print(f"Error analyzing {file_path}: {e}")

        # Filter by severity threshold
        filtered_issues = self._filter_by_severity(all_issues)

        # Deduplicate issues
        unique_issues = self._deduplicate_issues(filtered_issues)

        # Sort by severity and file
        sorted_issues = sorted(
            unique_issues,
            key=lambda x: (
                self._severity_order(x.severity),
                x.file_path,
                x.line_number
            )
        )

        result.issues = sorted_issues
        result.total_issues = len(sorted_issues)

        # Count fixable issues
        result.fixable_issues = sum(
            1 for issue in sorted_issues
            if issue.fix and issue.fix.is_auto_fixable
        )

        # Calculate counts
        for issue in sorted_issues:
            sev = issue.severity.value
            typ = issue.type.value
            result.severity_counts[sev] = result.severity_counts.get(sev, 0) + 1
            result.type_counts[typ] = result.type_counts.get(typ, 0) + 1

        result.analysis_time = time.time() - start_time
        return result

    def analyze_file(self, file_path: str) -> List[LeakPattern]:
        """
        Analyze a single file.

        Args:
            file_path: Path to the file to analyze

        Returns:
            List of detected issues
        """
        path = Path(file_path)

        if path.suffix in self.SWIFT_EXTENSIONS:
            issues, _ = self._analyze_swift_file(file_path)
            return issues
        elif path.suffix in self.OBJC_EXTENSIONS or path.suffix in self.HEADER_EXTENSIONS:
            issues, _ = self._analyze_objc_file(file_path)
            return issues
        else:
            print(f"Unsupported file type: {path.suffix}")
            return []

    def _collect_files(self, directory: str) -> List[Path]:
        """Collect all relevant source files in directory."""
        files = []
        root_path = Path(directory)

        if not root_path.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        for path in root_path.rglob('*'):
            # Skip excluded directories
            if any(excluded in path.parts for excluded in self.exclude_dirs):
                continue

            # Skip excluded files
            if any(excluded in path.name for excluded in self.exclude_files):
                continue

            # Check file extension
            if path.suffix in (self.SWIFT_EXTENSIONS | self.OBJC_EXTENSIONS | self.HEADER_EXTENSIONS):
                files.append(path)

        return files

    def _analyze_swift_file(self, file_path: str) -> Tuple[List[LeakPattern], Optional[Dict]]:
        """Analyze a Swift file."""
        parser = SwiftParser()
        issues = parser.parse_file(file_path)

        # Add SwiftUI-specific analysis if enabled
        if self.include_swiftui:
            swiftui_issues = self._detect_swiftui_issues(file_path)
            issues.extend(swiftui_issues)

        summary = parser.get_summary() if issues else None
        return issues, summary

    def _analyze_objc_file(self, file_path: str) -> Tuple[List[LeakPattern], Optional[Dict]]:
        """Analyze an Objective-C file."""
        parser = ObjCParser()
        issues = parser.parse_file(file_path)
        summary = parser.get_summary() if issues else None
        return issues, summary

    def _detect_swiftui_issues(self, file_path: str) -> List[LeakPattern]:
        """Detect SwiftUI-specific issues."""
        import re

        issues = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
        except Exception:
            return []

        # Check if file uses SwiftUI
        if 'import SwiftUI' not in content:
            return []

        # Calculate line offsets for precise location
        line_offsets = [0]
        offset = 0
        for line in lines:
            offset += len(line) + 1
            line_offsets.append(offset)

        def get_location(pos: int) -> Tuple[int, int]:
            for i, line_offset in enumerate(line_offsets):
                if i + 1 < len(line_offsets) and pos < line_offsets[i + 1]:
                    return (i + 1, pos - line_offset + 1)
            return (len(lines), 1)

        for name, pattern_data in SWIFTUI_PATTERNS.items():
            try:
                regex = re.compile(pattern_data["pattern"], re.MULTILINE | re.DOTALL)
                for match in regex.finditer(content):
                    line_num, column = get_location(match.start())
                    end_line, end_col = get_location(match.end())

                    # Get code snippet
                    start = max(0, line_num - 3)
                    end = min(len(lines), line_num + 2)
                    snippet_lines = []
                    for i in range(start, end):
                        prefix = ">>>" if i + 1 == line_num else "   "
                        snippet_lines.append(f"{prefix} {i+1:4d} | {lines[i]}")
                    snippet = '\n'.join(snippet_lines)

                    # Generate fix suggestion
                    fix_example = pattern_data.get('fix_example')
                    fix = None
                    if fix_example:
                        fix = FixSuggestion(
                            original_code=fix_example['before'],
                            fixed_code=fix_example['after'],
                            description=pattern_data['suggestion'],
                            start_line=line_num,
                            end_line=end_line,
                            is_auto_fixable=False
                        )

                    issue = LeakPattern(
                        type=pattern_data["type"],
                        severity=pattern_data["severity"],
                        file_path=file_path,
                        line_number=line_num,
                        column=column,
                        end_line=end_line,
                        end_column=end_col,
                        code_snippet=snippet,
                        message=pattern_data["message"],
                        suggestion=pattern_data["suggestion"],
                        fix=fix,
                        context={"pattern_name": name, "framework": "SwiftUI"}
                    )
                    issues.append(issue)
            except re.error:
                continue

        return issues

    def _filter_by_severity(self, issues: List[LeakPattern]) -> List[LeakPattern]:
        """Filter issues by minimum severity threshold."""
        severity_order = {
            LeakSeverity.CRITICAL: 0,
            LeakSeverity.HIGH: 1,
            LeakSeverity.MEDIUM: 2,
            LeakSeverity.LOW: 3,
            LeakSeverity.INFO: 4
        }

        threshold_order = severity_order.get(self.severity_threshold, 4)

        return [
            issue for issue in issues
            if severity_order.get(issue.severity, 4) <= threshold_order
        ]

    def _deduplicate_issues(self, issues: List[LeakPattern]) -> List[LeakPattern]:
        """Remove duplicate issues (same type, file, line)."""
        seen = set()
        unique = []

        for issue in issues:
            key = (issue.type, issue.file_path, issue.line_number)
            if key not in seen:
                seen.add(key)
                unique.append(issue)

        return unique

    def _severity_order(self, severity: LeakSeverity) -> int:
        """Get sorting order for severity."""
        order = {
            LeakSeverity.CRITICAL: 0,
            LeakSeverity.HIGH: 1,
            LeakSeverity.MEDIUM: 2,
            LeakSeverity.LOW: 3,
            LeakSeverity.INFO: 4
        }
        return order.get(severity, 5)

    def get_quick_stats(self, result: AnalysisResult) -> str:
        """Get a quick summary string."""
        critical = result.severity_counts.get('critical', 0)
        high = result.severity_counts.get('high', 0)
        medium = result.severity_counts.get('medium', 0)
        low = result.severity_counts.get('low', 0)

        return (
            f"Files: {result.total_files} | "
            f"Issues: {result.total_issues} | "
            f"Fixable: {result.fixable_issues} | "
            f"Critical: {critical} | High: {high} | "
            f"Medium: {medium} | Low: {low}"
        )
