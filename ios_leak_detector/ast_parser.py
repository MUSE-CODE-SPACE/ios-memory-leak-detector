"""
AST-like Parser for Swift and Objective-C
Provides scope-aware parsing with symbol table for accurate leak detection.

This module implements a lightweight parser that:
- Tracks nested scopes (classes, methods, closures, blocks)
- Builds symbol tables for properties, methods, and variables
- Detects self references with proper context
- Supports cross-file analysis for retain cycles
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from enum import Enum
from pathlib import Path


class ScopeType(Enum):
    """Types of scopes in Swift/Objective-C."""
    FILE = "file"
    CLASS = "class"
    STRUCT = "struct"
    ENUM = "enum"
    EXTENSION = "extension"
    PROTOCOL = "protocol"
    METHOD = "method"
    INIT = "init"
    DEINIT = "deinit"
    CLOSURE = "closure"
    BLOCK = "block"  # Objective-C block
    IF = "if"
    FOR = "for"
    WHILE = "while"
    SWITCH = "switch"
    GUARD = "guard"


class SymbolType(Enum):
    """Types of symbols."""
    CLASS = "class"
    STRUCT = "struct"
    PROPERTY = "property"
    METHOD = "method"
    VARIABLE = "variable"
    PARAMETER = "parameter"
    CLOSURE = "closure"
    DELEGATE = "delegate"
    IBOUTLET = "iboutlet"
    TIMER = "timer"
    OBSERVER = "observer"


class ReferenceStrength(Enum):
    """Reference strength for properties."""
    STRONG = "strong"
    WEAK = "weak"
    UNOWNED = "unowned"


@dataclass
class Symbol:
    """Represents a symbol in the code."""
    name: str
    type: SymbolType
    line: int
    column: int
    strength: ReferenceStrength = ReferenceStrength.STRONG
    type_annotation: str = ""
    is_optional: bool = False
    is_lazy: bool = False
    parent_scope: Optional[str] = None

    def is_weak_reference(self) -> bool:
        return self.strength in (ReferenceStrength.WEAK, ReferenceStrength.UNOWNED)


@dataclass
class Scope:
    """Represents a code scope."""
    type: ScopeType
    name: str
    start_line: int
    start_col: int
    end_line: int = -1
    end_col: int = -1
    parent: Optional['Scope'] = None
    symbols: Dict[str, Symbol] = field(default_factory=dict)
    children: List['Scope'] = field(default_factory=list)

    # Closure-specific
    capture_list: List[str] = field(default_factory=list)  # [weak self], [unowned self]
    has_weak_self: bool = False
    has_unowned_self: bool = False
    self_references: List[Tuple[int, int]] = field(default_factory=list)  # (line, col) of self usages

    def get_full_name(self) -> str:
        """Get fully qualified name including parent scopes."""
        if self.parent and self.parent.type != ScopeType.FILE:
            return f"{self.parent.get_full_name()}.{self.name}"
        return self.name


@dataclass
class SelfReference:
    """Tracks a reference to 'self'."""
    line: int
    column: int
    scope: Scope
    is_captured_weakly: bool
    context: str  # e.g., "closure", "block", "method"
    enclosing_closure: Optional[Scope] = None


@dataclass
class RetainCycleCandidate:
    """Potential retain cycle detected."""
    file_path: str
    line: int
    column: int
    description: str
    scope_chain: List[str]  # Names of scopes leading to the issue
    self_reference: Optional[SelfReference] = None
    confidence: float = 1.0  # 0.0 to 1.0


class SwiftASTParser:
    """
    Scope-aware parser for Swift code.
    Builds a symbol table and tracks closures/self references.
    """

    def __init__(self):
        self.scopes: List[Scope] = []
        self.current_scope: Optional[Scope] = None
        self.root_scope: Optional[Scope] = None
        self.symbols: Dict[str, Symbol] = {}
        self.self_references: List[SelfReference] = []
        self.retain_cycle_candidates: List[RetainCycleCandidate] = []
        self.lines: List[str] = []
        self.file_path: str = ""

        # Patterns for Swift parsing
        self.patterns = {
            'class': re.compile(r'\b(class|actor)\s+(\w+)'),
            'struct': re.compile(r'\bstruct\s+(\w+)'),
            'enum': re.compile(r'\benum\s+(\w+)'),
            'extension': re.compile(r'\bextension\s+(\w+)'),
            'protocol': re.compile(r'\bprotocol\s+(\w+)'),
            'func': re.compile(r'\bfunc\s+(\w+)'),
            'init': re.compile(r'\binit\s*\('),
            'deinit': re.compile(r'\bdeinit\s*\{'),
            'property': re.compile(
                r'(?:(@\w+\s+)*)'  # Attributes like @IBOutlet
                r'(?:(private|public|internal|fileprivate|open)\s+)?'
                r'(?:(weak|unowned)\s+)?'
                r'(?:(lazy)\s+)?'
                r'(var|let)\s+(\w+)\s*:\s*([^={\n]+)'
            ),
            'closure_start': re.compile(r'\{(?:\s*\[([^\]]*)\])?\s*(?:\([^)]*\)\s*)?(?:->.*?)?\s*in|\{\s*$'),
            'capture_list': re.compile(r'\[((?:weak|unowned)\s+\w+(?:\s*,\s*(?:weak|unowned)\s+\w+)*)\]'),
            'self_ref': re.compile(r'\bself\b'),
            'delegate_property': re.compile(r'(?:weak\s+)?(var|let)\s+(\w*[dD]elegate\w*)\s*:'),
            'timer': re.compile(r'Timer\.(scheduledTimer|publish)'),
            'notification': re.compile(r'NotificationCenter\.default\.(addObserver|publisher)'),
        }

    def parse(self, content: str, file_path: str = "") -> Scope:
        """Parse Swift code and build scope tree."""
        self.file_path = file_path
        self.lines = content.split('\n')
        self.scopes = []
        self.symbols = {}
        self.self_references = []
        self.retain_cycle_candidates = []

        # Create root file scope
        self.root_scope = Scope(
            type=ScopeType.FILE,
            name=Path(file_path).stem if file_path else "unknown",
            start_line=1,
            start_col=0
        )
        self.current_scope = self.root_scope
        self.scopes.append(self.root_scope)

        # Track brace depth
        brace_stack: List[Tuple[int, int, str]] = []  # (line, col, type)

        for line_num, line in enumerate(self.lines, 1):
            self._parse_line(line, line_num, brace_stack)

        # Close any remaining scopes
        self.root_scope.end_line = len(self.lines)

        # Analyze for retain cycles
        self._analyze_retain_cycles()

        return self.root_scope

    def _parse_line(self, line: str, line_num: int, brace_stack: List):
        """Parse a single line of code."""
        # Skip comments
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
            return

        # Check for class/struct/enum definitions
        for scope_type, pattern in [
            (ScopeType.CLASS, self.patterns['class']),
            (ScopeType.STRUCT, self.patterns['struct']),
            (ScopeType.ENUM, self.patterns['enum']),
            (ScopeType.EXTENSION, self.patterns['extension']),
            (ScopeType.PROTOCOL, self.patterns['protocol']),
        ]:
            match = pattern.search(line)
            if match:
                name = match.group(2) if scope_type == ScopeType.CLASS else match.group(1)
                col = match.start()
                self._enter_scope(scope_type, name, line_num, col)
                # Register as symbol
                self.symbols[name] = Symbol(
                    name=name,
                    type=SymbolType.CLASS if scope_type == ScopeType.CLASS else SymbolType.STRUCT,
                    line=line_num,
                    column=col,
                    parent_scope=self.current_scope.get_full_name() if self.current_scope else None
                )

        # Check for function definitions
        func_match = self.patterns['func'].search(line)
        if func_match:
            self._enter_scope(ScopeType.METHOD, func_match.group(1), line_num, func_match.start())

        init_match = self.patterns['init'].search(line)
        if init_match:
            self._enter_scope(ScopeType.INIT, "init", line_num, init_match.start())

        deinit_match = self.patterns['deinit'].search(line)
        if deinit_match:
            self._enter_scope(ScopeType.DEINIT, "deinit", line_num, deinit_match.start())

        # Check for properties
        prop_match = self.patterns['property'].search(line)
        if prop_match:
            self._parse_property(prop_match, line_num)

        # Check for closures with capture lists
        self._check_closures(line, line_num)

        # Check for self references
        for match in self.patterns['self_ref'].finditer(line):
            self._record_self_reference(line_num, match.start())

        # Track braces for scope management
        self._track_braces(line, line_num, brace_stack)

    def _parse_property(self, match, line_num: int):
        """Parse a property declaration."""
        groups = match.groups()
        # Groups: (attributes, access, weak/unowned, lazy, var/let, name, type)
        attributes = groups[0] or ""
        access = groups[1] or ""
        strength_str = groups[2]
        is_lazy = groups[3] is not None
        var_let = groups[4]
        name = groups[5]
        type_ann = groups[6].strip()

        # Determine reference strength
        strength = ReferenceStrength.STRONG
        if strength_str == 'weak':
            strength = ReferenceStrength.WEAK
        elif strength_str == 'unowned':
            strength = ReferenceStrength.UNOWNED

        # Determine symbol type
        symbol_type = SymbolType.PROPERTY
        if '@IBOutlet' in attributes:
            symbol_type = SymbolType.IBOUTLET
        elif 'delegate' in name.lower():
            symbol_type = SymbolType.DELEGATE

        is_optional = '?' in type_ann or 'Optional' in type_ann

        symbol = Symbol(
            name=name,
            type=symbol_type,
            line=line_num,
            column=match.start(),
            strength=strength,
            type_annotation=type_ann,
            is_optional=is_optional,
            is_lazy=is_lazy,
            parent_scope=self.current_scope.get_full_name() if self.current_scope else None
        )

        self.symbols[name] = symbol
        if self.current_scope:
            self.current_scope.symbols[name] = symbol

    def _check_closures(self, line: str, line_num: int):
        """Check for closure definitions and capture lists."""
        # Look for closure with capture list
        capture_match = self.patterns['capture_list'].search(line)
        if capture_match:
            capture_content = capture_match.group(1)
            has_weak_self = 'weak self' in capture_content or 'weak `self`' in capture_content
            has_unowned_self = 'unowned self' in capture_content or 'unowned `self`' in capture_content

            # Find the closure scope or create one
            if self.current_scope and self.current_scope.type == ScopeType.CLOSURE:
                self.current_scope.has_weak_self = has_weak_self
                self.current_scope.has_unowned_self = has_unowned_self
                self.current_scope.capture_list = capture_content.split(',')

        # Look for closure start (might need to create scope)
        closure_match = self.patterns['closure_start'].search(line)
        if closure_match and '{' in line:
            # Check if it's a trailing closure
            col = line.find('{')
            self._enter_scope(ScopeType.CLOSURE, f"closure_{line_num}", line_num, col)

            # Check capture list in the same match
            if capture_match:
                capture_content = capture_match.group(1)
                self.current_scope.has_weak_self = 'weak self' in capture_content
                self.current_scope.has_unowned_self = 'unowned self' in capture_content

    def _record_self_reference(self, line_num: int, col: int):
        """Record a reference to self."""
        if not self.current_scope:
            return

        # Find enclosing closure if any
        enclosing_closure = None
        scope = self.current_scope
        while scope:
            if scope.type == ScopeType.CLOSURE:
                enclosing_closure = scope
                break
            scope = scope.parent

        is_captured_weakly = False
        if enclosing_closure:
            is_captured_weakly = enclosing_closure.has_weak_self or enclosing_closure.has_unowned_self

        context = "method"
        if self.current_scope.type == ScopeType.CLOSURE:
            context = "closure"
        elif self.current_scope.type in (ScopeType.INIT, ScopeType.DEINIT):
            context = self.current_scope.type.value

        ref = SelfReference(
            line=line_num,
            column=col,
            scope=self.current_scope,
            is_captured_weakly=is_captured_weakly,
            context=context,
            enclosing_closure=enclosing_closure
        )
        self.self_references.append(ref)

        if self.current_scope:
            self.current_scope.self_references.append((line_num, col))

    def _track_braces(self, line: str, line_num: int, brace_stack: List):
        """Track opening and closing braces for scope management."""
        # Simple brace counting (doesn't handle strings/comments perfectly)
        in_string = False
        string_char = None

        for i, char in enumerate(line):
            if char in '"\'':
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char and (i == 0 or line[i-1] != '\\'):
                    in_string = False

            if in_string:
                continue

            if char == '{':
                brace_stack.append((line_num, i, 'brace'))
            elif char == '}':
                if brace_stack:
                    brace_stack.pop()
                    self._exit_scope(line_num, i)

    def _enter_scope(self, scope_type: ScopeType, name: str, line: int, col: int):
        """Enter a new scope."""
        new_scope = Scope(
            type=scope_type,
            name=name,
            start_line=line,
            start_col=col,
            parent=self.current_scope
        )

        if self.current_scope:
            self.current_scope.children.append(new_scope)

        self.scopes.append(new_scope)
        self.current_scope = new_scope

    def _exit_scope(self, line: int, col: int):
        """Exit current scope."""
        if self.current_scope and self.current_scope.parent:
            self.current_scope.end_line = line
            self.current_scope.end_col = col
            self.current_scope = self.current_scope.parent

    def _analyze_retain_cycles(self):
        """Analyze parsed code for potential retain cycles."""
        # Check all self references in closures
        for ref in self.self_references:
            if ref.context == "closure" and not ref.is_captured_weakly:
                # This is a potential retain cycle
                scope_chain = []
                scope = ref.scope
                while scope:
                    scope_chain.insert(0, f"{scope.type.value}:{scope.name}")
                    scope = scope.parent

                candidate = RetainCycleCandidate(
                    file_path=self.file_path,
                    line=ref.line,
                    column=ref.column,
                    description=f"'self' captured strongly in closure without [weak self]",
                    scope_chain=scope_chain,
                    self_reference=ref,
                    confidence=0.9
                )
                self.retain_cycle_candidates.append(candidate)

        # Check for non-weak delegates
        for name, symbol in self.symbols.items():
            if symbol.type == SymbolType.DELEGATE and not symbol.is_weak_reference():
                candidate = RetainCycleCandidate(
                    file_path=self.file_path,
                    line=symbol.line,
                    column=symbol.column,
                    description=f"Delegate '{name}' is not weak - potential retain cycle",
                    scope_chain=[symbol.parent_scope or ""],
                    confidence=0.95
                )
                self.retain_cycle_candidates.append(candidate)

            # Check IBOutlets
            if symbol.type == SymbolType.IBOUTLET and not symbol.is_weak_reference():
                candidate = RetainCycleCandidate(
                    file_path=self.file_path,
                    line=symbol.line,
                    column=symbol.column,
                    description=f"IBOutlet '{name}' should typically be weak",
                    scope_chain=[symbol.parent_scope or ""],
                    confidence=0.7  # Lower confidence as strong IBOutlets are sometimes intentional
                )
                self.retain_cycle_candidates.append(candidate)

    def get_class_info(self) -> Dict[str, Dict]:
        """Get information about all classes/structs in the file."""
        classes = {}
        for scope in self.scopes:
            if scope.type in (ScopeType.CLASS, ScopeType.STRUCT):
                classes[scope.name] = {
                    'type': scope.type.value,
                    'line': scope.start_line,
                    'properties': {k: v for k, v in scope.symbols.items() if v.type == SymbolType.PROPERTY},
                    'delegates': {k: v for k, v in scope.symbols.items() if v.type == SymbolType.DELEGATE},
                    'has_deinit': any(c.type == ScopeType.DEINIT for c in scope.children),
                    'methods': [c.name for c in scope.children if c.type == ScopeType.METHOD],
                }
        return classes

    def get_closures_with_self(self) -> List[Scope]:
        """Get all closures that reference self."""
        return [s for s in self.scopes if s.type == ScopeType.CLOSURE and s.self_references]

    def get_unsafe_closures(self) -> List[Scope]:
        """Get closures that capture self without weak/unowned."""
        unsafe = []
        for scope in self.scopes:
            if scope.type == ScopeType.CLOSURE and scope.self_references:
                if not scope.has_weak_self and not scope.has_unowned_self:
                    unsafe.append(scope)
        return unsafe


class ObjCASTParser:
    """
    Scope-aware parser for Objective-C code.
    Similar to SwiftASTParser but handles Objective-C syntax.
    """

    def __init__(self):
        self.scopes: List[Scope] = []
        self.current_scope: Optional[Scope] = None
        self.root_scope: Optional[Scope] = None
        self.symbols: Dict[str, Symbol] = {}
        self.self_references: List[SelfReference] = []
        self.retain_cycle_candidates: List[RetainCycleCandidate] = []
        self.lines: List[str] = []
        self.file_path: str = ""

        self.patterns = {
            'interface': re.compile(r'@interface\s+(\w+)'),
            'implementation': re.compile(r'@implementation\s+(\w+)'),
            'end': re.compile(r'@end\b'),
            'method': re.compile(r'^[-+]\s*\([^)]+\)\s*(\w+)'),
            'property': re.compile(
                r'@property\s*\(([^)]*)\)\s*'
                r'(?:IBOutlet\s+)?'
                r'(\w+(?:\s*<[^>]+>)?)\s*\*?\s*(\w+)'
            ),
            'block_start': re.compile(r'\^\s*(?:\([^)]*\))?\s*\{'),
            'weak_self': re.compile(r'__weak\s+(?:typeof\s*\(\s*self\s*\)|id)\s+(\w+)\s*=\s*self'),
            'self_ref': re.compile(r'\bself\b'),
            'dealloc': re.compile(r'-\s*\(\s*void\s*\)\s*dealloc\b'),
        }

    def parse(self, content: str, file_path: str = "") -> Scope:
        """Parse Objective-C code and build scope tree."""
        self.file_path = file_path
        self.lines = content.split('\n')
        self.scopes = []
        self.symbols = {}
        self.self_references = []
        self.retain_cycle_candidates = []

        self.root_scope = Scope(
            type=ScopeType.FILE,
            name=Path(file_path).stem if file_path else "unknown",
            start_line=1,
            start_col=0
        )
        self.current_scope = self.root_scope
        self.scopes.append(self.root_scope)

        in_block = False
        block_scope: Optional[Scope] = None
        has_weak_self_declaration = False
        weak_self_var = None
        brace_depth = 0
        block_brace_depth = 0

        for line_num, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # Skip comments
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # Check for @interface/@implementation
            interface_match = self.patterns['interface'].search(line)
            if interface_match:
                self._enter_scope(ScopeType.CLASS, interface_match.group(1), line_num, interface_match.start())

            impl_match = self.patterns['implementation'].search(line)
            if impl_match:
                self._enter_scope(ScopeType.CLASS, impl_match.group(1), line_num, impl_match.start())

            # Check for @end
            if self.patterns['end'].search(line):
                self._exit_scope(line_num, 0)

            # Check for method
            method_match = self.patterns['method'].search(line)
            if method_match:
                self._enter_scope(ScopeType.METHOD, method_match.group(1), line_num, method_match.start())
                has_weak_self_declaration = False
                weak_self_var = None

            # Check for dealloc
            if self.patterns['dealloc'].search(line):
                self._enter_scope(ScopeType.DEINIT, "dealloc", line_num, 0)

            # Check for property
            prop_match = self.patterns['property'].search(line)
            if prop_match:
                self._parse_property_objc(prop_match, line_num)

            # Check for __weak self declaration
            weak_match = self.patterns['weak_self'].search(line)
            if weak_match:
                has_weak_self_declaration = True
                weak_self_var = weak_match.group(1)

            # Check for block start
            if self.patterns['block_start'].search(line):
                in_block = True
                block_brace_depth = brace_depth + line.count('{')
                block_scope = Scope(
                    type=ScopeType.BLOCK,
                    name=f"block_{line_num}",
                    start_line=line_num,
                    start_col=line.find('^'),
                    parent=self.current_scope,
                    has_weak_self=has_weak_self_declaration
                )
                if self.current_scope:
                    self.current_scope.children.append(block_scope)
                self.scopes.append(block_scope)
                self.current_scope = block_scope

            # Check for self references
            for match in self.patterns['self_ref'].finditer(line):
                # Check if this is actually using weakSelf instead
                if weak_self_var and weak_self_var in line:
                    continue  # Using weak reference

                self._record_self_reference_objc(line_num, match.start(), in_block, has_weak_self_declaration)

            # Track braces
            brace_depth += line.count('{') - line.count('}')

            if in_block and brace_depth < block_brace_depth:
                in_block = False
                if block_scope:
                    block_scope.end_line = line_num
                self._exit_scope(line_num, 0)
                block_scope = None

        self.root_scope.end_line = len(self.lines)
        self._analyze_retain_cycles_objc()

        return self.root_scope

    def _parse_property_objc(self, match, line_num: int):
        """Parse an Objective-C property declaration."""
        attributes = match.group(1)
        type_name = match.group(2)
        prop_name = match.group(3)

        # Determine strength from attributes
        strength = ReferenceStrength.STRONG
        if 'weak' in attributes:
            strength = ReferenceStrength.WEAK
        elif 'assign' in attributes:
            strength = ReferenceStrength.WEAK  # assign is like weak for objects

        # Determine symbol type
        symbol_type = SymbolType.PROPERTY
        if 'IBOutlet' in self.lines[line_num - 1]:
            symbol_type = SymbolType.IBOUTLET
        elif 'delegate' in prop_name.lower():
            symbol_type = SymbolType.DELEGATE

        symbol = Symbol(
            name=prop_name,
            type=symbol_type,
            line=line_num,
            column=match.start(),
            strength=strength,
            type_annotation=type_name,
            parent_scope=self.current_scope.get_full_name() if self.current_scope else None
        )

        self.symbols[prop_name] = symbol
        if self.current_scope:
            self.current_scope.symbols[prop_name] = symbol

    def _record_self_reference_objc(self, line_num: int, col: int, in_block: bool, has_weak_self: bool):
        """Record a reference to self in Objective-C."""
        if not self.current_scope:
            return

        context = "block" if in_block else "method"

        ref = SelfReference(
            line=line_num,
            column=col,
            scope=self.current_scope,
            is_captured_weakly=has_weak_self,
            context=context
        )
        self.self_references.append(ref)

        if self.current_scope:
            self.current_scope.self_references.append((line_num, col))

    def _enter_scope(self, scope_type: ScopeType, name: str, line: int, col: int):
        """Enter a new scope."""
        new_scope = Scope(
            type=scope_type,
            name=name,
            start_line=line,
            start_col=col,
            parent=self.current_scope
        )

        if self.current_scope:
            self.current_scope.children.append(new_scope)

        self.scopes.append(new_scope)
        self.current_scope = new_scope

    def _exit_scope(self, line: int, col: int):
        """Exit current scope."""
        if self.current_scope and self.current_scope.parent:
            self.current_scope.end_line = line
            self.current_scope.end_col = col
            self.current_scope = self.current_scope.parent

    def _analyze_retain_cycles_objc(self):
        """Analyze for retain cycles in Objective-C code."""
        # Check self references in blocks
        for ref in self.self_references:
            if ref.context == "block" and not ref.is_captured_weakly:
                scope_chain = []
                scope = ref.scope
                while scope:
                    scope_chain.insert(0, f"{scope.type.value}:{scope.name}")
                    scope = scope.parent

                candidate = RetainCycleCandidate(
                    file_path=self.file_path,
                    line=ref.line,
                    column=ref.column,
                    description="'self' captured in block without __weak - potential retain cycle",
                    scope_chain=scope_chain,
                    self_reference=ref,
                    confidence=0.9
                )
                self.retain_cycle_candidates.append(candidate)

        # Check non-weak delegates and IBOutlets
        for name, symbol in self.symbols.items():
            if symbol.type == SymbolType.DELEGATE and not symbol.is_weak_reference():
                candidate = RetainCycleCandidate(
                    file_path=self.file_path,
                    line=symbol.line,
                    column=symbol.column,
                    description=f"Delegate '{name}' should be weak",
                    scope_chain=[symbol.parent_scope or ""],
                    confidence=0.95
                )
                self.retain_cycle_candidates.append(candidate)


class CrossFileAnalyzer:
    """
    Analyzes retain cycles across multiple files.
    Detects A -> B -> A reference patterns.
    """

    def __init__(self):
        self.files: Dict[str, Scope] = {}  # file_path -> root scope
        self.all_symbols: Dict[str, List[Symbol]] = {}  # symbol_name -> list of definitions
        self.type_references: Dict[str, Set[str]] = {}  # class -> set of referenced classes

    def add_file(self, file_path: str, root_scope: Scope, symbols: Dict[str, Symbol]):
        """Add a parsed file to the analyzer."""
        self.files[file_path] = root_scope

        for name, symbol in symbols.items():
            if name not in self.all_symbols:
                self.all_symbols[name] = []
            self.all_symbols[name].append(symbol)

            # Track type references
            if symbol.type_annotation:
                # Extract referenced types from type annotation
                type_refs = re.findall(r'\b([A-Z]\w+)\b', symbol.type_annotation)
                parent = symbol.parent_scope or ""
                if parent not in self.type_references:
                    self.type_references[parent] = set()
                self.type_references[parent].update(type_refs)

    def find_cross_file_cycles(self) -> List[RetainCycleCandidate]:
        """Find retain cycles that span multiple files."""
        cycles = []

        # Build reference graph
        for class_name, refs in self.type_references.items():
            for ref in refs:
                # Check if ref also references class_name (direct cycle)
                if ref in self.type_references and class_name in self.type_references[ref]:
                    # Check if either reference is weak
                    is_weak = False
                    for symbols in self.all_symbols.values():
                        for sym in symbols:
                            if sym.type_annotation and ref in sym.type_annotation:
                                if sym.is_weak_reference():
                                    is_weak = True
                                    break

                    if not is_weak:
                        cycles.append(RetainCycleCandidate(
                            file_path="cross-file",
                            line=0,
                            column=0,
                            description=f"Potential retain cycle: {class_name} <-> {ref}",
                            scope_chain=[class_name, ref],
                            confidence=0.7
                        ))

        return cycles


def parse_swift_file(file_path: str) -> Tuple[Scope, Dict[str, Symbol], List[RetainCycleCandidate]]:
    """Convenience function to parse a Swift file."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    parser = SwiftASTParser()
    root = parser.parse(content, file_path)
    return root, parser.symbols, parser.retain_cycle_candidates


def parse_objc_file(file_path: str) -> Tuple[Scope, Dict[str, Symbol], List[RetainCycleCandidate]]:
    """Convenience function to parse an Objective-C file."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    parser = ObjCASTParser()
    root = parser.parse(content, file_path)
    return root, parser.symbols, parser.retain_cycle_candidates
