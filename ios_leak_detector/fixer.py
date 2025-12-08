"""
Auto-Fix Generator for iOS Memory Leak Issues
Generates exact code fixes with file locations
"""

import re
import os
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

from .patterns import (
    LeakPattern, LeakType, LeakSeverity, FixSuggestion,
    SWIFT_PATTERNS, OBJC_PATTERNS, SWIFTUI_PATTERNS, PERFORMANCE_PATTERNS,
    get_all_patterns
)


@dataclass
class FileFix:
    """Represents all fixes for a single file."""
    file_path: str
    original_content: str
    fixed_content: str
    fixes: List[FixSuggestion] = field(default_factory=list)
    backup_path: Optional[str] = None

    def has_changes(self) -> bool:
        return self.original_content != self.fixed_content

    def get_diff(self) -> str:
        """Generate unified diff between original and fixed content."""
        import difflib
        original_lines = self.original_content.splitlines(keepends=True)
        fixed_lines = self.fixed_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f'a/{Path(self.file_path).name}',
            tofile=f'b/{Path(self.file_path).name}',
            lineterm=''
        )
        return ''.join(diff)

    def get_inline_diff(self) -> List[Dict]:
        """Generate inline diff showing changes per line."""
        import difflib
        original_lines = self.original_content.splitlines()
        fixed_lines = self.fixed_content.splitlines()

        differ = difflib.Differ()
        diff_result = list(differ.compare(original_lines, fixed_lines))

        changes = []
        line_num = 0

        for line in diff_result:
            if line.startswith('  '):  # Unchanged
                line_num += 1
            elif line.startswith('- '):  # Removed
                line_num += 1
                changes.append({
                    'type': 'removed',
                    'line': line_num,
                    'content': line[2:]
                })
            elif line.startswith('+ '):  # Added
                changes.append({
                    'type': 'added',
                    'line': line_num,
                    'content': line[2:]
                })
            elif line.startswith('? '):  # Hint line
                continue

        return changes


class CodeFixer:
    """Generates and applies code fixes for detected issues."""

    def __init__(self, dry_run: bool = True, backup: bool = True):
        """
        Initialize the fixer.

        Args:
            dry_run: If True, don't actually modify files
            backup: If True, create backup before modifying
        """
        self.dry_run = dry_run
        self.backup = backup
        self.all_patterns = get_all_patterns("all")

    def generate_fix(self, issue: LeakPattern, file_content: str) -> Optional[FixSuggestion]:
        """
        Generate a fix suggestion for an issue.

        Args:
            issue: The detected leak pattern
            file_content: Full content of the source file

        Returns:
            FixSuggestion with original and fixed code, or None if no fix available
        """
        lines = file_content.split('\n')

        # Get the pattern data
        pattern_name = issue.context.get('pattern_name', '')
        pattern_data = self.all_patterns.get(pattern_name, {})

        # Get fix generator function if available
        fix_generator = pattern_data.get('fix_generator')

        if fix_generator:
            # Extract the relevant code section
            start_line = max(0, issue.line_number - 1)
            end_line = min(len(lines), issue.end_line if issue.end_line else issue.line_number + 5)

            original_code = '\n'.join(lines[start_line:end_line])

            # Generate fix
            try:
                fix = fix_generator(original_code, issue.context)
                fix.start_line = issue.line_number
                fix.end_line = end_line
                fix.start_column = issue.column
                return fix
            except Exception as e:
                print(f"Warning: Fix generation failed for {pattern_name}: {e}")
                return None

        # If no fix generator, try to create fix based on type
        return self._generate_type_based_fix(issue, lines)

    def _generate_type_based_fix(self, issue: LeakPattern, lines: List[str]) -> Optional[FixSuggestion]:
        """Generate fix based on issue type when no specific generator exists."""
        line_idx = issue.line_number - 1
        if line_idx < 0 or line_idx >= len(lines):
            return None

        original_line = lines[line_idx]
        fixed_line = original_line

        if issue.type == LeakType.NON_WEAK_DELEGATE:
            # Swift: var delegate: -> weak var delegate:
            if 'var' in original_line and 'delegate' in original_line.lower():
                if 'weak' not in original_line:
                    fixed_line = re.sub(r'\bvar\s+', 'weak var ', original_line)

        elif issue.type == LeakType.STRONG_IBOUTLET:
            # Swift: @IBOutlet var -> @IBOutlet weak var
            if '@IBOutlet' in original_line and 'weak' not in original_line:
                fixed_line = original_line.replace('@IBOutlet var', '@IBOutlet weak var')
                fixed_line = fixed_line.replace('@IBOutlet private var', '@IBOutlet private weak var')

        elif issue.type == LeakType.MISSING_WEAK_SELF:
            # Add [weak self] to closure
            if '{' in original_line and 'self' in original_line:
                if '[weak self]' not in original_line and '[unowned self]' not in original_line:
                    # Insert after opening brace
                    fixed_line = re.sub(r'\{\s*', '{ [weak self] in ', original_line)
                    # Change self. to self?.
                    fixed_line = re.sub(r'\bself\.', 'self?.', fixed_line)

        elif issue.type == LeakType.SYNC_MAIN_DISPATCH:
            # Change .sync to .async
            fixed_line = original_line.replace('.sync', '.async')

        if fixed_line != original_line:
            return FixSuggestion(
                original_code=original_line,
                fixed_code=fixed_line,
                description=issue.suggestion,
                start_line=issue.line_number,
                end_line=issue.line_number,
                start_column=1,
                end_column=len(original_line),
                is_auto_fixable=True
            )

        return None

    def fix_file(self, file_path: str, issues: List[LeakPattern]) -> FileFix:
        """
        Generate fixes for all issues in a file.

        Args:
            file_path: Path to the source file
            issues: List of issues detected in this file

        Returns:
            FileFix object with all fixes applied
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return FileFix(file_path=file_path, original_content="", fixed_content="")

        file_fix = FileFix(
            file_path=file_path,
            original_content=original_content,
            fixed_content=original_content
        )

        # Sort issues by line number in reverse order to avoid offset issues
        sorted_issues = sorted(issues, key=lambda x: x.line_number, reverse=True)

        lines = original_content.split('\n')

        for issue in sorted_issues:
            fix = self.generate_fix(issue, '\n'.join(lines))
            if fix and fix.is_auto_fixable:
                # Apply fix
                start_idx = fix.start_line - 1
                end_idx = fix.end_line

                if start_idx >= 0 and start_idx < len(lines):
                    # Handle single-line fixes
                    if fix.start_line == fix.end_line or not fix.end_line:
                        lines[start_idx] = fix.fixed_code
                    else:
                        # Handle multi-line fixes
                        fixed_lines = fix.fixed_code.split('\n')
                        lines[start_idx:end_idx] = fixed_lines

                    fix.start_line = issue.line_number
                    fix.end_line = issue.end_line or issue.line_number
                    file_fix.fixes.append(fix)

        file_fix.fixed_content = '\n'.join(lines)
        return file_fix

    def apply_fixes(self, file_fixes: List[FileFix]) -> Dict[str, Any]:
        """
        Apply fixes to files.

        Args:
            file_fixes: List of FileFix objects to apply

        Returns:
            Summary of applied fixes
        """
        summary = {
            'files_modified': 0,
            'fixes_applied': 0,
            'backups_created': [],
            'errors': []
        }

        for file_fix in file_fixes:
            if not file_fix.has_changes():
                continue

            try:
                if self.backup:
                    backup_path = self._create_backup(file_fix.file_path)
                    file_fix.backup_path = backup_path
                    summary['backups_created'].append(backup_path)

                if not self.dry_run:
                    with open(file_fix.file_path, 'w', encoding='utf-8') as f:
                        f.write(file_fix.fixed_content)

                summary['files_modified'] += 1
                summary['fixes_applied'] += len(file_fix.fixes)

            except Exception as e:
                summary['errors'].append({
                    'file': file_fix.file_path,
                    'error': str(e)
                })

        return summary

    def _create_backup(self, file_path: str) -> str:
        """Create a backup of the file before modification."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = Path(file_path).parent / '.leak_detector_backups'
        backup_dir.mkdir(exist_ok=True)

        backup_name = f"{Path(file_path).name}.{timestamp}.bak"
        backup_path = backup_dir / backup_name

        shutil.copy2(file_path, backup_path)
        return str(backup_path)

    def generate_fix_report(self, file_fixes: List[FileFix]) -> str:
        """Generate a detailed fix report."""
        report = []
        report.append("=" * 70)
        report.append("  iOS Memory Leak Detector - Fix Report")
        report.append("=" * 70)
        report.append("")

        total_fixes = sum(len(ff.fixes) for ff in file_fixes)
        files_with_fixes = sum(1 for ff in file_fixes if ff.has_changes())

        report.append(f"Total files with fixes: {files_with_fixes}")
        report.append(f"Total fixes available: {total_fixes}")
        report.append("")

        for file_fix in file_fixes:
            if not file_fix.fixes:
                continue

            rel_path = self._get_relative_path(file_fix.file_path)
            report.append("-" * 70)
            report.append(f"File: {rel_path}")
            report.append(f"Fixes: {len(file_fix.fixes)}")
            report.append("")

            for i, fix in enumerate(file_fix.fixes, 1):
                report.append(f"  [{i}] Line {fix.start_line}")
                report.append(f"      {fix.description}")
                report.append("")

                # Show original code
                report.append("      Before:")
                for line in fix.original_code.split('\n')[:5]:
                    report.append(f"        - {line}")

                # Show fixed code
                report.append("      After:")
                for line in fix.fixed_code.split('\n')[:5]:
                    report.append(f"        + {line}")

                report.append("")

        return '\n'.join(report)

    def generate_diff_output(self, file_fixes: List[FileFix], colored: bool = True) -> str:
        """Generate unified diff output for all fixes."""
        output = []

        for file_fix in file_fixes:
            if not file_fix.has_changes():
                continue

            diff = file_fix.get_diff()
            if diff:
                if colored:
                    diff = self._colorize_diff(diff)
                output.append(diff)
                output.append("")

        return '\n'.join(output)

    def _colorize_diff(self, diff: str) -> str:
        """Add ANSI colors to diff output."""
        RED = '\033[91m'
        GREEN = '\033[92m'
        CYAN = '\033[96m'
        RESET = '\033[0m'

        lines = diff.split('\n')
        colored_lines = []

        for line in lines:
            if line.startswith('+++') or line.startswith('---'):
                colored_lines.append(f"{CYAN}{line}{RESET}")
            elif line.startswith('+'):
                colored_lines.append(f"{GREEN}{line}{RESET}")
            elif line.startswith('-'):
                colored_lines.append(f"{RED}{line}{RESET}")
            elif line.startswith('@@'):
                colored_lines.append(f"{CYAN}{line}{RESET}")
            else:
                colored_lines.append(line)

        return '\n'.join(colored_lines)

    def _get_relative_path(self, file_path: str) -> str:
        """Get a shorter relative path for display."""
        parts = Path(file_path).parts
        if len(parts) > 3:
            return '/'.join(parts[-3:])
        return file_path


class SwiftFixer:
    """Specialized fixer for Swift code."""

    @staticmethod
    def add_weak_self_to_closure(closure_code: str) -> str:
        """Add [weak self] to a Swift closure."""
        # Check if already has capture list
        if re.search(r'\[\s*(?:weak|unowned)', closure_code):
            return closure_code

        # Find opening brace
        brace_match = re.search(r'\{(\s*)', closure_code)
        if brace_match:
            insert_pos = brace_match.end()
            # Check if there's an 'in' keyword
            if ' in' not in closure_code[insert_pos:insert_pos+20]:
                fixed = closure_code[:insert_pos] + '[weak self] in ' + closure_code[insert_pos:]
            else:
                fixed = closure_code[:insert_pos] + '[weak self] ' + closure_code[insert_pos:]

            # Change self. to self?.
            fixed = re.sub(r'\bself\.', 'self?.', fixed)
            return fixed

        return closure_code

    @staticmethod
    def add_deinit(class_code: str, cleanup_code: str = "") -> str:
        """Add deinit to a Swift class."""
        if 'deinit {' in class_code or 'deinit{' in class_code:
            return class_code

        # Find the last closing brace of the class
        last_brace = class_code.rfind('}')
        if last_brace == -1:
            return class_code

        deinit_code = f'''
    deinit {{
        {cleanup_code if cleanup_code else 'print("\\(type(of: self)) deallocated")'}
    }}
'''
        return class_code[:last_brace] + deinit_code + class_code[last_brace:]

    @staticmethod
    def make_delegate_weak(property_declaration: str) -> str:
        """Make a delegate property weak."""
        if 'weak' in property_declaration:
            return property_declaration
        return re.sub(r'\bvar\s+', 'weak var ', property_declaration)


class ObjCFixer:
    """Specialized fixer for Objective-C code."""

    @staticmethod
    def add_weak_self_before_block(code: str, block_start_line: int) -> str:
        """Add __weak typeof(self) weakSelf = self; before a block."""
        lines = code.split('\n')
        if block_start_line <= 0 or block_start_line > len(lines):
            return code

        # Get indentation of the block line
        block_line = lines[block_start_line - 1]
        indent = len(block_line) - len(block_line.lstrip())
        indent_str = ' ' * indent

        # Insert weak self declaration
        weak_decl = f"{indent_str}__weak typeof(self) weakSelf = self;"
        lines.insert(block_start_line - 1, weak_decl)

        return '\n'.join(lines)

    @staticmethod
    def replace_self_with_weakself(block_code: str) -> str:
        """Replace self with weakSelf in block."""
        return re.sub(r'\bself\b', 'weakSelf', block_code)

    @staticmethod
    def add_dealloc(implementation_code: str, cleanup_code: str = "") -> str:
        """Add dealloc method to Objective-C implementation."""
        if '- (void)dealloc' in implementation_code:
            return implementation_code

        # Find @end
        end_match = re.search(r'@end', implementation_code)
        if not end_match:
            return implementation_code

        dealloc_code = f'''
- (void)dealloc {{
    {cleanup_code if cleanup_code else 'NSLog(@"%@ deallocated", NSStringFromClass([self class]));'}
}}

'''
        return implementation_code[:end_match.start()] + dealloc_code + implementation_code[end_match.start():]

    @staticmethod
    def make_property_weak(property_declaration: str) -> str:
        """Make an Objective-C property weak."""
        # Replace strong/retain with weak
        fixed = re.sub(r'\bstrong\b', 'weak', property_declaration)
        fixed = re.sub(r'\bretain\b', 'weak', fixed)
        return fixed


def get_fix_for_issue(issue: LeakPattern, file_content: str) -> Optional[FixSuggestion]:
    """
    Convenience function to get a fix for a single issue.

    Args:
        issue: The detected leak pattern
        file_content: Content of the source file

    Returns:
        FixSuggestion or None
    """
    fixer = CodeFixer(dry_run=True)
    return fixer.generate_fix(issue, file_content)


def apply_all_fixes(issues: List[LeakPattern], dry_run: bool = True) -> Dict[str, Any]:
    """
    Apply fixes for all issues.

    Args:
        issues: List of all detected issues
        dry_run: If True, don't modify files

    Returns:
        Summary of fixes
    """
    fixer = CodeFixer(dry_run=dry_run)

    # Group issues by file
    issues_by_file: Dict[str, List[LeakPattern]] = {}
    for issue in issues:
        if issue.file_path not in issues_by_file:
            issues_by_file[issue.file_path] = []
        issues_by_file[issue.file_path].append(issue)

    # Generate fixes for each file
    file_fixes = []
    for file_path, file_issues in issues_by_file.items():
        file_fix = fixer.fix_file(file_path, file_issues)
        if file_fix.has_changes():
            file_fixes.append(file_fix)

    # Apply fixes
    summary = fixer.apply_fixes(file_fixes)
    summary['file_fixes'] = file_fixes

    return summary
