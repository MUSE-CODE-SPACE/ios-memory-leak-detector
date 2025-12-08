"""
Swift Code Parser for Memory Leak Detection
Enhanced with precise location tracking and fix generation
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path

from .patterns import (
    LeakPattern, LeakSeverity, LeakType, FixSuggestion,
    SWIFT_PATTERNS, SWIFTUI_PATTERNS, PERFORMANCE_PATTERNS,
    get_all_patterns
)


@dataclass
class CodeLocation:
    """Precise code location."""
    line: int
    column: int
    end_line: int = 0
    end_column: int = 0
    offset: int = 0  # Character offset from start of file

    def to_dict(self) -> Dict:
        return {
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line or self.line,
            "end_column": self.end_column
        }


@dataclass
class SwiftClass:
    """Represents a Swift class/struct."""
    name: str
    type: str  # class, struct, actor
    location: CodeLocation = None
    has_deinit: bool = False
    properties: List[Dict] = field(default_factory=list)
    methods: List[Dict] = field(default_factory=list)
    closures: List[Dict] = field(default_factory=list)
    delegates: List[str] = field(default_factory=list)
    timers: List[Dict] = field(default_factory=list)
    observers: List[Dict] = field(default_factory=list)

    @property
    def start_line(self) -> int:
        return self.location.line if self.location else 0

    @property
    def end_line(self) -> int:
        return self.location.end_line if self.location else 0


@dataclass
class SwiftClosure:
    """Represents a Swift closure."""
    location: CodeLocation
    has_weak_self: bool
    has_unowned_self: bool
    uses_self: bool
    capture_list: List[str]
    content: str
    context_type: str = ""  # timer, dispatch, animation, stored, etc.


class SwiftParser:
    """Parser for Swift source code files with enhanced location tracking."""

    def __init__(self):
        self.classes: List[SwiftClass] = []
        self.issues: List[LeakPattern] = []
        self.file_path: str = ""
        self.lines: List[str] = []
        self.content: str = ""
        self.line_offsets: List[int] = []  # Offset of each line start

    def parse_file(self, file_path: str) -> List[LeakPattern]:
        """Parse a Swift file and return detected issues."""
        self.file_path = file_path
        self.issues = []
        self.classes = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.content = f.read()
                self.lines = self.content.split('\n')
                self._calculate_line_offsets()
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []

        # Parse structure
        self._parse_classes()
        self._parse_closures()

        # Detect issues with precise locations
        self._detect_pattern_issues()
        self._detect_closure_issues()
        self._detect_delegate_issues()
        self._detect_timer_observer_issues()
        self._detect_deinit_issues()

        return self.issues

    def _calculate_line_offsets(self):
        """Calculate character offset for each line."""
        self.line_offsets = [0]
        offset = 0
        for line in self.lines:
            offset += len(line) + 1  # +1 for newline
            self.line_offsets.append(offset)

    def _get_location_from_offset(self, offset: int) -> CodeLocation:
        """Convert character offset to line:column location."""
        for i, line_offset in enumerate(self.line_offsets):
            if i + 1 < len(self.line_offsets) and offset < self.line_offsets[i + 1]:
                return CodeLocation(
                    line=i + 1,
                    column=offset - line_offset + 1,
                    offset=offset
                )
        return CodeLocation(line=len(self.lines), column=1, offset=offset)

    def _get_location_from_match(self, match: re.Match) -> CodeLocation:
        """Get location from regex match."""
        start_loc = self._get_location_from_offset(match.start())
        end_loc = self._get_location_from_offset(match.end())
        return CodeLocation(
            line=start_loc.line,
            column=start_loc.column,
            end_line=end_loc.line,
            end_column=end_loc.column,
            offset=match.start()
        )

    def _parse_classes(self):
        """Parse class/struct definitions."""
        class_pattern = re.compile(
            r'^[ \t]*((?:public|private|internal|fileprivate|open|final)\s+)*'
            r'(class|struct|actor)\s+(\w+)[^{]*\{',
            re.MULTILINE
        )

        for match in class_pattern.finditer(self.content):
            class_type = match.group(2)
            class_name = match.group(3)
            location = self._get_location_from_match(match)

            # Find matching closing brace
            end_line = self._find_matching_brace(match.start())
            location.end_line = end_line

            swift_class = SwiftClass(
                name=class_name,
                type=class_type,
                location=location
            )

            # Check for deinit
            class_content = '\n'.join(self.lines[location.line-1:end_line])
            if re.search(r'\bdeinit\s*\{', class_content):
                swift_class.has_deinit = True

            # Parse properties
            self._parse_properties(swift_class, class_content, location.line)

            self.classes.append(swift_class)

    def _parse_properties(self, swift_class: SwiftClass, content: str, base_line: int):
        """Parse properties of a class with precise locations."""
        prop_pattern = re.compile(
            r'(@IBOutlet\s+)?'
            r'(weak\s+|unowned\s+)?'
            r'(private\s+|public\s+|internal\s+|fileprivate\s+)?'
            r'(let|var)\s+'
            r'(\w+)\s*:\s*'
            r'([^=\n{]+)',
            re.MULTILINE
        )

        for match in prop_pattern.finditer(content):
            is_outlet = match.group(1) is not None
            is_weak = match.group(2) is not None
            var_type = match.group(4)
            name = match.group(5)
            type_annotation = match.group(6).strip()

            # Calculate precise line number
            line_in_content = content[:match.start()].count('\n')
            line_num = base_line + line_in_content

            # Calculate column
            line_start = content.rfind('\n', 0, match.start()) + 1
            column = match.start() - line_start + 1

            prop = {
                "name": name,
                "type": type_annotation,
                "is_weak": is_weak,
                "is_outlet": is_outlet,
                "is_var": var_type == "var",
                "line": line_num,
                "column": column,
                "raw_match": match.group(0)
            }
            swift_class.properties.append(prop)

            # Check if it's a delegate
            if 'delegate' in name.lower():
                swift_class.delegates.append(name)

    def _parse_closures(self):
        """Parse closures in the code with context awareness."""
        # Find closures with potential self capture
        closure_pattern = re.compile(
            r'\{(\s*\[[^\]]*\])?\s*(?:\([^)]*\))?\s*(?:->.*?)?\s*in',
            re.MULTILINE | re.DOTALL
        )

        for match in closure_pattern.finditer(self.content):
            location = self._get_location_from_match(match)
            end_line = self._find_matching_brace(match.start())
            location.end_line = end_line

            capture_list = match.group(1) or ""
            has_weak_self = 'weak self' in capture_list or 'weak `self`' in capture_list
            has_unowned_self = 'unowned self' in capture_list or 'unowned `self`' in capture_list

            closure_content = '\n'.join(self.lines[location.line-1:end_line])
            uses_self = bool(re.search(r'\bself[.\[]', closure_content))

            # Determine closure context
            context_type = self._determine_closure_context(match.start())

            closure = SwiftClosure(
                location=location,
                has_weak_self=has_weak_self,
                has_unowned_self=has_unowned_self,
                uses_self=uses_self,
                capture_list=self._parse_capture_list(capture_list),
                content=closure_content,
                context_type=context_type
            )

            # Associate with class
            for cls in self.classes:
                if cls.start_line <= location.line <= cls.end_line:
                    cls.closures.append({
                        "location": location,
                        "line": location.line,
                        "column": location.column,
                        "has_weak_self": has_weak_self,
                        "has_unowned_self": has_unowned_self,
                        "uses_self": uses_self,
                        "context_type": context_type
                    })

    def _determine_closure_context(self, offset: int) -> str:
        """Determine the context of a closure (timer, dispatch, animation, etc.)."""
        # Look at the 100 characters before the closure
        prefix = self.content[max(0, offset-100):offset]

        if 'Timer.' in prefix or 'NSTimer' in prefix:
            return 'timer'
        elif 'DispatchQueue' in prefix or 'dispatch_' in prefix:
            return 'dispatch'
        elif 'UIView.animate' in prefix:
            return 'animation'
        elif '.sink' in prefix:
            return 'combine'
        elif 'completionHandler' in prefix or 'completion' in prefix:
            return 'completion'
        elif re.search(r'=\s*$', prefix):
            return 'stored'
        elif '.task' in prefix:
            return 'async_task'
        elif '.onAppear' in prefix or '.onDisappear' in prefix:
            return 'swiftui_lifecycle'

        return 'unknown'

    def _parse_capture_list(self, capture_str: str) -> List[str]:
        """Parse capture list items."""
        if not capture_str:
            return []
        items = capture_str.strip('[]').split(',')
        return [item.strip() for item in items if item.strip()]

    def _find_matching_brace(self, start_pos: int) -> int:
        """Find the line number of matching closing brace."""
        brace_count = 0
        in_string = False
        escape_next = False

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
        """Detect issues using regex patterns with precise locations."""
        all_patterns = {**SWIFT_PATTERNS, **PERFORMANCE_PATTERNS}

        for name, pattern_data in all_patterns.items():
            try:
                regex = re.compile(pattern_data["pattern"], re.MULTILINE | re.DOTALL)
                for match in regex.finditer(self.content):
                    location = self._get_location_from_match(match)
                    code_snippet = self._get_code_snippet(location.line)

                    # Generate fix if possible
                    fix = self._generate_fix(pattern_data, match.group(0), location)

                    issue = LeakPattern(
                        type=pattern_data["type"],
                        severity=pattern_data["severity"],
                        file_path=self.file_path,
                        line_number=location.line,
                        column=location.column,
                        end_line=location.end_line,
                        end_column=location.end_column,
                        code_snippet=code_snippet,
                        message=pattern_data["message"],
                        suggestion=pattern_data["suggestion"],
                        fix=fix,
                        context={"pattern_name": name}
                    )
                    self.issues.append(issue)
            except re.error:
                continue

    def _generate_fix(self, pattern_data: Dict, matched_text: str, location: CodeLocation) -> Optional[FixSuggestion]:
        """Generate fix suggestion for a pattern match."""
        fix_generator = pattern_data.get('fix_generator')
        if fix_generator:
            try:
                fix = fix_generator(matched_text, {})
                fix.start_line = location.line
                fix.end_line = location.end_line
                fix.start_column = location.column
                fix.end_column = location.end_column
                return fix
            except Exception:
                pass

        # Return example fix if available
        fix_example = pattern_data.get('fix_example')
        if fix_example:
            return FixSuggestion(
                original_code=fix_example['before'],
                fixed_code=fix_example['after'],
                description=pattern_data['suggestion'],
                start_line=location.line,
                end_line=location.end_line,
                is_auto_fixable=False  # Example only, not auto-fixable
            )

        return None

    def _detect_closure_issues(self):
        """Detect closure-related memory issues."""
        for cls in self.classes:
            for closure_info in cls.closures:
                if closure_info["uses_self"] and not closure_info["has_weak_self"] and not closure_info["has_unowned_self"]:
                    location = closure_info.get("location")
                    line_num = closure_info["line"]
                    column = closure_info.get("column", 1)

                    # Check if this is a known safe pattern
                    context_type = closure_info.get("context_type", "unknown")
                    if self._is_safe_closure_context(context_type):
                        continue

                    snippet = self._get_code_snippet(line_num)

                    # Generate fix
                    fix = FixSuggestion(
                        original_code=snippet.split('\n')[2] if len(snippet.split('\n')) > 2 else "",
                        fixed_code="{ [weak self] in",
                        description="Add [weak self] at the start of the closure and use self?.",
                        start_line=line_num,
                        end_line=line_num,
                        start_column=column,
                        is_auto_fixable=True
                    )

                    issue = LeakPattern(
                        type=LeakType.MISSING_WEAK_SELF,
                        severity=LeakSeverity.HIGH,
                        file_path=self.file_path,
                        line_number=line_num,
                        column=column,
                        end_line=location.end_line if location else line_num,
                        code_snippet=snippet,
                        message=f"Closure captures 'self' without [weak self] (context: {context_type})",
                        suggestion="Add [weak self] at the start of the closure",
                        fix=fix,
                        context={"class": cls.name, "context_type": context_type}
                    )
                    self.issues.append(issue)

    def _is_safe_closure_context(self, context_type: str) -> bool:
        """Check if closure context is typically safe."""
        safe_contexts = {'animation', 'swiftui_lifecycle'}
        return context_type in safe_contexts

    def _detect_delegate_issues(self):
        """Detect non-weak delegate declarations."""
        for cls in self.classes:
            for prop in cls.properties:
                if 'delegate' in prop['name'].lower() and not prop['is_weak']:
                    line_num = prop['line']
                    column = prop.get('column', 1)

                    # Generate fix
                    original = prop.get('raw_match', '')
                    fixed = re.sub(r'\bvar\s+', 'weak var ', original)

                    fix = FixSuggestion(
                        original_code=original,
                        fixed_code=fixed,
                        description="Add 'weak' keyword to delegate property",
                        start_line=line_num,
                        end_line=line_num,
                        start_column=column,
                        is_auto_fixable=True
                    )

                    issue = LeakPattern(
                        type=LeakType.NON_WEAK_DELEGATE,
                        severity=LeakSeverity.HIGH,
                        file_path=self.file_path,
                        line_number=line_num,
                        column=column,
                        code_snippet=self._get_code_snippet(line_num),
                        message=f"Delegate property '{prop['name']}' is not declared as weak",
                        suggestion="Declare as: weak var delegate: DelegateType?",
                        fix=fix,
                        context={"class": cls.name, "property": prop['name']}
                    )
                    self.issues.append(issue)

    def _detect_timer_observer_issues(self):
        """Detect timer and observer issues with precise locations."""
        timer_pattern = re.compile(r'Timer\.(?:scheduledTimer|init)\s*\(', re.MULTILINE)
        observer_pattern = re.compile(r'NotificationCenter\.default\.addObserver', re.MULTILINE)

        for cls in self.classes:
            class_content = '\n'.join(self.lines[cls.start_line-1:cls.end_line])

            # Check timers
            for match in timer_pattern.finditer(class_content):
                line_in_class = class_content[:match.start()].count('\n')
                line_num = cls.start_line + line_in_class
                column = match.start() - class_content.rfind('\n', 0, match.start())

                cls.timers.append({
                    "line": line_num,
                    "column": column
                })

            # Check observers
            for match in observer_pattern.finditer(class_content):
                line_in_class = class_content[:match.start()].count('\n')
                line_num = cls.start_line + line_in_class
                column = match.start() - class_content.rfind('\n', 0, match.start())

                cls.observers.append({
                    "line": line_num,
                    "column": column
                })

            # Check if properly cleaned up in deinit
            deinit_content = self._get_deinit_content(cls)

            if cls.timers and 'invalidate' not in deinit_content:
                for timer_info in cls.timers:
                    issue = LeakPattern(
                        type=LeakType.UNREMOVED_TIMER,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=timer_info["line"],
                        column=timer_info.get("column", 1),
                        code_snippet=self._get_code_snippet(timer_info["line"]),
                        message="Timer may not be invalidated in deinit",
                        suggestion="Store timer and call timer.invalidate() in deinit",
                        fix=FixSuggestion(
                            original_code="// No deinit cleanup",
                            fixed_code="deinit {\n    timer?.invalidate()\n    timer = nil\n}",
                            description="Add timer invalidation in deinit",
                            is_auto_fixable=False
                        ),
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

            if cls.observers and 'removeObserver' not in deinit_content:
                for obs_info in cls.observers:
                    issue = LeakPattern(
                        type=LeakType.NOTIFICATION_NOT_REMOVED,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=obs_info["line"],
                        column=obs_info.get("column", 1),
                        code_snippet=self._get_code_snippet(obs_info["line"]),
                        message="NotificationCenter observer may not be removed in deinit",
                        suggestion="Call NotificationCenter.default.removeObserver(self) in deinit",
                        fix=FixSuggestion(
                            original_code="// No deinit cleanup",
                            fixed_code="deinit {\n    NotificationCenter.default.removeObserver(self)\n}",
                            description="Add observer removal in deinit",
                            is_auto_fixable=False
                        ),
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
                    severity=LeakSeverity.INFO,
                    file_path=self.file_path,
                    line_number=cls.start_line,
                    column=1,
                    end_line=cls.end_line,
                    code_snippet=self._get_code_snippet(cls.start_line),
                    message=f"Class '{cls.name}' should have deinit for cleanup",
                    suggestion="Add deinit to clean up timers, observers, and delegates",
                    fix=FixSuggestion(
                        original_code="// No deinit",
                        fixed_code='deinit {\n    print("\\(type(of: self)) deallocated")\n}',
                        description="Add deinit method for debugging and cleanup",
                        is_auto_fixable=False
                    ),
                    context={"class": cls.name}
                )
                self.issues.append(issue)

    def _get_code_snippet(self, line_num: int, context: int = 2) -> str:
        """Get code snippet around a line with line numbers."""
        start = max(0, line_num - context - 1)
        end = min(len(self.lines), line_num + context)
        snippet_lines = self.lines[start:end]

        # Format with line numbers, highlighting the target line
        formatted = []
        for i, line in enumerate(snippet_lines):
            actual_line = i + start + 1
            prefix = ">>>" if actual_line == line_num else "   "
            formatted.append(f"{prefix} {actual_line:4d} | {line}")

        return '\n'.join(formatted)

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
