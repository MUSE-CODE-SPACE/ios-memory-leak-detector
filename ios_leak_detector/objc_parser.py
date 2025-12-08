"""
Objective-C Code Parser for Memory Leak Detection
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path

from .patterns import LeakPattern, LeakSeverity, LeakType, OBJC_PATTERNS, PERFORMANCE_PATTERNS


@dataclass
class ObjCClass:
    """Represents an Objective-C class."""
    name: str
    start_line: int
    end_line: int
    has_dealloc: bool = False
    properties: List[Dict] = field(default_factory=list)
    methods: List[Dict] = field(default_factory=list)
    blocks: List[Dict] = field(default_factory=list)
    delegates: List[str] = field(default_factory=list)
    timers: List[int] = field(default_factory=list)
    observers: List[int] = field(default_factory=list)
    kvo_observers: List[int] = field(default_factory=list)


@dataclass
class ObjCBlock:
    """Represents an Objective-C block."""
    start_line: int
    end_line: int
    uses_self: bool
    has_weak_self_before: bool
    content: str


class ObjCParser:
    """Parser for Objective-C source code files (.m, .mm, .h)."""

    def __init__(self):
        self.classes: List[ObjCClass] = []
        self.issues: List[LeakPattern] = []
        self.file_path: str = ""
        self.lines: List[str] = []
        self.content: str = ""
        self.is_header: bool = False

    def parse_file(self, file_path: str) -> List[LeakPattern]:
        """Parse an Objective-C file and return detected issues."""
        self.file_path = file_path
        self.issues = []
        self.classes = []
        self.is_header = file_path.endswith('.h')

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.content = f.read()
                self.lines = self.content.split('\n')
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []

        # Parse structure
        self._parse_interfaces()
        self._parse_implementations()
        self._parse_properties()
        self._parse_blocks()

        # Detect issues
        self._detect_pattern_issues()
        self._detect_block_issues()
        self._detect_property_issues()
        self._detect_timer_observer_issues()
        self._detect_dealloc_issues()
        self._detect_arc_issues()

        return self.issues

    def _parse_interfaces(self):
        """Parse @interface declarations (usually in .h files)."""
        interface_pattern = re.compile(
            r'@interface\s+(\w+)\s*(?::\s*(\w+))?\s*(?:<[^>]+>)?\s*(?:\{[^}]*\})?',
            re.MULTILINE | re.DOTALL
        )

        for match in interface_pattern.finditer(self.content):
            class_name = match.group(1)
            start_pos = match.start()
            start_line = self.content[:start_pos].count('\n') + 1

            # Find @end
            end_match = re.search(r'@end', self.content[match.end():])
            if end_match:
                end_line = self.content[:match.end() + end_match.end()].count('\n') + 1
            else:
                end_line = len(self.lines)

            objc_class = ObjCClass(
                name=class_name,
                start_line=start_line,
                end_line=end_line
            )
            self.classes.append(objc_class)

    def _parse_implementations(self):
        """Parse @implementation sections."""
        impl_pattern = re.compile(
            r'@implementation\s+(\w+)',
            re.MULTILINE
        )

        for match in impl_pattern.finditer(self.content):
            class_name = match.group(1)
            start_pos = match.start()
            start_line = self.content[:start_pos].count('\n') + 1

            # Find @end
            end_match = re.search(r'@end', self.content[match.end():])
            if end_match:
                end_line = self.content[:match.end() + end_match.end()].count('\n') + 1
            else:
                end_line = len(self.lines)

            # Check if class already exists (from interface)
            existing = next((c for c in self.classes if c.name == class_name), None)
            if existing:
                existing.end_line = end_line
            else:
                objc_class = ObjCClass(
                    name=class_name,
                    start_line=start_line,
                    end_line=end_line
                )
                self.classes.append(objc_class)

            # Check for dealloc
            impl_content = '\n'.join(self.lines[start_line-1:end_line])
            if re.search(r'-\s*\(void\)\s*dealloc\s*\{', impl_content):
                if existing:
                    existing.has_dealloc = True
                else:
                    self.classes[-1].has_dealloc = True

    def _parse_properties(self):
        """Parse @property declarations."""
        prop_pattern = re.compile(
            r'@property\s*\(([^)]*)\)\s*'
            r'(?:IBOutlet\s+)?'
            r'(\w+(?:\s*\*)?)\s*'
            r'(\w+)\s*;',
            re.MULTILINE
        )

        for match in prop_pattern.finditer(self.content):
            attributes = match.group(1).lower()
            prop_type = match.group(2).strip()
            prop_name = match.group(3)
            line_num = self.content[:match.start()].count('\n') + 1

            is_weak = 'weak' in attributes
            is_strong = 'strong' in attributes or 'retain' in attributes
            is_copy = 'copy' in attributes
            is_assign = 'assign' in attributes
            is_outlet = 'IBOutlet' in match.group(0)

            prop = {
                "name": prop_name,
                "type": prop_type,
                "attributes": attributes,
                "is_weak": is_weak,
                "is_strong": is_strong,
                "is_copy": is_copy,
                "is_assign": is_assign,
                "is_outlet": is_outlet,
                "line": line_num
            }

            # Find which class this belongs to
            for cls in self.classes:
                if cls.start_line <= line_num <= cls.end_line:
                    cls.properties.append(prop)
                    if 'delegate' in prop_name.lower():
                        cls.delegates.append(prop_name)
                    break

    def _parse_blocks(self):
        """Parse blocks in the code."""
        # Match blocks: ^{...} or ^returnType(params){...}
        block_pattern = re.compile(
            r'\^(?:\s*\([^)]*\))?\s*(?:\([^)]*\))?\s*\{',
            re.MULTILINE
        )

        for match in block_pattern.finditer(self.content):
            start_pos = match.start()
            start_line = self.content[:start_pos].count('\n') + 1

            # Find matching brace
            end_line = self._find_matching_brace(match.end() - 1)

            block_content = '\n'.join(self.lines[start_line-1:end_line])
            uses_self = bool(re.search(r'\bself\b', block_content))

            # Check for __weak typeof(self) weakSelf = self; before block
            lines_before = '\n'.join(self.lines[max(0, start_line-5):start_line])
            has_weak_self = bool(re.search(
                r'__weak\s+(?:typeof\s*\(self\)|__typeof__\s*\(self\)|id)\s*\w*[Ss]elf\s*=\s*self',
                lines_before
            ))

            block = ObjCBlock(
                start_line=start_line,
                end_line=end_line,
                uses_self=uses_self,
                has_weak_self_before=has_weak_self,
                content=block_content
            )

            # Associate with class
            for cls in self.classes:
                if cls.start_line <= start_line <= cls.end_line:
                    cls.blocks.append({
                        "line": start_line,
                        "uses_self": uses_self,
                        "has_weak_self": has_weak_self
                    })
                    break

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
        """Detect issues using regex patterns."""
        all_patterns = {**OBJC_PATTERNS, **PERFORMANCE_PATTERNS}

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

    def _detect_block_issues(self):
        """Detect block-related memory issues."""
        for cls in self.classes:
            for block_info in cls.blocks:
                if block_info["uses_self"] and not block_info["has_weak_self"]:
                    line_num = block_info["line"]
                    snippet = self._get_code_snippet(line_num)

                    # Check if this is a safe context
                    if self._is_safe_block_context(snippet, line_num):
                        continue

                    issue = LeakPattern(
                        type=LeakType.RETAIN_CYCLE_BLOCK,
                        severity=LeakSeverity.HIGH,
                        file_path=self.file_path,
                        line_number=line_num,
                        code_snippet=snippet,
                        message="Block captures 'self' without __weak reference",
                        suggestion="Add: __weak typeof(self) weakSelf = self; before block and use weakSelf",
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

    def _is_safe_block_context(self, snippet: str, line_num: int) -> bool:
        """Check if block is in a safe context."""
        # Get more context
        start = max(0, line_num - 5)
        context = '\n'.join(self.lines[start:line_num + 2])

        safe_patterns = [
            r'\[UIView\s+animate',
            r'\[UIView\s+transition',
            r'dispatch_once',
            r'\benumerateObjects',
            r'\bmakeConstraints:',
            r'\bsetNeedsLayout',
        ]

        for pattern in safe_patterns:
            if re.search(pattern, context, re.IGNORECASE):
                return True

        return False

    def _detect_property_issues(self):
        """Detect property-related memory issues."""
        for cls in self.classes:
            for prop in cls.properties:
                # Non-weak delegate
                if 'delegate' in prop['name'].lower():
                    if not prop['is_weak'] and not prop['is_assign']:
                        issue = LeakPattern(
                            type=LeakType.NON_WEAK_DELEGATE,
                            severity=LeakSeverity.HIGH,
                            file_path=self.file_path,
                            line_number=prop['line'],
                            code_snippet=self._get_code_snippet(prop['line']),
                            message=f"Delegate property '{prop['name']}' is not weak",
                            suggestion="Use @property (nonatomic, weak) for delegate",
                            context={"class": cls.name, "property": prop['name']}
                        )
                        self.issues.append(issue)

                # Strong IBOutlet
                if prop['is_outlet'] and prop['is_strong']:
                    issue = LeakPattern(
                        type=LeakType.STRONG_IBOUTLET,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=prop['line'],
                        code_snippet=self._get_code_snippet(prop['line']),
                        message=f"IBOutlet '{prop['name']}' is strong",
                        suggestion="Use weak for IBOutlet view properties",
                        context={"class": cls.name, "property": prop['name']}
                    )
                    self.issues.append(issue)

    def _detect_timer_observer_issues(self):
        """Detect timer and observer issues."""
        timer_pattern = re.compile(r'\[NSTimer\s+scheduledTimer', re.MULTILINE)
        observer_pattern = re.compile(
            r'\[\[NSNotificationCenter\s+defaultCenter\]\s+addObserver',
            re.MULTILINE
        )
        kvo_pattern = re.compile(r'addObserver:\s*self\s+forKeyPath:', re.MULTILINE)

        for cls in self.classes:
            if cls.start_line == 0:
                continue

            class_content = '\n'.join(self.lines[cls.start_line-1:cls.end_line])

            # Check timers
            for match in timer_pattern.finditer(class_content):
                line_num = cls.start_line + class_content[:match.start()].count('\n')
                cls.timers.append(line_num)

            # Check notification observers
            for match in observer_pattern.finditer(class_content):
                line_num = cls.start_line + class_content[:match.start()].count('\n')
                cls.observers.append(line_num)

            # Check KVO observers
            for match in kvo_pattern.finditer(class_content):
                line_num = cls.start_line + class_content[:match.start()].count('\n')
                cls.kvo_observers.append(line_num)

            # Check if properly cleaned up in dealloc
            dealloc_content = self._get_dealloc_content(cls)

            if cls.timers and 'invalidate' not in dealloc_content:
                for timer_line in cls.timers:
                    issue = LeakPattern(
                        type=LeakType.UNREMOVED_TIMER,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=timer_line,
                        code_snippet=self._get_code_snippet(timer_line),
                        message="NSTimer may not be invalidated in dealloc",
                        suggestion="Store timer and call [timer invalidate] in dealloc",
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

            if cls.observers and 'removeObserver' not in dealloc_content:
                for obs_line in cls.observers:
                    issue = LeakPattern(
                        type=LeakType.NOTIFICATION_NOT_REMOVED,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=obs_line,
                        code_snippet=self._get_code_snippet(obs_line),
                        message="NotificationCenter observer may not be removed in dealloc",
                        suggestion="Add [[NSNotificationCenter defaultCenter] removeObserver:self] in dealloc",
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

            if cls.kvo_observers and 'removeObserver' not in dealloc_content:
                for kvo_line in cls.kvo_observers:
                    issue = LeakPattern(
                        type=LeakType.KVO_NOT_REMOVED,
                        severity=LeakSeverity.HIGH,
                        file_path=self.file_path,
                        line_number=kvo_line,
                        code_snippet=self._get_code_snippet(kvo_line),
                        message="KVO observer may not be removed in dealloc",
                        suggestion="Call [object removeObserver:self forKeyPath:...] in dealloc",
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

    def _get_dealloc_content(self, cls: ObjCClass) -> str:
        """Get the content of dealloc method for a class."""
        class_content = '\n'.join(self.lines[cls.start_line-1:cls.end_line])
        dealloc_match = re.search(
            r'-\s*\(void\)\s*dealloc\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
            class_content,
            re.DOTALL
        )
        if dealloc_match:
            return dealloc_match.group(1)
        return ""

    def _detect_dealloc_issues(self):
        """Detect missing dealloc methods."""
        for cls in self.classes:
            # Skip header files and empty classes
            if self.is_header:
                continue

            needs_dealloc = (
                cls.timers or
                cls.observers or
                cls.kvo_observers or
                cls.delegates
            )

            if needs_dealloc and not cls.has_dealloc:
                issue = LeakPattern(
                    type=LeakType.MISSING_DEALLOC,
                    severity=LeakSeverity.LOW,
                    file_path=self.file_path,
                    line_number=cls.start_line,
                    code_snippet=self._get_code_snippet(cls.start_line),
                    message=f"Class '{cls.name}' should have dealloc for cleanup",
                    suggestion="Add -(void)dealloc { ... } to clean up resources",
                    context={"class": cls.name}
                )
                self.issues.append(issue)

    def _detect_arc_issues(self):
        """Detect ARC-related issues."""
        # Check for manual retain/release (shouldn't be used with ARC)
        manual_memory_pattern = re.compile(
            r'\[\s*\w+\s+(retain|release|autorelease)\s*\]',
            re.MULTILINE
        )

        for match in manual_memory_pattern.finditer(self.content):
            line_num = self.content[:match.start()].count('\n') + 1

            issue = LeakPattern(
                type=LeakType.STRONG_REFERENCE_CYCLE,
                severity=LeakSeverity.INFO,
                file_path=self.file_path,
                line_number=line_num,
                code_snippet=self._get_code_snippet(line_num),
                message="Manual memory management detected (retain/release/autorelease)",
                suggestion="If using ARC, remove manual memory management calls",
                context={}
            )
            self.issues.append(issue)

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
