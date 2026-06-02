# core/report.py
"""
Generates the final HTML QA report and JSON summaries from drawing comparison results.
Uses Jinja2 to render a rich, modern HTML dashboard with 13-category compliance audits.
"""

from jinja2 import Template
from pathlib import Path
import json
from datetime import datetime
from core.qa_agent import CATEGORIES_LIST

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Engineering drawing QA compliance audit report: Reference vs Creo review">
  <title>Engineering Drawing QA Compliance Report</title>
  <!-- Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  
  <style>
    :root {
      --bg-color: #0b0f19;
      --panel-bg: #141b2d;
      --panel-border: #243049;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      
      /* Brand / Severity Colors */
      --primary: #6366f1;
      --primary-glow: rgba(99, 102, 241, 0.15);
      
      --color-high: #ef4444;
      --color-high-bg: rgba(239, 68, 68, 0.1);
      
      --color-medium: #f59e0b;
      --color-medium-bg: rgba(245, 158, 11, 0.1);
      
      --color-low: #3b82f6;
      --color-low-bg: rgba(59, 130, 246, 0.1);
      
      --color-clean: #10b981;
      --color-clean-bg: rgba(16, 185, 129, 0.1);
      
      /* Issue Specific Category Colors (CSS representation of python config colors) */
      --category-missing: #ef4444;      /* Red */
      --category-misplacement: #3b82f6; /* Blue */
      --category-overlap: #f97316;      /* Orange */
      --category-geom: #d946ef;         /* Magenta */
    }

    html[data-theme="light"] {
      --bg-color: #f8fafc;
      --panel-bg: #ffffff;
      --panel-border: #e2e8f0;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --primary: #4f46e5;
      --primary-glow: rgba(79, 70, 229, 0.1);
      
      --color-high: #dc2626;
      --color-high-bg: rgba(220, 38, 38, 0.08);
      
      --color-medium: #d97706;
      --color-medium-bg: rgba(217, 119, 6, 0.08);
      
      --color-low: #2563eb;
      --color-low-bg: rgba(37, 99, 235, 0.08);
      
      --color-clean: #16a34a;
      --color-clean-bg: rgba(22, 163, 74, 0.08);
    }

    html[data-theme="light"] header {
      background: linear-gradient(135deg, #e0e7ff 0%, #f8fafc 100%);
      border-color: #cbd5e1;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
    }

    html[data-theme="light"] header h1 {
      background: linear-gradient(to right, #4f46e5, #7c3aed);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    html[data-theme="light"] header p {
      color: #475569;
    }

    html[data-theme="light"] header .meta-grid {
      color: #64748b;
    }

    html[data-theme="light"] header .meta-item strong {
      color: #0f172a;
    }

    html[data-theme="light"] .header-actions {
      border-top-color: #cbd5e1;
    }

    html[data-theme="light"] .download-note {
      color: #64748b;
    }

    html[data-theme="light"] .section-title {
      color: #1e293b;
    }

    html[data-theme="light"] .summary-text {
      background-color: #f1f5f9;
      border-color: #cbd5e1;
      color: #334155;
    }

    html[data-theme="light"] .category-card {
      background-color: #ffffff;
    }

    html[data-theme="light"] .category-card:hover {
      background-color: #f1f5f9;
    }

    html[data-theme="light"] .category-card-details {
      border-top-color: #e2e8f0;
    }

    html[data-theme="light"] .category-card-details li {
      color: #334155;
    }

    html[data-theme="light"] .audit-summary-table td {
      border-bottom: 1px solid #f1f5f9;
    }

    html[data-theme="light"] .breakdown-title {
      color: #4f46e5 !important;
    }

    html[data-theme="light"] .click-hint {
      color: #94a3b8;
    }

    html[data-theme="light"] .theme-toggle {
      background: #f1f5f9;
      border-color: #cbd5e1;
      color: #0f172a;
    }

    html[data-theme="light"] .theme-toggle:hover {
      background: #e2e8f0;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background-color: var(--bg-color);
      color: var(--text-main);
      padding: 40px 24px;
      line-height: 1.5;
      transition: background-color 0.2s ease, color 0.2s ease;
    }

    .container {
      max-width: 1400px;
      margin: 0 auto;
    }

    /* Header styling with smooth gradients */
    header {
      background: linear-gradient(135deg, #1e1b4b 0%, #141b2d 100%);
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      padding: 32px 40px;
      margin-bottom: 32px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
      position: relative;
      overflow: hidden;
    }

    header::before {
      content: '';
      position: absolute;
      top: -50%;
      right: -10%;
      width: 400px;
      height: 400px;
      background: radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%);
      pointer-events: none;
    }

    header h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 2.25rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(to right, #a5b4fc, #e0e7ff);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 12px;
    }

    header p {
      color: var(--text-muted);
      font-size: 1rem;
      font-weight: 400;
    }

    .header-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
    }

    header .meta-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 24px;
      font-size: 0.875rem;
      color: var(--text-muted);
    }

    header .meta-item {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    header .meta-item strong {
      color: var(--text-main);
    }

    /* Stats Grid Dashboard */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 20px;
      margin-bottom: 40px;
    }

    .stat-card {
      background-color: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 14px;
      padding: 24px;
      text-align: center;
      transition: transform 0.3s ease, box-shadow 0.3s ease;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    }

    html[data-theme="light"] .stat-card,
    html[data-theme="light"] .audit-summary-panel,
    html[data-theme="light"] .page-section,
    html[data-theme="light"] .category-card,
    html[data-theme="light"] header {
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
    }

    .stat-card:hover {
      transform: translateY(-4px);
      box-shadow: 0 8px 25px rgba(99, 102, 241, 0.1);
    }

    .stat-card .num {
      font-family: 'Outfit', sans-serif;
      font-size: 2.75rem;
      font-weight: 700;
      line-height: 1.2;
      margin-bottom: 4px;
    }

    .stat-card .label {
      font-size: 0.8rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--text-muted);
    }

    .stat-card.high .num { color: var(--color-high); }
    .stat-card.medium .num { color: var(--color-medium); }
    .stat-card.low .num { color: var(--color-low); }
    .stat-card.clean .num { color: var(--color-clean); }
    .stat-card.bad .num { color: var(--color-high); }

    /* Section Header */
    .section-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.5rem;
      font-weight: 700;
      margin-bottom: 24px;
      color: #e0e7ff;
      border-left: 4px solid var(--primary);
      padding-left: 12px;
    }

    /* Global Audit Summary Table styling */
    .audit-summary-panel {
      background-color: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 14px;
      padding: 24px;
      margin-bottom: 40px;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    }

    .audit-summary-table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.95rem;
    }

    .audit-summary-table th {
      padding: 12px;
      border-bottom: 2px solid var(--panel-border);
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.75rem;
      letter-spacing: 0.5px;
    }

    .audit-summary-table td {
      padding: 14px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }

    .audit-summary-table tr:last-child td {
      border-bottom: none;
    }

    .cat-name-cell {
      font-weight: 600;
      color: var(--text-main);
    }

    .failed-row {
      background-color: rgba(239, 68, 68, 0.01);
    }

    .passed-row {
      background-color: rgba(16, 185, 129, 0.01);
    }

    .failures-cell {
      color: var(--text-muted);
      font-weight: 500;
    }

    /* Page Analysis Cards */
    .page-section {
      background-color: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      margin-bottom: 32px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    }

    .page-header {
      padding: 20px 28px;
      font-size: 1.15rem;
      font-weight: 600;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--panel-border);
    }

    .page-header.bad {
      background: linear-gradient(to right, rgba(239, 68, 68, 0.05), transparent);
    }

    .page-header.ok {
      background: linear-gradient(to right, rgba(16, 185, 129, 0.05), transparent);
    }

    .status-pill {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 6px 14px;
      border-radius: 50px;
      letter-spacing: 0.5px;
    }

    .status-pill.bad {
      background-color: var(--color-high-bg);
      color: var(--color-high);
      border: 1px solid rgba(239, 68, 68, 0.2);
    }

    .status-pill.ok {
      background-color: var(--color-clean-bg);
      color: var(--color-clean);
      border: 1px solid rgba(16, 185, 129, 0.2);
    }

    /* Target Image Container */
    .comparison-container {
      position: relative;
      background-color: rgba(26, 34, 53, 0.98);
      padding: 10px;
      border-bottom: 1px solid var(--panel-border);
      overflow: hidden;
    }

    html[data-theme="light"] .comparison-container {
      background-color: #eef2ff;
    }

    .comparison-img {
      width: 100%;
      height: auto;
      display: block;
      border-radius: 8px;
      box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }

    /* Body padding inside page card */
    .page-body {
      padding: 28px;
    }

    .summary-text {
      background-color: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.05);
      padding: 16px 20px;
      border-radius: 10px;
      margin-bottom: 24px;
      font-size: 0.95rem;
      color: #d1d5db;
      font-style: italic;
    }

    /* 13-Categories Card Grid */
    .categories-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }

    .category-card {
      background-color: rgba(255, 255, 255, 0.015);
      border: 1px solid var(--panel-border);
      border-radius: 10px;
      padding: 16px;
      cursor: pointer;
      transition: background-color 0.2s, border-color 0.2s, transform 0.2s;
    }

    .category-card:hover {
      background-color: rgba(255, 255, 255, 0.035);
      transform: translateY(-2px);
    }

    .category-card.passed {
      border-left: 5px solid var(--color-clean);
    }

    .category-card.failed {
      border-left: 5px solid var(--color-high);
      background-color: rgba(239, 68, 68, 0.01);
    }

    .category-card.failed .category-card-details {
      display: block;
    }

    .category-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .category-card-name {
      font-weight: 700;
      font-size: 0.95rem;
      color: var(--text-main);
    }

    .category-card-status {
      font-size: 0.72rem;
      font-weight: 800;
      padding: 3px 8px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .category-card-status.passed {
      background-color: var(--color-clean-bg);
      color: var(--color-clean);
    }

    .category-card-status.failed {
      background-color: var(--color-high-bg);
      color: var(--color-high);
    }

    .category-card-details {
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 0.8rem;
      color: var(--text-muted);
      display: none;
    }

    .category-card-details ul {
      list-style-type: square;
      margin-left: 16px;
    }

    .category-card-details li {
      margin-bottom: 6px;
      color: #e5e7eb;
      line-height: 1.4;
    }

    .click-hint {
      display: block;
      font-size: 0.68rem;
      color: var(--text-muted);
      margin-top: 8px;
      text-align: right;
      font-style: italic;
    }

    .score-badge {
      font-size: 0.78rem;
      font-weight: 700;
      padding: 6px 14px;
      border-radius: 50px;
      letter-spacing: 0.5px;
      display: inline-flex;
      align-items: center;
    }
    .score-badge.good {
      background-color: rgba(16, 185, 129, 0.1);
      color: #10b981;
      border: 1px solid rgba(16, 185, 129, 0.2);
    }
    .score-badge.avg {
      background-color: rgba(245, 158, 11, 0.1);
      color: #f59e0b;
      border: 1px solid rgba(245, 158, 11, 0.2);
    }
    .score-badge.poor {
      background-color: rgba(239, 68, 68, 0.1);
      color: #ef4444;
      border: 1px solid rgba(239, 68, 68, 0.2);
    }

    html[data-theme="light"] .score-badge.good {
      background-color: rgba(22, 163, 74, 0.08);
      color: #16a34a;
      border-color: rgba(22, 163, 74, 0.15);
    }
    html[data-theme="light"] .score-badge.avg {
      background-color: rgba(217, 119, 6, 0.08);
      color: #d97706;
      border-color: rgba(217, 119, 6, 0.15);
    }
    html[data-theme="light"] .score-badge.poor {
      background-color: rgba(220, 38, 38, 0.08);
      color: #dc2626;
      border-color: rgba(220, 38, 38, 0.15);
    }

    .score-bar-bg {
      width: 100px;
      height: 8px;
      background-color: var(--panel-border);
      border-radius: 4px;
      overflow: hidden;
    }

    .no-issues-msg {
      padding: 12px 0;
      color: var(--color-clean);
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .download-btn {
      appearance: none;
      border: 1px solid rgba(99, 102, 241, 0.45);
      background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
      color: #fff;
      border-radius: 999px;
      padding: 12px 18px;
      font-weight: 700;
      font-size: 0.92rem;
      cursor: pointer;
      box-shadow: 0 10px 24px rgba(79, 70, 229, 0.28);
      transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
    }

    .download-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 14px 28px rgba(79, 70, 229, 0.34);
    }

    .download-btn:active {
      transform: translateY(0);
      opacity: 0.92;
    }

    .download-btn:disabled {
      cursor: wait;
      opacity: 0.7;
    }

    .download-note {
      color: var(--text-muted);
      font-size: 0.82rem;
    }

    .theme-toggle {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--panel-border);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text-main);
      border-radius: 999px;
      padding: 11px 16px;
      font-weight: 700;
      font-size: 0.88rem;
      cursor: pointer;
      transition: transform 0.2s ease, background-color 0.2s ease, border-color 0.2s ease;
    }

    .theme-toggle:hover {
      transform: translateY(-1px);
      background: rgba(99, 102, 241, 0.1);
    }

    html[data-theme="light"] .theme-toggle {
      background: #eef2ff;
    }

    .pdf-status {
      color: #c7d2fe;
      font-size: 0.82rem;
      min-height: 1em;
    }

    html[data-theme="light"] .pdf-status {
      color: #4f46e5;
    }

    .pdf-exporting .header-actions,
    .pdf-exporting .download-btn,
    .pdf-exporting .download-note,
    .pdf-exporting .pdf-status {
      display: none !important;
    }

    @media print {
      .header-actions,
      .download-btn,
      .download-note,
      .pdf-status {
        display: none !important;
      }
    }
  </style>
</head>
<body>
  <div class="container">
    
    <header>
      <h1>🔍 Engineering Drawing QA Compliance Report</h1>
      <p>Automated visual & text compliance audit between design source drawings and Creo review drawings.</p>
      
      <div class="meta-grid">
        <div class="meta-item">📅 Generated: <strong>{{ generated_at }}</strong></div>
        <div class="meta-item">📄 Total Pages Analyzed: <strong>{{ total_pages }}</strong></div>
        <div class="meta-item">⚠️ Total Issues Flagged: <strong>{{ total_issues }}</strong></div>
      </div>
      
      <div class="header-actions">
        <div class="download-note">Download a PDF copy of this report from the current page.</div>
        <div>
          <button id="themeToggleBtn" class="theme-toggle" type="button">Toggle Light/Dark</button>
          <button id="downloadPdfBtn" class="download-btn" type="button">Download PDF</button>
          <div id="pdfStatus" class="pdf-status" aria-live="polite"></div>
        </div>
      </div>
    </header>

    <!-- Stats Dashboard -->
    <div class="stats-grid">
      <div class="stat-card high">
        <div class="num">{{ high_count }}</div>
        <div class="label">High Severity</div>
      </div>
      <div class="stat-card medium">
        <div class="num">{{ medium_count }}</div>
        <div class="label">Medium Severity</div>
      </div>
      <div class="stat-card low">
        <div class="num">{{ low_count }}</div>
        <div class="label">Low Severity</div>
      </div>
      <div class="stat-card clean">
        <div class="num">{{ ok_pages }}</div>
        <div class="label">Clean Pages</div>
      </div>
      <div class="stat-card bad">
        <div class="num">{{ bad_pages }}</div>
        <div class="label">Pages with Issues</div>
      </div>
    </div>

    <!-- Global Audit Summary Grid -->
    <div class="section-title">Compliance Audit Matrix (13 Categories Summary)</div>
    <div class="audit-summary-panel">
      <table class="audit-summary-table">
        <thead>
          <tr>
            <th>Audit Category</th>
            <th>Compliance Status</th>
            <th>Failures (Pages Affected)</th>
          </tr>
        </thead>
        <tbody>
          {% for cat_name, cat_data in global_categories.items() %}
          <tr class="{{ 'failed-row' if cat_data.status == 'FAIL' else 'passed-row' }}">
            <td class="cat-name-cell">{{ cat_name }}</td>
            <td>
              <span class="status-pill {{ 'bad' if cat_data.status == 'FAIL' else 'ok' }}">
                {{ cat_data.status }}
              </span>
            </td>
            <td class="failures-cell">{{ cat_data.failed_count }} page(s) failed</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <!-- Drawing Quality Scoreboard Section -->
    <div class="section-title">Drawing Quality Scoreboard</div>
    <div class="audit-summary-panel">
      <table class="audit-summary-table">
        <thead>
          <tr>
            <th>Drawing File</th>
            <th>Compliance Status</th>
            <th>Quality Score</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {% for page in pages | sort(attribute='score', reverse=true) %}
          <tr class="{{ 'passed-row' if page.score >= 80 else 'failed-row' }}">
            <td class="cat-name-cell">{{ page.page }}</td>
            <td>
              <span class="status-pill {{ 'ok' if page.status == 'PASS' else 'bad' }}">
                {{ page.status }}
              </span>
            </td>
            <td>
              <div style="display: flex; align-items: center; gap: 10px;">
                <div class="score-bar-bg">
                  <div style="width: {{ page.score }}%; height: 100%; background-color: {{ '#10b981' if page.score >= 80 else '#f59e0b' if page.score >= 50 else '#ef4444' }};"></div>
                </div>
                <strong style="color: {{ '#10b981' if page.score >= 80 else '#f59e0b' if page.score >= 50 else '#ef4444' }}; font-size: 1.1rem; min-width: 60px; text-align: right;">{{ page.score }}/100</strong>
              </div>
            </td>
            <td>
              <a href="#page-{{ page.index }}" style="color: var(--primary); text-decoration: none; font-weight: 700; font-size: 0.85rem;">View Details →</a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="section-title">Page Breakdown Analysis</div>

    <!-- Pages List -->
    {% for page in pages %}
    <div class="page-section" id="page-{{ page.index }}">
      <div class="page-header {{ 'bad' if page.page_has_issues else 'ok' }}">
        <span>Page {{ page.page }}</span>
        <div style="display: flex; align-items: center; gap: 12px;">
          <span class="score-badge {{ 'good' if page.score >= 80 else 'avg' if page.score >= 50 else 'poor' }}">
            Score: {{ page.score }}/100
          </span>
          <span class="status-pill {{ 'bad' if page.page_has_issues else 'ok' }}">
            {{ page.status }} - {{ page.issues|length }} issue(s) detected
          </span>
        </div>
      </div>

      {% if page.comparison_image %}
      <div class="comparison-container">
        <img class="comparison-img" src="{{ page.comparison_image }}" alt="Page {{ page.page }} Creo Drawing with highlighting">
      </div>
      {% endif %}

      <div class="page-body">
        {% if page.summary %}
        <div class="summary-text">{{ page.summary }}</div>
        {% endif %}

        <div class="breakdown-title" style="margin-bottom: 12px; font-weight:700; font-size:1rem; color: #a5b4fc;">Audit Categories Breakdown:</div>
        
        <!-- Collapsible Category Grid -->
        <div class="categories-grid">
          {% for cat in page.categories_report %}
          <div class="category-card {{ 'failed' if cat.status == 'FAIL' else 'passed' }} {{ 'expanded' if cat.status == 'FAIL' else '' }}" onclick="toggleDetails(this)">
            <div class="category-card-header">
              <span class="category-card-name">{{ cat.name }}</span>
              <span class="category-card-status {{ 'failed' if cat.status == 'FAIL' else 'passed' }}">{{ cat.status }}</span>
            </div>
            {% if cat.issues %}
            <div class="category-card-details" style="display: {{ 'block' if cat.status == 'FAIL' else 'none' }};">
              <ul>
                {% for issue_desc in cat.issues %}
                <li>{{ issue_desc }}</li>
                {% endfor %}
              </ul>
            </div>
            <span class="click-hint">{{ 'Click to hide details' if cat.status == 'FAIL' else 'Click to show details' }}</span>
            {% endif %}
          </div>
          {% endfor %}
        </div>

        {% if not page.page_has_issues %}
        <div class="no-issues-msg">
          ✨ Perfect Match! All 13 compliance categories passed.
        </div>
        {% endif %}
      </div>
    </div>
    {% endfor %}

  </div>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
  <script>
    const storageKey = 'pdf-report-theme';

    function toggleDetails(card) {
      const details = card.querySelector('.category-card-details');
      const hint = card.querySelector('.click-hint');
      if (!details) return;

      const isVisible = details.style.display === 'block';
      details.style.display = isVisible ? 'none' : 'block';
      card.classList.toggle('expanded', !isVisible);
      if (hint) {
        hint.innerText = isVisible ? 'Click to show details' : 'Click to hide details';
      }
    }

    function syncFailedCards(root) {
      root.querySelectorAll('.category-card.failed').forEach((card) => {
        const details = card.querySelector('.category-card-details');
        const hint = card.querySelector('.click-hint');
        if (details) {
          details.style.display = 'block';
        }
        card.classList.add('expanded');
        if (hint) {
          hint.innerText = 'Click to hide details';
        }
      });
    }

    function applyTheme(theme) {
      document.documentElement.dataset.theme = theme;
      const themeBtn = document.getElementById('themeToggleBtn');
      if (themeBtn) {
        themeBtn.textContent = theme === 'light' ? 'Switch to Dark' : 'Switch to Light';
      }
      localStorage.setItem(storageKey, theme);
    }

    function getPreferredTheme() {
      const stored = localStorage.getItem(storageKey);
      return stored || 'light';
    }

    document.addEventListener('DOMContentLoaded', () => {
      const root = document.querySelector('.container');
      const themeBtn = document.getElementById('themeToggleBtn');
      const downloadBtn = document.getElementById('downloadPdfBtn');
      const pdfStatus = document.getElementById('pdfStatus');

      applyTheme(getPreferredTheme());
      if (root) {
        syncFailedCards(root);
      }

      if (themeBtn) {
        themeBtn.addEventListener('click', () => {
          const nextTheme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
          applyTheme(nextTheme);
        });
      }

      if (downloadBtn) {
        downloadBtn.addEventListener('click', async () => {
          const reportRoot = document.querySelector('.container');
          if (!reportRoot) {
            if (pdfStatus) {
              pdfStatus.textContent = 'PDF export is unavailable in this browser.';
            }
            return;
          }

          if (typeof html2pdf === 'undefined') {
            if (pdfStatus) {
              pdfStatus.textContent = 'PDF library did not load. Opening print dialog instead.';
            }
            window.print();
            return;
          }

          reportRoot.classList.add('pdf-exporting');
          syncFailedCards(reportRoot);
          downloadBtn.disabled = true;
          if (pdfStatus) {
            pdfStatus.textContent = 'Rendering report for download...';
          }

          try {
            await html2pdf().set({
              margin: 10,
              filename: 'engineering-drawing-qa-report.pdf',
              image: { type: 'jpeg', quality: 0.98 },
              html2canvas: {
                scale: 2,
                useCORS: true,
                allowTaint: true,
                scrollY: 0,
                onclone: (clonedDoc) => {
                  clonedDoc.documentElement.dataset.theme = document.documentElement.dataset.theme || 'light';
                  clonedDoc.documentElement.classList.add('pdf-exporting');
                  const clonedRoot = clonedDoc.querySelector('.container');
                  if (clonedRoot) {
                    syncFailedCards(clonedRoot);
                  }
                  const clonedBtn = clonedDoc.getElementById('downloadPdfBtn');
                  const clonedStatus = clonedDoc.getElementById('pdfStatus');
                  const clonedNote = clonedDoc.querySelector('.download-note');
                  const clonedTheme = clonedDoc.getElementById('themeToggleBtn');
                  if (clonedBtn) clonedBtn.remove();
                  if (clonedStatus) clonedStatus.remove();
                  if (clonedNote) clonedNote.remove();
                  if (clonedTheme) clonedTheme.remove();
                }
              },
              jsPDF: {
                unit: 'mm',
                format: 'a4',
                orientation: 'portrait'
              }
            }).from(reportRoot).save();

            if (pdfStatus) {
              pdfStatus.textContent = 'PDF download started.';
            }
          } catch (error) {
            console.error('PDF export failed:', error);
            if (pdfStatus) {
              pdfStatus.textContent = 'PDF export failed. Please try again.';
            }
          } finally {
            downloadBtn.disabled = false;
            reportRoot.classList.remove('pdf-exporting');
            setTimeout(() => {
              if (pdfStatus && pdfStatus.textContent === 'PDF download started.') {
                pdfStatus.textContent = '';
              }
            }, 3000);
          }
        });
      }
    });
  </script>
</body>
</html>
"""

def generate_report(results: list[dict], output_path: str = "output/report.html"):
    """
    Generates the compliance QA report using the 13 categories.
    """
    all_issues = [i for r in results for i in r.get("issues", [])]
    total_issues = len(all_issues)
    high_count   = sum(1 for i in all_issues if i.get("severity") == "HIGH")
    medium_count = sum(1 for i in all_issues if i.get("severity") == "MEDIUM")
    low_count    = sum(1 for i in all_issues if i.get("severity") == "LOW")
    bad_pages    = sum(1 for r in results if r.get("page_has_issues"))
    ok_pages     = len(results) - bad_pages

    # 1. Map global categories, assign anchors, and calculate drawing quality scores
    global_categories = {name: {"failed_count": 0, "status": "PASS"} for name in CATEGORIES_LIST}
    for idx, r in enumerate(results):
        r["index"] = idx + 1
        
        # Use pre-calculated score from the analyzer, fallback if missing
        if "score" not in r:
            score = 100
            fallback_weights = {
                "Drawing Layout": 10,
                "Views & Geometry": 15,
                "Dimensions & Tolerances": 15,
                "Notes & Annotations": 10,
                "Title Block": 10,
                "Revision History": 5,
                "BOM / Tables": 10,
                "Symbols & Standards": 5,
                "Styling & Layers": 5,
                "Scale & Proportion": 5,
                "Visual Quality": 5,
                "Conversion Integrity": 3,
                "Compliance Rules": 2
            }
            for cat in r.get("categories_report", []):
                if cat["status"] == "FAIL":
                    score -= fallback_weights.get(cat["name"], 0)
            r["score"] = max(0, score)

        for cat in r.get("categories_report", []):
            if cat["status"] == "FAIL":
                global_categories[cat["name"]]["failed_count"] += 1
                global_categories[cat["name"]]["status"] = "FAIL"

    # Inline images as base64 to prevent local file CORS / tainted canvas security errors in browser PDF exports
    import base64
    for r in results:
        if "comparison_image" in r:
            img_path = Path(r["comparison_image"])
            inline_success = False
            # Check candidate locations to find the generated drawing image
            for path_candidate in [img_path, Path("output") / "comparisons" / img_path.name, Path("output") / img_path.name]:
                if path_candidate.exists():
                    try:
                        img_bytes = path_candidate.read_bytes()
                        encoded = base64.b64encode(img_bytes).decode("utf-8")
                        r["comparison_image"] = f"data:image/png;base64,{encoded}"
                        inline_success = True
                        break
                    except Exception:
                        pass
            if not inline_success:
                # Fallback to relative path if files cannot be read
                r["comparison_image"] = f"comparisons/{img_path.name}"

    template = Template(HTML_TEMPLATE)
    html = template.render(
        pages=results,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_pages=len(results),
        total_issues=total_issues,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        ok_pages=ok_pages,
        bad_pages=bad_pages,
        global_categories=global_categories
    )

    Path(output_path).write_text(html, encoding="utf-8")
