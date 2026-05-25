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

    header .meta-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 24px;
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
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
      background-color: #1a2235;
      padding: 10px;
      border-bottom: 1px solid var(--panel-border);
      overflow: hidden;
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

    .no-issues-msg {
      padding: 12px 0;
      color: var(--color-clean);
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
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

    <div class="section-title">Page Breakdown Analysis</div>

    <!-- Pages List -->
    {% for page in pages %}
    <div class="page-section">
      <div class="page-header {{ 'bad' if page.page_has_issues else 'ok' }}">
        <span>Page {{ page.page }}</span>
        <span class="status-pill {{ 'bad' if page.page_has_issues else 'ok' }}">
          {{ page.status }} - {{ page.issues|length }} issue(s) detected
        </span>
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

        <div style="margin-bottom: 12px; font-weight:700; font-size:1rem; color: #a5b4fc;">Audit Categories Breakdown:</div>
        
        <!-- Collapsible Category Grid -->
        <div class="categories-grid">
          {% for cat in page.categories_report %}
          <div class="category-card {{ 'failed' if cat.status == 'FAIL' else 'passed' }}" onclick="toggleDetails(this)">
            <div class="category-card-header">
              <span class="category-card-name">{{ cat.name }}</span>
              <span class="category-card-status {{ 'failed' if cat.status == 'FAIL' else 'passed' }}">{{ cat.status }}</span>
            </div>
            {% if cat.issues %}
            <div class="category-card-details">
              <ul>
                {% for issue_desc in cat.issues %}
                <li>{{ issue_desc }}</li>
                {% endfor %}
              </ul>
            </div>
            <span class="click-hint">Click to show details</span>
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

  <script>
    function toggleDetails(card) {
      const details = card.querySelector('.category-card-details');
      const hint = card.querySelector('.click-hint');
      if (details) {
        const isVisible = details.style.display === 'block';
        details.style.display = isVisible ? 'none' : 'block';
        if (hint) {
          hint.innerText = isVisible ? 'Click to show details' : 'Click to hide details';
        }
      }
    }
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

    # 1. Map global categories from individual page reports
    global_categories = {name: {"failed_count": 0, "status": "PASS"} for name in CATEGORIES_LIST}
    for r in results:
        for cat in r.get("categories_report", []):
            if cat["status"] == "FAIL":
                global_categories[cat["name"]]["failed_count"] += 1
                global_categories[cat["name"]]["status"] = "FAIL"

    # Keep image paths relative for web portability
    for r in results:
        if "comparison_image" in r:
            r["comparison_image"] = f"comparisons/{Path(r['comparison_image']).name}"

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
