"""Tests for the analyzer, reporter, fixer and CLI using the bundled leaky examples."""
import json
import os
import subprocess
import sys

import pytest

from ios_leak_detector import CodeFixer, LeakSeverity, LeakType, MemoryLeakAnalyzer, Reporter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")


@pytest.fixture(scope="module")
def result():
    return MemoryLeakAnalyzer().analyze_directory(EXAMPLES)


def test_examples_are_detected(result):
    assert result.swift_files == 2 and result.objc_files == 1
    assert result.total_issues == len(result.issues) > 0
    types = {i.type for i in result.issues}
    assert {LeakType.NON_WEAK_DELEGATE, LeakType.MISSING_WEAK_SELF, LeakType.RETAIN_CYCLE_BLOCK,
            LeakType.UNREMOVED_TIMER, LeakType.STRONG_IBOUTLET} <= types
    assert result.severity_counts.get("high", 0) > 0
    assert result.fixable_issues == sum(1 for i in result.issues if i.fix is not None and i.fix.is_auto_fixable) > 0


def test_single_file_analysis_and_issue_dict():
    issues = MemoryLeakAnalyzer().analyze_file(os.path.join(EXAMPLES, "LeakyViewController.swift"))
    assert issues
    d = issues[0].to_dict()
    assert d["file"].endswith("LeakyViewController.swift")
    assert d["location"]["line"] >= 1 and d["severity"] in {s.value for s in LeakSeverity}


def test_severity_threshold_filters(result):
    high_only = MemoryLeakAnalyzer({"severity_threshold": "high"}).analyze_directory(EXAMPLES)
    assert 0 < high_only.total_issues < result.total_issues
    assert all(i.severity in (LeakSeverity.HIGH, LeakSeverity.CRITICAL) for i in high_only.issues)


def test_reporter_formats(result, tmp_path):
    reporter = Reporter(result, project_name="examples")
    data = json.loads(reporter.to_json())
    assert data["analysis"]["summary"]["total_issues"] == result.total_issues
    md = reporter.to_markdown()
    assert "LeakyViewController.swift" in md
    html_path = tmp_path / "report.html"
    reporter.to_html(str(html_path))
    assert html_path.read_text(encoding="utf-8").lstrip().lower().startswith("<!doctype html")


def test_fixer_generates_weak_self_fix():
    path = os.path.join(EXAMPLES, "LeakyViewController.swift")
    issues = [i for i in MemoryLeakAnalyzer().analyze_file(path) if i.type == LeakType.MISSING_WEAK_SELF]
    assert issues
    with open(path, encoding="utf-8") as f:
        content = f.read()
    fix = CodeFixer(dry_run=True).generate_fix(issues[0], content)
    assert fix is not None and "[weak self]" in fix.fixed_code


def test_cli_json_output_and_exit_code(tmp_path):
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, "-m", "ios_leak_detector.cli", EXAMPLES, "--format", "json", "--output", str(out)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode in (1, 2), proc.stderr  # high / critical issues found in the examples
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["analysis"]["summary"]["total_issues"] > 0
