"""
Objective-C Code Parser for Memory Leak Detection
Enhanced with precise location tracking and fix generation
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path

from .patterns import (
    LeakPattern, LeakSeverity, LeakType, FixSuggestion,
    OBJC_PATTERNS, PERFORMANCE_PATTERNS, get_all_patterns
)


@dataclass
class CodeLocation:
    """Precise code location."""
    line: int
    column: int
    end_line: int = 0
    end_column: int = 0
    offset: int = 0

    def to_dict(self) -> Dict:
        return {
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line or self.line,
            "end_column": self.end_column
        }


@dataclass
class ObjCClass:
    """Represents an Objective-C class."""
    name: str
    location: CodeLocation = None
    has_dealloc: bool = False
    properties: List[Dict] = field(default_factory=list)
    methods: List[Dict] = field(default_factory=list)
    blocks: List[Dict] = field(default_factory=list)
    delegates: List[str] = field(default_factory=list)
    timers: List[Dict] = field(default_factory=list)
    observers: List[Dict] = field(default_factory=list)
    kvo_observers: List[Dict] = field(default_factory=list)

    @property
    def start_line(self) -> int:
        return self.location.line if self.location else 0

    @property
    def end_line(self) -> int:
        return self.location.end_line if self.location else 0


@dataclass
class ObjCBlock:
    """Represents an Objective-C block."""
    location: CodeLocation
    uses_self: bool
    has_weak_self_before: bool
    content: str
    context_type: str = ""  # dispatch, completion, stored, etc.


class ObjCParser:
    """Parser for Objective-C source code files (.m, .mm, .h) with enhanced location tracking."""

    def __init__(self):
        self.classes: List[ObjCClass] = []
        self.issues: List[LeakPattern] = []
        self.file_path: str = ""
        self.lines: List[str] = []
        self.content: str = ""
        self.is_header: bool = False
        self.line_offsets: List[int] = []

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
                self._calculate_line_offsets()
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []

        # Parse structure
        self._parse_interfaces()
        self._parse_implementations()
        self._parse_properties()
        self._parse_blocks()

        # Detect issues with precise locations
        self._detect_pattern_issues()
        self._detect_block_issues()
        self._detect_property_issues()
        self._detect_timer_observer_issues()
        self._detect_dealloc_issues()
        self._detect_arc_issues()

        return self.issues

    def _calculate_line_offsets(self):
        """Calculate character offset for each line."""
        self.line_offsets = [0]
        offset = 0
        for line in self.lines:
            offset += len(line) + 1
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

    def _parse_interfaces(self):
        """Parse @interface declarations (usually in .h files)."""
        interface_pattern = re.compile(
            r'@interface\s+(\w+)\s*(?::\s*(\w+))?\s*(?:<[^>]+>)?\s*(?:\{[^}]*\})?',
            re.MULTILINE | re.DOTALL
        )

        for match in interface_pattern.finditer(self.content):
            class_name = match.group(1)
            location = self._get_location_from_match(match)

            # Find @end
            end_match = re.search(r'@end', self.content[match.end():])
            if end_match:
                end_offset = match.end() + end_match.end()
                end_loc = self._get_location_from_offset(end_offset)
                location.end_line = end_loc.line
            else:
                location.end_line = len(self.lines)

            objc_class = ObjCClass(
                name=class_name,
                location=location
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
            location = self._get_location_from_match(match)

            # Find @end
            end_match = re.search(r'@end', self.content[match.end():])
            if end_match:
                end_offset = match.end() + end_match.end()
                end_loc = self._get_location_from_offset(end_offset)
                location.end_line = end_loc.line
            else:
                location.end_line = len(self.lines)

            # Check if class already exists (from interface)
            existing = next((c for c in self.classes if c.name == class_name), None)
            if existing:
                existing.location.end_line = location.end_line
            else:
                objc_class = ObjCClass(
                    name=class_name,
                    location=location
                )
                self.classes.append(objc_class)

            # Check for dealloc
            impl_content = '\n'.join(self.lines[location.line-1:location.end_line])
            if re.search(r'-\s*\(void\)\s*dealloc\s*\{', impl_content):
                if existing:
                    existing.has_dealloc = True
                else:
                    self.classes[-1].has_dealloc = True

    def _parse_properties(self):
        """Parse @property declarations with precise locations."""
        prop_pattern = re.compile(
            r'@property\s*\(([^)]*)\)\s*'
            r'(IBOutlet\s+)?'
            r'(\w+(?:\s*\*)?)\s*'
            r'(\w+)\s*;',
            re.MULTILINE
        )

        for match in prop_pattern.finditer(self.content):
            attributes = match.group(1).lower()
            is_outlet = match.group(2) is not None
            prop_type = match.group(3).strip()
            prop_name = match.group(4)

            location = self._get_location_from_match(match)

            is_weak = 'weak' in attributes
            is_strong = 'strong' in attributes or 'retain' in attributes
            is_copy = 'copy' in attributes
            is_assign = 'assign' in attributes

            prop = {
                "name": prop_name,
                "type": prop_type,
                "attributes": attributes,
                "is_weak": is_weak,
                "is_strong": is_strong,
                "is_copy": is_copy,
                "is_assign": is_assign,
                "is_outlet": is_outlet,
                "line": location.line,
                "column": location.column,
                "raw_match": match.group(0)
            }

            # Find which class this belongs to
            for cls in self.classes:
                if cls.start_line <= location.line <= cls.end_line:
                    cls.properties.append(prop)
                    if 'delegate' in prop_name.lower():
                        cls.delegates.append(prop_name)
                    break

    def _parse_blocks(self):
        """Parse blocks in the code with context awareness."""
        block_pattern = re.compile(
            r'\^(?:\s*\([^)]*\))?\s*(?:\([^)]*\))?\s*\{',
            re.MULTILINE
        )

        for match in block_pattern.finditer(self.content):
            location = self._get_location_from_match(match)
            end_line = self._find_matching_brace(match.end() - 1)
            location.end_line = end_line

            block_content = '\n'.join(self.lines[location.line-1:end_line])
            uses_self = bool(re.search(r'\bself\b', block_content))

            # Check for __weak typeof(self) weakSelf = self; before block
            lines_before = '\n'.join(self.lines[max(0, location.line-6):location.line-1])
            has_weak_self = bool(re.search(
                r'__weak\s+(?:typeof\s*\(self\)|__typeof__\s*\(self\)|id)\s*\w*[Ss]elf\s*=\s*self',
                lines_before
            ))

            # Determine block context
            context_type = self._determine_block_context(match.start())

            block = ObjCBlock(
                location=location,
                uses_self=uses_self,
                has_weak_self_before=has_weak_self,
                content=block_content,
                context_type=context_type
            )

            # Associate with class
            for cls in self.classes:
                if cls.start_line <= location.line <= cls.end_line:
                    cls.blocks.append({
                        "location": location,
                        "line": location.line,
                        "column": location.column,
                        "uses_self": uses_self,
                        "has_weak_self": has_weak_self,
                        "context_type": context_type
                    })
                    break

    def _determine_block_context(self, offset: int) -> str:
        """Determine the context of a block."""
        prefix = self.content[max(0, offset-100):offset]

        if 'dispatch_async' in prefix or 'dispatch_' in prefix:
            return 'dispatch'
        elif 'NSTimer' in prefix:
            return 'timer'
        elif 'completion' in prefix.lower():
            return 'completion'
        elif 'UIView animate' in prefix:
            return 'animation'
        elif '=' in prefix[-20:]:
            return 'stored'

        return 'unknown'

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
        all_patterns = {**OBJC_PATTERNS, **PERFORMANCE_PATTERNS}

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
                is_auto_fixable=False
            )

        return None

    def _detect_block_issues(self):
        """Detect block-related memory issues."""
        for cls in self.classes:
            for block_info in cls.blocks:
                if block_info["uses_self"] and not block_info["has_weak_self"]:
                    location = block_info.get("location")
                    line_num = block_info["line"]
                    column = block_info.get("column", 1)

                    # Check if this is a safe context
                    context_type = block_info.get("context_type", "unknown")
                    if self._is_safe_block_context(context_type):
                        continue

                    snippet = self._get_code_snippet(line_num)

                    # Generate fix
                    fix = FixSuggestion(
                        original_code="^{ [self ...",
                        fixed_code="__weak typeof(self) weakSelf = self;\n^{ [weakSelf ...",
                        description="Add __weak self declaration before block and use weakSelf inside",
                        start_line=line_num,
                        end_line=location.end_line if location else line_num,
                        start_column=column,
                        is_auto_fixable=True
                    )

                    issue = LeakPattern(
                        type=LeakType.RETAIN_CYCLE_BLOCK,
                        severity=LeakSeverity.HIGH,
                        file_path=self.file_path,
                        line_number=line_num,
                        column=column,
                        end_line=location.end_line if location else line_num,
                        code_snippet=snippet,
                        message=f"Block captures 'self' without __weak reference (context: {context_type})",
                        suggestion="Add: __weak typeof(self) weakSelf = self; before block and use weakSelf",
                        fix=fix,
                        context={"class": cls.name, "context_type": context_type}
                    )
                    self.issues.append(issue)

    def _is_safe_block_context(self, context_type: str) -> bool:
        """Check if block context is typically safe."""
        safe_contexts = {'animation'}
        return context_type in safe_contexts

    def _detect_property_issues(self):
        """Detect property-related memory issues."""
        for cls in self.classes:
            for prop in cls.properties:
                # Non-weak delegate
                if 'delegate' in prop['name'].lower():
                    if not prop['is_weak'] and not prop['is_assign']:
                        original = prop.get('raw_match', '')
                        fixed = re.sub(r'\bstrong\b', 'weak', original)
                        fixed = re.sub(r'\bretain\b', 'weak', fixed)

                        if 'weak' not in fixed and 'assign' not in fixed:
                            fixed = original.replace(')', ', weak)', 1)

                        fix = FixSuggestion(
                            original_code=original,
                            fixed_code=fixed,
                            description="Change delegate property to weak",
                            start_line=prop['line'],
                            end_line=prop['line'],
                            start_column=prop.get('column', 1),
                            is_auto_fixable=True
                        )

                        issue = LeakPattern(
                            type=LeakType.NON_WEAK_DELEGATE,
                            severity=LeakSeverity.HIGH,
                            file_path=self.file_path,
                            line_number=prop['line'],
                            column=prop.get('column', 1),
                            code_snippet=self._get_code_snippet(prop['line']),
                            message=f"Delegate property '{prop['name']}' is not weak - creates retain cycle",
                            suggestion="Use @property (nonatomic, weak) for delegate",
                            fix=fix,
                            context={"class": cls.name, "property": prop['name']}
                        )
                        self.issues.append(issue)

                # Strong IBOutlet
                if prop['is_outlet'] and prop['is_strong']:
                    original = prop.get('raw_match', '')
                    fixed = re.sub(r'\bstrong\b', 'weak', original)

                    fix = FixSuggestion(
                        original_code=original,
                        fixed_code=fixed,
                        description="Change IBOutlet to weak",
                        start_line=prop['line'],
                        end_line=prop['line'],
                        start_column=prop.get('column', 1),
                        is_auto_fixable=True
                    )

                    issue = LeakPattern(
                        type=LeakType.STRONG_IBOUTLET,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=prop['line'],
                        column=prop.get('column', 1),
                        code_snippet=self._get_code_snippet(prop['line']),
                        message=f"IBOutlet '{prop['name']}' is strong - should be weak",
                        suggestion="Use weak for IBOutlet view properties",
                        fix=fix,
                        context={"class": cls.name, "property": prop['name']}
                    )
                    self.issues.append(issue)

    def _detect_timer_observer_issues(self):
        """Detect timer and observer issues with precise locations."""
        timer_pattern = re.compile(r'\[NSTimer\s+scheduledTimer', re.MULTILINE)
        observer_pattern = re.compile(
            r'\[\[NSNotificationCenter\s+defaultCenter\]\s+addObserver',
            re.MULTILINE
        )
        kvo_pattern = re.compile(r'\[\s*\w+\s+addObserver:\s*self\s+forKeyPath:', re.MULTILINE)

        for cls in self.classes:
            if cls.start_line == 0:
                continue

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

            # Check notification observers
            for match in observer_pattern.finditer(class_content):
                line_in_class = class_content[:match.start()].count('\n')
                line_num = cls.start_line + line_in_class
                column = match.start() - class_content.rfind('\n', 0, match.start())

                cls.observers.append({
                    "line": line_num,
                    "column": column
                })

            # Check KVO observers
            for match in kvo_pattern.finditer(class_content):
                line_in_class = class_content[:match.start()].count('\n')
                line_num = cls.start_line + line_in_class
                column = match.start() - class_content.rfind('\n', 0, match.start())

                cls.kvo_observers.append({
                    "line": line_num,
                    "column": column
                })

            # Check if properly cleaned up in dealloc
            dealloc_content = self._get_dealloc_content(cls)

            if cls.timers and 'invalidate' not in dealloc_content:
                for timer_info in cls.timers:
                    issue = LeakPattern(
                        type=LeakType.UNREMOVED_TIMER,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=timer_info["line"],
                        column=timer_info.get("column", 1),
                        code_snippet=self._get_code_snippet(timer_info["line"]),
                        message="NSTimer may not be invalidated in dealloc",
                        suggestion="Store timer and call [timer invalidate] in dealloc",
                        fix=FixSuggestion(
                            original_code="// No dealloc cleanup",
                            fixed_code="- (void)dealloc {\n    [self.timer invalidate];\n    self.timer = nil;\n}",
                            description="Add timer invalidation in dealloc",
                            is_auto_fixable=False
                        ),
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

            if cls.observers and 'removeObserver' not in dealloc_content:
                for obs_info in cls.observers:
                    issue = LeakPattern(
                        type=LeakType.NOTIFICATION_NOT_REMOVED,
                        severity=LeakSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_number=obs_info["line"],
                        column=obs_info.get("column", 1),
                        code_snippet=self._get_code_snippet(obs_info["line"]),
                        message="NotificationCenter observer may not be removed in dealloc",
                        suggestion="Add [[NSNotificationCenter defaultCenter] removeObserver:self] in dealloc",
                        fix=FixSuggestion(
                            original_code="// No dealloc cleanup",
                            fixed_code="- (void)dealloc {\n    [[NSNotificationCenter defaultCenter] removeObserver:self];\n}",
                            description="Add observer removal in dealloc",
                            is_auto_fixable=False
                        ),
                        context={"class": cls.name}
                    )
                    self.issues.append(issue)

            if cls.kvo_observers and 'removeObserver' not in dealloc_content:
                for kvo_info in cls.kvo_observers:
                    issue = LeakPattern(
                        type=LeakType.KVO_NOT_REMOVED,
                        severity=LeakSeverity.HIGH,
                        file_path=self.file_path,
                        line_number=kvo_info["line"],
                        column=kvo_info.get("column", 1),
                        code_snippet=self._get_code_snippet(kvo_info["line"]),
                        message="KVO observer may not be removed in dealloc - will crash!",
                        suggestion="Call [object removeObserver:self forKeyPath:...] in dealloc",
                        fix=FixSuggestion(
                            original_code="// No dealloc cleanup",
                            fixed_code="- (void)dealloc {\n    [self.someObject removeObserver:self forKeyPath:@\"property\"];\n}",
                            description="Add KVO observer removal in dealloc",
                            is_auto_fixable=False
                        ),
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
                    severity=LeakSeverity.INFO,
                    file_path=self.file_path,
                    line_number=cls.start_line,
                    column=1,
                    end_line=cls.end_line,
                    code_snippet=self._get_code_snippet(cls.start_line),
                    message=f"Class '{cls.name}' should have dealloc for cleanup",
                    suggestion="Add -(void)dealloc { ... } to clean up resources",
                    fix=FixSuggestion(
                        original_code="// No dealloc",
                        fixed_code='- (void)dealloc {\n    NSLog(@"%@ deallocated", NSStringFromClass([self class]));\n}',
                        description="Add dealloc method for debugging and cleanup",
                        is_auto_fixable=False
                    ),
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
            location = self._get_location_from_match(match)

            issue = LeakPattern(
                type=LeakType.STRONG_REFERENCE_CYCLE,
                severity=LeakSeverity.INFO,
                file_path=self.file_path,
                line_number=location.line,
                column=location.column,
                code_snippet=self._get_code_snippet(location.line),
                message="Manual memory management detected (retain/release/autorelease)",
                suggestion="If using ARC, remove manual memory management calls",
                fix=FixSuggestion(
                    original_code=match.group(0),
                    fixed_code="// Remove under ARC",
                    description="Remove manual memory management if using ARC",
                    is_auto_fixable=False
                ),
                context={}
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
