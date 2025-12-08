#!/usr/bin/env python3
"""
iOS Memory Leak Detector - Web UI
A beautiful local web interface for analyzing iOS projects
"""

import os
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file

# Add the current directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ios_leak_detector import MemoryLeakAnalyzer, Reporter, __version__
from ios_leak_detector.fixer import CodeFixer

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# Store analysis results in memory
analysis_cache = {}


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html', version=__version__)


@app.route('/analyze', methods=['POST'])
def analyze():
    """Analyze a project path."""
    data = request.get_json()
    project_path = data.get('path', '').strip()

    if not project_path:
        return jsonify({'error': 'Project path is required'}), 400

    # Expand ~ to home directory
    project_path = os.path.expanduser(project_path)

    if not os.path.exists(project_path):
        return jsonify({'error': f'Path does not exist: {project_path}'}), 400

    try:
        # Configuration
        config = {
            'exclude_dirs': data.get('exclude', ['Pods', 'Carthage', '.build', 'DerivedData', 'build', '.git']),
            'severity_threshold': data.get('severity', 'info'),
            'include_swiftui': data.get('include_swiftui', True),
            'max_workers': 4
        }

        analyzer = MemoryLeakAnalyzer(config)

        if os.path.isfile(project_path):
            issues = analyzer.analyze_file(project_path)
            from ios_leak_detector.analyzer import AnalysisResult
            result = AnalysisResult()
            result.total_files = 1
            result.swift_files = 1 if project_path.endswith('.swift') else 0
            result.objc_files = 1 if project_path.endswith(('.m', '.mm')) else 0
            result.issues = issues
            result.total_issues = len(issues)
            result.fixable_issues = sum(1 for i in issues if i.fix and i.fix.is_auto_fixable)
            for issue in issues:
                sev = issue.severity.value
                typ = issue.type.value
                result.severity_counts[sev] = result.severity_counts.get(sev, 0) + 1
                result.type_counts[typ] = result.type_counts.get(typ, 0) + 1
        else:
            result = analyzer.analyze_directory(project_path)

        # Cache the result
        cache_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        analysis_cache[cache_id] = {
            'result': result,
            'path': project_path,
            'timestamp': datetime.now().isoformat()
        }

        # Build response
        issues_data = []
        for issue in result.issues:
            issue_dict = {
                'type': issue.type.value,
                'severity': issue.severity.value,
                'file': issue.file_path,
                'line': issue.line_number,
                'column': issue.column,
                'message': issue.message,
                'suggestion': issue.suggestion,
                'code': issue.code_snippet,
                'fix': None
            }
            if issue.fix:
                issue_dict['fix'] = {
                    'before': issue.fix.original_code,
                    'after': issue.fix.fixed_code,
                    'description': issue.fix.description,
                    'auto_fixable': issue.fix.is_auto_fixable
                }
            issues_data.append(issue_dict)

        return jsonify({
            'cache_id': cache_id,
            'summary': {
                'total_files': result.total_files,
                'swift_files': result.swift_files,
                'objc_files': result.objc_files,
                'total_issues': result.total_issues,
                'fixable_issues': result.fixable_issues,
                'analysis_time': round(result.analysis_time, 2)
            },
            'severity_counts': result.severity_counts,
            'type_counts': result.type_counts,
            'issues': issues_data
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/fix', methods=['POST'])
def apply_fixes():
    """Apply fixes to files."""
    data = request.get_json()
    cache_id = data.get('cache_id')

    if not cache_id or cache_id not in analysis_cache:
        return jsonify({'error': 'Invalid analysis session'}), 400

    cached = analysis_cache[cache_id]
    result = cached['result']

    try:
        fixer = CodeFixer(dry_run=False, backup=True)
        issues_by_file = result.get_issues_by_file()

        file_fixes = []
        for file_path, issues in issues_by_file.items():
            file_fix = fixer.fix_file(file_path, issues)
            if file_fix.has_changes():
                file_fixes.append(file_fix)

        if not file_fixes:
            return jsonify({'message': 'No changes to apply', 'fixes_applied': 0})

        summary = fixer.apply_fixes(file_fixes)

        return jsonify({
            'message': f'Applied {summary["fixes_applied"]} fixes to {summary["files_modified"]} files',
            'fixes_applied': summary['fixes_applied'],
            'files_modified': summary['files_modified'],
            'backups': summary['backups_created'][:5],
            'errors': summary.get('errors', [])
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/diff', methods=['POST'])
def get_diff():
    """Get diff preview."""
    data = request.get_json()
    cache_id = data.get('cache_id')

    if not cache_id or cache_id not in analysis_cache:
        return jsonify({'error': 'Invalid analysis session'}), 400

    cached = analysis_cache[cache_id]
    result = cached['result']

    try:
        fixer = CodeFixer(dry_run=True, backup=False)
        issues_by_file = result.get_issues_by_file()

        diffs = []
        for file_path, issues in issues_by_file.items():
            file_fix = fixer.fix_file(file_path, issues)
            if file_fix.has_changes():
                parts = Path(file_path).parts
                rel_path = '/'.join(parts[-3:]) if len(parts) > 3 else file_path
                diffs.append({
                    'file': rel_path,
                    'full_path': file_path,
                    'fix_count': len(file_fix.fixes),
                    'diff': file_fix.get_diff()
                })

        return jsonify({'diffs': diffs})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/export/<format_type>', methods=['POST'])
def export_report(format_type):
    """Export report in various formats."""
    data = request.get_json()
    cache_id = data.get('cache_id')

    if not cache_id or cache_id not in analysis_cache:
        return jsonify({'error': 'Invalid analysis session'}), 400

    cached = analysis_cache[cache_id]
    result = cached['result']
    project_name = Path(cached['path']).name

    reporter = Reporter(result, project_name)

    try:
        if format_type == 'json':
            content = reporter.to_json()
            return jsonify(json.loads(content))

        elif format_type == 'html':
            html = reporter._generate_html()
            return html, 200, {'Content-Type': 'text/html'}

        elif format_type == 'markdown':
            md = reporter._generate_markdown()
            return md, 200, {'Content-Type': 'text/markdown'}

        else:
            return jsonify({'error': 'Unknown format'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/patterns')
def list_patterns():
    """List all detection patterns."""
    from ios_leak_detector.patterns import (
        SWIFT_PATTERNS, SWIFTUI_PATTERNS, OBJC_PATTERNS, PERFORMANCE_PATTERNS
    )

    def pattern_to_dict(name, data):
        return {
            'name': name,
            'severity': data['severity'].value,
            'message': data['message'],
            'suggestion': data.get('suggestion', ''),
            'has_fix': 'fix_generator' in data or 'fix_example' in data
        }

    return jsonify({
        'swift': [pattern_to_dict(n, d) for n, d in SWIFT_PATTERNS.items()],
        'swiftui': [pattern_to_dict(n, d) for n, d in SWIFTUI_PATTERNS.items()],
        'objc': [pattern_to_dict(n, d) for n, d in OBJC_PATTERNS.items()],
        'performance': [pattern_to_dict(n, d) for n, d in PERFORMANCE_PATTERNS.items()]
    })


# Create templates directory and HTML template
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
os.makedirs(TEMPLATE_DIR, exist_ok=True)

INDEX_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iOS Memory Leak Detector</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --primary: #667eea;
            --primary-dark: #5a67d8;
            --danger: #e53e3e;
            --warning: #dd6b20;
            --success: #38a169;
            --info: #3182ce;
            --gray: #718096;
            --bg: #f7fafc;
            --card-bg: #ffffff;
            --text: #2d3748;
            --border: #e2e8f0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }

        .header {
            background: linear-gradient(135deg, var(--primary), #764ba2);
            color: white;
            padding: 30px 20px;
            text-align: center;
        }

        .header h1 { font-size: 2em; margin-bottom: 10px; }
        .header p { opacity: 0.9; }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .card {
            background: var(--card-bg);
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.07);
            padding: 24px;
            margin-bottom: 20px;
        }

        .card h2 {
            font-size: 1.3em;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .input-group {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }

        .input-group input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid var(--border);
            border-radius: 8px;
            font-size: 1em;
            transition: border-color 0.2s;
        }

        .input-group input:focus {
            outline: none;
            border-color: var(--primary);
        }

        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .btn-primary {
            background: var(--primary);
            color: white;
        }

        .btn-primary:hover { background: var(--primary-dark); }

        .btn-success {
            background: var(--success);
            color: white;
        }

        .btn-warning {
            background: var(--warning);
            color: white;
        }

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .stat-card {
            background: var(--bg);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }

        .stat-card .value {
            font-size: 2.5em;
            font-weight: 700;
            color: var(--primary);
        }

        .stat-card .label {
            color: var(--gray);
            font-size: 0.9em;
        }

        .stat-card.fixable .value { color: var(--success); }
        .stat-card.critical .value { color: var(--danger); }
        .stat-card.high .value { color: var(--warning); }

        .severity-bar {
            display: flex;
            height: 8px;
            border-radius: 4px;
            overflow: hidden;
            margin: 20px 0;
        }

        .severity-bar .critical { background: var(--danger); }
        .severity-bar .high { background: var(--warning); }
        .severity-bar .medium { background: #ecc94b; }
        .severity-bar .low { background: var(--success); }
        .severity-bar .info { background: var(--gray); }

        .issues-list {
            max-height: 600px;
            overflow-y: auto;
        }

        .issue {
            border-left: 4px solid var(--gray);
            padding: 15px;
            margin: 10px 0;
            background: var(--bg);
            border-radius: 0 8px 8px 0;
        }

        .issue.critical { border-color: var(--danger); }
        .issue.high { border-color: var(--warning); }
        .issue.medium { border-color: #ecc94b; }
        .issue.low { border-color: var(--success); }

        .issue-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }

        .issue-badge {
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.75em;
            font-weight: 600;
            text-transform: uppercase;
        }

        .issue-badge.critical { background: var(--danger); color: white; }
        .issue-badge.high { background: var(--warning); color: white; }
        .issue-badge.medium { background: #ecc94b; color: #744210; }
        .issue-badge.low { background: var(--success); color: white; }
        .issue-badge.info { background: var(--gray); color: white; }

        .issue-location {
            font-family: monospace;
            font-size: 0.85em;
            color: var(--gray);
        }

        .issue-message {
            font-weight: 500;
            margin: 8px 0;
        }

        .issue-suggestion {
            color: var(--success);
            font-size: 0.9em;
        }

        .issue-code {
            background: #1a202c;
            color: #e2e8f0;
            padding: 12px;
            border-radius: 6px;
            font-family: 'Fira Code', monospace;
            font-size: 0.85em;
            overflow-x: auto;
            margin: 10px 0;
            white-space: pre;
        }

        .fix-box {
            background: #c6f6d5;
            border: 1px solid var(--success);
            border-radius: 6px;
            padding: 12px;
            margin-top: 10px;
        }

        .fix-box h4 {
            color: var(--success);
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .fix-code {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }

        .fix-before, .fix-after {
            padding: 10px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.85em;
            overflow-x: auto;
            white-space: pre;
        }

        .fix-before {
            background: #fed7d7;
            color: #c53030;
        }

        .fix-after {
            background: #c6f6d5;
            color: #276749;
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: var(--gray);
        }

        .loading::after {
            content: '';
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid var(--primary);
            border-radius: 50%;
            border-top-color: transparent;
            animation: spin 1s linear infinite;
            margin-left: 10px;
            vertical-align: middle;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .hidden { display: none !important; }

        .actions {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }

        .filters {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }

        .filter-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .filter-group label {
            font-size: 0.9em;
            color: var(--gray);
        }

        .filter-group select {
            padding: 8px 12px;
            border: 2px solid var(--border);
            border-radius: 6px;
            font-size: 0.9em;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--gray);
        }

        .empty-state .icon {
            font-size: 4em;
            margin-bottom: 20px;
        }

        @media (max-width: 768px) {
            .fix-code { grid-template-columns: 1fr; }
            .input-group { flex-direction: column; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 iOS Memory Leak Detector</h1>
        <p>Detect memory leaks in Swift, SwiftUI & Objective-C projects</p>
        <p style="font-size: 0.85em; margin-top: 5px;">v{{ version }}</p>
    </div>

    <div class="container">
        <!-- Analyze Form -->
        <div class="card">
            <h2>📂 Analyze Project</h2>
            <div class="input-group">
                <input type="text" id="projectPath" placeholder="Enter project path (e.g., ~/Projects/MyApp or /Users/name/MyApp)" />
                <button class="btn btn-primary" id="analyzeBtn" onclick="analyzeProject()">
                    🔍 Analyze
                </button>
            </div>
            <div class="filters">
                <div class="filter-group">
                    <label>Severity:</label>
                    <select id="severityFilter">
                        <option value="info">All (Info+)</option>
                        <option value="low">Low+</option>
                        <option value="medium">Medium+</option>
                        <option value="high">High+</option>
                        <option value="critical">Critical only</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>
                        <input type="checkbox" id="swiftuiCheck" checked /> Include SwiftUI patterns
                    </label>
                </div>
            </div>
        </div>

        <!-- Loading -->
        <div id="loading" class="card hidden">
            <div class="loading">Analyzing project...</div>
        </div>

        <!-- Results -->
        <div id="results" class="hidden">
            <!-- Summary -->
            <div class="card">
                <h2>📊 Analysis Summary</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="value" id="totalFiles">0</div>
                        <div class="label">Files Analyzed</div>
                    </div>
                    <div class="stat-card">
                        <div class="value" id="totalIssues">0</div>
                        <div class="label">Issues Found</div>
                    </div>
                    <div class="stat-card fixable">
                        <div class="value" id="fixableIssues">0</div>
                        <div class="label">Auto-fixable</div>
                    </div>
                    <div class="stat-card critical">
                        <div class="value" id="criticalCount">0</div>
                        <div class="label">Critical</div>
                    </div>
                    <div class="stat-card high">
                        <div class="value" id="highCount">0</div>
                        <div class="label">High</div>
                    </div>
                    <div class="stat-card">
                        <div class="value" id="analysisTime">0s</div>
                        <div class="label">Analysis Time</div>
                    </div>
                </div>

                <div class="severity-bar" id="severityBar"></div>

                <div class="actions">
                    <button class="btn btn-success" onclick="applyFixes()">🔧 Apply Fixes</button>
                    <button class="btn btn-warning" onclick="showDiff()">📋 Preview Diff</button>
                    <button class="btn btn-primary" onclick="exportHtml()">📄 Export HTML</button>
                </div>
            </div>

            <!-- Issues List -->
            <div class="card">
                <h2>🔍 Issues (<span id="issueCount">0</span>)</h2>
                <div class="filters">
                    <div class="filter-group">
                        <label>Filter by severity:</label>
                        <select id="displayFilter" onchange="filterIssues()">
                            <option value="all">All</option>
                            <option value="critical">Critical</option>
                            <option value="high">High</option>
                            <option value="medium">Medium</option>
                            <option value="low">Low</option>
                            <option value="info">Info</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label>
                            <input type="checkbox" id="fixableOnly" onchange="filterIssues()" /> Show fixable only
                        </label>
                    </div>
                </div>
                <div class="issues-list" id="issuesList"></div>
            </div>
        </div>

        <!-- Empty State -->
        <div id="emptyState" class="card">
            <div class="empty-state">
                <div class="icon">📱</div>
                <h3>Enter a project path to analyze</h3>
                <p>Supports Swift, SwiftUI, and Objective-C projects</p>
            </div>
        </div>
    </div>

    <script>
        let currentCacheId = null;
        let allIssues = [];

        async function analyzeProject() {
            const path = document.getElementById('projectPath').value.trim();
            if (!path) {
                alert('Please enter a project path');
                return;
            }

            const severity = document.getElementById('severityFilter').value;
            const includeSwiftui = document.getElementById('swiftuiCheck').checked;

            document.getElementById('emptyState').classList.add('hidden');
            document.getElementById('results').classList.add('hidden');
            document.getElementById('loading').classList.remove('hidden');
            document.getElementById('analyzeBtn').disabled = true;

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: path,
                        severity: severity,
                        include_swiftui: includeSwiftui
                    })
                });

                const data = await response.json();

                if (data.error) {
                    alert('Error: ' + data.error);
                    document.getElementById('emptyState').classList.remove('hidden');
                } else {
                    currentCacheId = data.cache_id;
                    allIssues = data.issues;
                    displayResults(data);
                }
            } catch (e) {
                alert('Error analyzing project: ' + e.message);
                document.getElementById('emptyState').classList.remove('hidden');
            } finally {
                document.getElementById('loading').classList.add('hidden');
                document.getElementById('analyzeBtn').disabled = false;
            }
        }

        function displayResults(data) {
            // Summary stats
            document.getElementById('totalFiles').textContent = data.summary.total_files;
            document.getElementById('totalIssues').textContent = data.summary.total_issues;
            document.getElementById('fixableIssues').textContent = data.summary.fixable_issues;
            document.getElementById('criticalCount').textContent = data.severity_counts.critical || 0;
            document.getElementById('highCount').textContent = data.severity_counts.high || 0;
            document.getElementById('analysisTime').textContent = data.summary.analysis_time + 's';

            // Severity bar
            const total = data.summary.total_issues || 1;
            const bar = document.getElementById('severityBar');
            bar.innerHTML = '';

            ['critical', 'high', 'medium', 'low', 'info'].forEach(sev => {
                const count = data.severity_counts[sev] || 0;
                if (count > 0) {
                    const pct = (count / total * 100);
                    const div = document.createElement('div');
                    div.className = sev;
                    div.style.width = pct + '%';
                    div.title = sev + ': ' + count;
                    bar.appendChild(div);
                }
            });

            // Issues
            displayIssues(data.issues);

            document.getElementById('results').classList.remove('hidden');
        }

        function displayIssues(issues) {
            const list = document.getElementById('issuesList');
            list.innerHTML = '';
            document.getElementById('issueCount').textContent = issues.length;

            if (issues.length === 0) {
                list.innerHTML = '<div class="empty-state"><div class="icon">✅</div><h3>No issues found!</h3></div>';
                return;
            }

            issues.forEach((issue, idx) => {
                const div = document.createElement('div');
                div.className = 'issue ' + issue.severity;
                div.dataset.severity = issue.severity;
                div.dataset.fixable = issue.fix && issue.fix.auto_fixable ? 'true' : 'false';

                const shortFile = issue.file.split('/').slice(-2).join('/');

                let fixHtml = '';
                if (issue.fix) {
                    fixHtml = `
                        <div class="fix-box">
                            <h4>🔧 ${issue.fix.auto_fixable ? '✓ Auto-fixable' : 'Manual fix'}</h4>
                            <div class="fix-code">
                                <div class="fix-before">${escapeHtml(issue.fix.before)}</div>
                                <div class="fix-after">${escapeHtml(issue.fix.after)}</div>
                            </div>
                        </div>
                    `;
                }

                div.innerHTML = `
                    <div class="issue-header">
                        <span class="issue-badge ${issue.severity}">${issue.severity}</span>
                        <span class="issue-location">${shortFile}:${issue.line}${issue.column > 1 ? ':' + issue.column : ''}</span>
                    </div>
                    <div class="issue-message">${escapeHtml(issue.message)}</div>
                    <div class="issue-suggestion">💡 ${escapeHtml(issue.suggestion)}</div>
                    ${issue.code ? `<div class="issue-code">${escapeHtml(issue.code)}</div>` : ''}
                    ${fixHtml}
                `;

                list.appendChild(div);
            });
        }

        function filterIssues() {
            const filter = document.getElementById('displayFilter').value;
            const fixableOnly = document.getElementById('fixableOnly').checked;

            let filtered = allIssues;

            if (filter !== 'all') {
                filtered = filtered.filter(i => i.severity === filter);
            }

            if (fixableOnly) {
                filtered = filtered.filter(i => i.fix && i.fix.auto_fixable);
            }

            displayIssues(filtered);
        }

        async function applyFixes() {
            if (!currentCacheId) return;

            if (!confirm('Apply auto-fixes? Backups will be created.')) return;

            try {
                const response = await fetch('/fix', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cache_id: currentCacheId })
                });

                const data = await response.json();

                if (data.error) {
                    alert('Error: ' + data.error);
                } else {
                    alert(data.message);
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function showDiff() {
            if (!currentCacheId) return;

            try {
                const response = await fetch('/diff', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cache_id: currentCacheId })
                });

                const data = await response.json();

                if (data.error) {
                    alert('Error: ' + data.error);
                } else if (data.diffs.length === 0) {
                    alert('No auto-fixable changes available');
                } else {
                    let diffText = data.diffs.map(d =>
                        `=== ${d.file} (${d.fix_count} fixes) ===\\n${d.diff}`
                    ).join('\\n\\n');

                    const win = window.open('', '_blank');
                    win.document.write('<pre style="font-family: monospace; padding: 20px;">' + escapeHtml(diffText) + '</pre>');
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function exportHtml() {
            if (!currentCacheId) return;

            try {
                const response = await fetch('/export/html', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cache_id: currentCacheId })
                });

                const html = await response.text();
                const win = window.open('', '_blank');
                win.document.write(html);
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        function escapeHtml(text) {
            if (!text) return '';
            return text.replace(/&/g, '&amp;')
                       .replace(/</g, '&lt;')
                       .replace(/>/g, '&gt;')
                       .replace(/"/g, '&quot;');
        }

        // Enter key to analyze
        document.getElementById('projectPath').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') analyzeProject();
        });
    </script>
</body>
</html>'''

# Write template on startup
with open(os.path.join(TEMPLATE_DIR, 'index.html'), 'w') as f:
    f.write(INDEX_HTML)


if __name__ == '__main__':
    import argparse
    import webbrowser
    import threading

    parser = argparse.ArgumentParser(description='iOS Memory Leak Detector Web UI')
    parser.add_argument('--port', '-p', type=int, default=5050, help='Port to run on (default: 5050)')
    parser.add_argument('--no-browser', action='store_true', help='Do not auto-open browser')
    args = parser.parse_args()

    port = args.port
    url = f'http://localhost:{port}'

    print(f'''
╔═══════════════════════════════════════════════════════╗
║     iOS Memory Leak Detector - Web UI                 ║
║                                                       ║
║     Open in browser: {url:<30} ║
║     Press Ctrl+C to stop                              ║
╚═══════════════════════════════════════════════════════╝
''')

    # Open browser after short delay
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host='0.0.0.0', port=port, debug=False)
