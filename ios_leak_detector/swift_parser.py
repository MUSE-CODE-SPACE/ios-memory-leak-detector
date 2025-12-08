"""
Swift Code Parser for Memory Leak Detection
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path

from .patterns import LeakPattern, LeakSeverity, LeakType, SWIFT_PATTERNS, PERFORMANCE_PATTERNS


@dataclass
class SwiftClass:
    """Represents a Swift class/struct."""
    name: str
    type: str  # class, struct, actor
    start_line: int
    end_line: int
    has_deinit: bool = False
    properties: List[Dict] = field(default_factory=list)
    methods: List[Dict] = field(default_factory=list)
    closures: List[Dict] = field(default_factory=list)
    delegates: List[str] = field(default_factory=list)
    timers: List[int] = field(default_factory=list)
    observers: List[int] = field(default_factory=list)


@dataclass
class SwiftClosure:
    """Represents a Swift closure."""
    start_line: int
    end_line: int
    has_weak_self: bool
    has_unowned_self: bool
    uses_self: bool
    capture_list: List[str]
    content: str


class SwiftParser:
    """Parser for Swift source code files."""

    def __init__(self):
        self.classes: List[SwiftClass] = []
        self.issues: List[LeakPattern] = []
        self.file_path: str = ""
        self.lines: List[str] = []
        self.content: str = ""

    def parse_file(self, file_path: str) -> List[LeakPattern]:
        """Parse a Swift file and return detected issues."""
        self.file_path = file_path
        self.issues = []
        self.classes = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.content = f.read()
                self.lines = self.content.split('\n')
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []

        # Parse structure
        self._parse_classes()
        self._parse_closures()

        # Detect issues
        self._detect_pattern_issues()
        self._detect_closure_issues()
        self._detect_delegate_issues()
        self._detect_timer_observer_issues()
        self._detect_deinit_issues()
        self._detect_performance_issues()

        return self.issues

    def _parse_classes(self):
        """Parse class/struct definitions."""
        # Match class, struct, actor definitions
        class_pattern = re.compile(
            r'^[ \t]*((?:public|private|internal|fileprivate|open|final)\s+)*'
            r'(class|struct|actor)\s+(\w+)[^{]*\{',
            re.MULTILINE
        )

        for match in class_pattern.finditer(self.content):
            class_type = match.group(2)
            class_name = match.group(3)
            start_pos = match.start()
            start_line = self.content[:start_pos].count('\n') + 1

            # Find matching closing brace
            end_line = self._find_matching_brace(start_pos)

            swift_class = SwiftClass(
                name=class_name,
                type=class_type,
                start_line=start_line,
                end_line=end_line
            )

            # Check for deinit
            class_content = '\n'.join(self.lines[start_line-1:end_line])
            if re.search(r'\bdeinit\s*\{', class_content):
                swift_class.has_deinit = True

            # Parse properties
            self._parse_properties(swift_class, class_content, start_line)

            self.classes.append(swift_class)

    def _parse_properties(self, swift_class: SwiftClass, content: str, base_line: int):
        """Parse properties of a class."""
        # Match property declarations
        prop_pattern = re.compile(
            r'(@IBOutlet\s+)?'
            r'(weak\s+|unowned\s+)?'
            r'(let|var)\s+'
            r'(\w+)\s*:\s*'
            r'([^=\n{]+)',
            re.MULTILINE
        )

        for match in prop_pattern.finditer(content):
            is_outlet = match.group(1) is not None
            is_weak = match.group(2) is not None
            var_type = match.group(3)
            name = match.group(4)
            type_annotation = match.group(5).strip()

            line_num = base_line + content[:match.start()].count('\n')

            prop = {
                "name": name,
                "type": type_annotation,
                "is_weak": is_weak,
                "is_outlet": is_outlet,
                "is_var": var_type == "var",
                "line": line_num
            }
            swift_class.properties.append(prop)

            # Check if it's a delegate
            if 'delegate' in name.lower():
                swift_class.delegates.append(name)

    def _parse_closures(self):
        """Parse closures in the code."""
        # Find closures with potential self capture
        closure_pattern = re.compile(
            r'\{(\s*\[[^\]]*\])?\s*(?:\([^)]*\))?\s*(?:->.*?)?\s*in',
            re.MULTILINE | re.DOTALL
        )

        for match in closure_pattern.finditer(self.content):
            start_pos = match.start()
            start_line = self.content[:start_pos].count('\n') + 1
            end_line = self._find_matching_brace(start_pos)

            capture_list = match.group(1) or ""
            has_weak_self = 'weak self' in capture_list or 'weak `self`' in capture_list
            has_unowned_self = 'unowned self' in capture_list or 'unowned `self`' in capture_list

            closure_content = '\n'.join(self.lines[start_line-1:end_line])
            uses_self = bool(re.search(r'\bself[.\[]', closure_content))

            closure = SwiftClosure(
                start_line=start_line,
                end_line=end_line,
                has_weak_self=has_weak_self,
                has_unowned_self=has_unowned_self,
                uses_self=uses_self,
                capture_list=self._parse_capture_list(capture_list),
                content=closure_content
            )

            # Associate with class
            for cls in self.classes:
                if cls.start_line <= start_line <= cls.end_line:
                    cls.closures.append({
                        "line": start_line,
                        "has_weak_self": has_weak_self,
                        "has_unowned_self": has_unowned_self,
                        "uses_self": uses_self
                    })

    def _parse_capture_list(self, capture_str: str) -> List[str]:
        """Parse capture list items."""
        if not capture_str:
            return []
        # Remove brackets and split
        items = capture_str.strip('[]').split(',')
        return [item.strip() for item in items if item.strip()]

    def _find_matching_brace(self, start_pos: int) -> int:
        """Find the line number of matching closing brace."""
        brace_count = 0
        in_string = False
        escape_next = False
        start_line = self.content[:start_pos].count('\n') + 1

        for i, char in enumerate(self.content[start_pos:], start_pos):
            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return self.content[:i].count('\n') + 1

        return len(self.lines)

    def _detect_pattern_issues(self):
        """Detect issues using regex patterns."""
        all_patterns = {**SWIFT_PATTERNS, **PERFORMANCE_PATTERNS}

        for name, pattern_data in all_patterns.items():
            try:
                regex = re.compile(pattern_data["pattern"], re.MULTILINE | re.DOTALL)
                for match in regex.finditer(self.content):
                    line_num = self.content[:match.start()].count('\n') + 1
                    code_snippet = self._get_code_snippet(line_num)

                    issue = LeakPattern(
                        type=pattern_data["type"],
                        severity=pattern_data["severity"],
                        file_path=self.file_path,
                        line_number=line_num,
                        code_snippet=code_snippet,
                        message=pattern_data["message"],
                        suggestion=pattern_data["suggestion"],
                        context={"pattern_name": name}
                    )
                    self.issues.append(issue)
            except re.error:
                continue

    def _detect_closure_issues(self):
        """Detect closure-related memory issues."""
        for cls in self.classes:
            for closure_info in cls.closures:
                if closure_info["uses_self"] and not closure_info["has_weak_self"] and not closure_info["has_unowned_self"]:
                    line_num = closure_info["line"]

                    # Check if this is a known safe pattern (animation, etc.)
                    snippet = self._get_code_snippet(line_num)
                    if self._is_safe_closure_context(snippet):
                        continue

                    issue = LeakPattern(
                        type=LeakType.MISSING_WEAK_SELF,
                        severity=LeakSeverity.HIGH,
                        file_path=self.file_path,
                        line_number=line_num,
                        code_snippet=snippet,
                        message="Closure captures 'self' without [weak self] or [unowned self]",
                        suggestion="Add [weak self] at the start of the closure",
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

    def _is_safe_closure_context(self, snippet: str) -> bool:
        """Check if closure is in a safe context (animation, etc.)."""
        safe_patterns = [
            r'UIView\.animate',
            r'UIView\.transition',
            r'\.forEach\s*\{',
            r'\.map\s*\{',
            r'\.filter\s*\{',
            r'\.reduce\s*\(',
            r'\.compactMap\s*\{',
            r'\.flatMap\s*\{',
        ]
        for pattern in safe_patterns:
            if re.search(pattern, snippet):
                return True
        return False

    def _detect_delegate_issues(self):
        """Detect non-weak delegate declarations."""
        for cls in self.classes:
            for prop in cls.properties:
                if 'delegate' in prop['name'].lower() and not prop['is_weak']:
                    issue = LeakPattern(
                        type=LeakType.NON_WEAK_DELEGATE,
                        severity=LeakSeverity.HIGH,
                        file_path=self.file_path,
                        line_number=prop['line'],
                        code_snippet=self._get_code_snippet(prop['line']),
                        message=f"Delegate property '{prop['name']}' is not declared as weak",
                        suggestion="Declare as: weak var delegate: DelegateType?",
                        context={"class": cls.name, "property": prop['name']}
                    )
                    self.issues.append(issue)

    def _detect_timer_observer_issues(self):
        """Detect timer and observer issues."""
        timer_pattern = re.compile(r'Timer\.(?:scheduledTimer|init)\s*\(', re.MULTILINE)
        observer_pattern = re.compile(r'NotificationCenter\.default\.addObserver', re.MULTILINE)

        for cls in self.classes:
            class_content = '\n'.join(self.lines[cls.start_line-1:cls.end_line])

            # Check timers
            for match in timer_pattern.finditer(class_content):
                line_num = cls.start_line + class_content[:match.start()].count('\n')
                cls.timers.append(line_num)

            # Check observers
            for match in observer_pattern.finditer(class_content):
                line_num = cls.start_line + class_content[:match.start()].count('\n')
                cls.observers.append(line_num)

            # Check if properly cleaned up in deinit
            deinit_content = self._get_deinit_content(cls)

            if cls.timers and 'invalidate' not in deinit_content:
                for timer_line in cls.timers:
                    issue = LeakPattern(
                        type=LeakType.UNREMOVED_TIMER,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=timer_line,
                        code_snippet=self._get_code_snippet(timer_line),
                        message="Timer may not be invalidated in deinit",
                        suggestion="Store timer and call timer.invalidate() in deinit",
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

            if cls.observers and 'removeObserver' not in deinit_content:
                for obs_line in cls.observers:
                    issue = LeakPattern(
                        type=LeakType.NOTIFICATION_NOT_REMOVED,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=obs_line,
                        code_snippet=self._get_code_snippet(obs_line),
                        message="NotificationCenter observer may not be removed in deinit",
                        suggestion="Call NotificationCenter.default.removeObserver(self) in deinit",
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

    def _get_deinit_content(self, cls: SwiftClass) -> str:
        """Get the content of deinit method for a class."""
        class_content = '\n'.join(self.lines[cls.start_line-1:cls.end_line])
        deinit_match = re.search(r'deinit\s*\{([^}]*)\}', class_content, re.DOTALL)
        if deinit_match:
            return deinit_match.group(1)
        return ""

    def _detect_deinit_issues(self):
        """Detect classes that should have deinit but don't."""
        for cls in self.classes:
            if cls.type != 'class':
                continue

            # Class has potential cleanup needs
            needs_deinit = (
                cls.timers or
                cls.observers or
                any('delegate' in p['name'].lower() for p in cls.properties)
            )

            if needs_deinit and not cls.has_deinit:
                issue = LeakPattern(
                    type=LeakType.MISSING_DEINIT,
                    severity=LeakSeverity.LOW,
                    file_path=self.file_path,
                    line_number=cls.start_line,
                    code_snippet=self._get_code_snippet(cls.start_line),
                    message=f"Class '{cls.name}' should have deinit for cleanup",
                    suggestion="Add deinit to clean up timers, observers, and delegates",
                    context={"class": cls.name}
                )
                self.issues.append(issue)

    def _detect_performance_issues(self):
        """Detect potential main thread hang issues."""
        # Already covered by pattern matching in _detect_pattern_issues
        pass

    def _get_code_snippet(self, line_num: int, context: int = 2) -> str:
        """Get code snippet around a line."""
        start = max(0, line_num - context - 1)
        end = min(len(self.lines), line_num + context)
        snippet_lines = self.lines[start:end]
        return '\n'.join(f"{i+start+1}: {line}" for i, line in enumerate(snippet_lines))

    def get_summary(self) -> Dict:
        """Get analysis summary."""
        severity_counts = {}
        type_counts = {}

        for issue in self.issues:
            sev = issue.severity.value
            typ = issue.type.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            type_counts[typ] = type_counts.get(typ, 0) + 1

        return {
            "file": self.file_path,
            "total_issues": len(self.issues),
            "classes_analyzed": len(self.classes),
            "by_severity": severity_counts,
            "by_type": type_counts
        }
