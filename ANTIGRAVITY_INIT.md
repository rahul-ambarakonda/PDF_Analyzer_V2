# 🧠 Drawing QA Agent — Cursor Project Init

> **Purpose:** This file is the single source of truth for Cursor AI to understand, scaffold, and build the entire Drawing QA Agent project. Read this fully before generating any code.

---

## 📌 Project Summary

A local Python CLI agent that compares two engineering drawing PDFs — one exported from **SolidWorks/SolidEdge** (reference/correct) and one from **Creo** (under review) — and generates a detailed QA report identifying visual issues such as text overlap, text misplacement, missing features, and missing annotations.

The agent uses **Llama 3.2 Vision running locally via Ollama** — no cloud API, fully offline.

---

## 🎯 Problem Statement

| Attribute        | Detail |
|------------------|--------|
| Input A          | Creo-exported PDF (may have issues) |
| Input B          | SolidWorks/SolidEdge PDF (reference, always correct) |
| Issue Types      | Text overlap, text misplacement, missing geometry, missing annotations, font issues, title block differences, broken leader lines |
| QA Style         | Visual inspection, like a human QA engineer would do |
| Output           | Structured JSON + HTML report with annotated comparison images |
| Runtime          | Fully local, no internet required after setup |

---

## 🗂️ Project Structure

```
drawing-qa/
│
├── CURSOR_INIT.md              ← THIS FILE (project context for Cursor)
│
├── main.py                     ← CLI entry point
├── config.py                   ← All configurable settings
│
├── core/
│   ├── __init__.py
│   ├── pdf_utils.py            ← PDF to image conversion (pymupdf)
│   ├── image_utils.py          ← Side-by-side compositing, tiling, annotation
│   ├── qa_agent.py             ← Ollama Vision API calls + prompt logic
│   └── report.py               ← HTML + JSON report generation
│
├── prompts/
│   └── qa_system_prompt.txt    ← The QA inspection prompt (editable without code changes)
│
├── output/                     ← Auto-created at runtime
│   ├── report.html
│   ├── report.json
│   └── comparisons/            ← Per-page side-by-side images saved here
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## ⚙️ config.py — All Settings

```python
# config.py

# --- PDF Rendering ---
PDF_DPI = 300                        # Higher = better quality, slower. 200 is minimum for drawings.

# --- Ollama ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2-vision:11b" # Change to "llama3.2-vision:90b" for better accuracy

# --- Tiling ---
ENABLE_TILING = True                 # If True, each page is split into quadrants for detailed analysis
TILE_GRID = (2, 2)                   # 2x2 = 4 tiles per page. Can use (3,3) for very dense drawings.

# --- Comparison Image Layout ---
LABEL_BAR_HEIGHT = 70                # Pixels for the top label bar on comparison images
DIVIDER_WIDTH = 20                   # Pixel gap between left and right images
REFERENCE_LABEL = "REFERENCE (SolidWorks / SolidEdge)"
REVIEW_LABEL = "CREO (Under Review)"
REFERENCE_LABEL_COLOR = (0, 140, 0)  # Green
REVIEW_LABEL_COLOR = (200, 0, 0)     # Red

# --- Output ---
OUTPUT_DIR = "output"
COMPARISONS_DIR = "output/comparisons"
REPORT_HTML_PATH = "output/report.html"
REPORT_JSON_PATH = "output/report.json"
SAVE_COMPARISON_IMAGES = True        # Save side-by-side images to disk for the HTML report

# --- Analysis ---
CONFIDENCE_THRESHOLD = 0.5           # Future use: filter low-confidence issues
```

---

## 📦 requirements.txt

```
pymupdf==1.24.5          # PDF to image (fitz)
Pillow==10.3.0           # Image compositing and annotation
ollama==0.2.1            # Ollama Python SDK
rich==13.7.1             # Pretty CLI output
tqdm==4.66.4             # Progress bars
jinja2==3.1.4            # HTML report templating
click==8.1.7             # CLI argument parsing
python-dotenv==1.0.1     # .env support
```

---

## 🚀 main.py — CLI Interface

```python
# main.py
# CLI Usage:
#   python main.py --ref solidworks.pdf --review creo.pdf
#   python main.py --ref solidworks.pdf --review creo.pdf --no-tiles
#   python main.py --ref solidworks.pdf --review creo.pdf --model llama3.2-vision:90b --dpi 200

import click
from core.pdf_utils import pdf_to_images
from core.image_utils import create_comparison_image, tile_image
from core.qa_agent import analyze_page
from core.report import generate_report
from config import *
from rich.console import Console
from tqdm import tqdm
import os, json

console = Console()

@click.command()
@click.option("--ref", required=True, help="Path to reference PDF (SolidWorks/SolidEdge)")
@click.option("--review", required=True, help="Path to review PDF (Creo)")
@click.option("--model", default=OLLAMA_MODEL, help="Ollama model name")
@click.option("--dpi", default=PDF_DPI, type=int, help="Rendering DPI")
@click.option("--tiles/--no-tiles", default=ENABLE_TILING, help="Enable quadrant tiling")
@click.option("--out", default=OUTPUT_DIR, help="Output directory")
def main(ref, review, model, dpi, tiles, out):
    """
    Engineering Drawing QA Agent
    Compares a Creo PDF against a SolidWorks/SolidEdge reference PDF
    and identifies visual issues using Llama 3.2 Vision (local Ollama).
    """
    os.makedirs(out, exist_ok=True)
    os.makedirs(f"{out}/comparisons", exist_ok=True)

    console.print(f"[bold green]Drawing QA Agent[/bold green]")
    console.print(f"  Reference : {ref}")
    console.print(f"  Review    : {review}")
    console.print(f"  Model     : {model}")
    console.print(f"  DPI       : {dpi}")
    console.print(f"  Tiling    : {'Enabled (2x2)' if tiles else 'Disabled'}\n")

    # Step 1: Convert PDFs to images
    console.print("[cyan]Converting PDFs to images...[/cyan]")
    ref_images = pdf_to_images(ref, dpi=dpi)
    review_images = pdf_to_images(review, dpi=dpi)

    if len(ref_images) != len(review_images):
        console.print(f"[yellow]⚠ Page count mismatch: ref={len(ref_images)}, review={len(review_images)}[/yellow]")

    page_count = min(len(ref_images), len(review_images))
    all_results = []

    # Step 2: Analyze page by page
    for page_num in tqdm(range(page_count), desc="Analyzing pages"):
        console.print(f"\n[bold]Page {page_num + 1} / {page_count}[/bold]")

        ref_img = ref_images[page_num]
        review_img = review_images[page_num]

        if tiles:
            # Analyze each quadrant separately for dense drawings
            ref_tiles = tile_image(ref_img)
            review_tiles = tile_image(review_img)
            tile_results = []
            for t_idx, (rt, ct) in enumerate(zip(ref_tiles, review_tiles)):
                comp = create_comparison_image(rt, ct, label_suffix=f" — Quadrant {t_idx+1}")
                result = analyze_page(comp, page_num + 1, tile=t_idx + 1, model=model)
                tile_results.append(result)
                if SAVE_COMPARISON_IMAGES:
                    save_path = f"{out}/comparisons/page_{page_num+1}_tile_{t_idx+1}.png"
                    with open(save_path, "wb") as f:
                        f.write(comp)
                    result["comparison_image"] = save_path
            # Merge tile results into page result
            page_result = merge_tile_results(tile_results, page_num + 1)
        else:
            comp = create_comparison_image(ref_img, review_img)
            page_result = analyze_page(comp, page_num + 1, model=model)
            if SAVE_COMPARISON_IMAGES:
                save_path = f"{out}/comparisons/page_{page_num+1}.png"
                with open(save_path, "wb") as f:
                    f.write(comp)
                page_result["comparison_image"] = save_path

        all_results.append(page_result)
        _print_page_summary(page_result, console)

    # Step 3: Generate reports
    with open(f"{out}/report.json", "w") as f:
        json.dump(all_results, f, indent=2)

    generate_report(all_results, output_path=f"{out}/report.html")
    console.print(f"\n[bold green]✅ Report saved to {out}/report.html[/bold green]")


def merge_tile_results(tile_results, page_num):
    """Merge 4 quadrant results into one page result."""
    all_issues = []
    for t in tile_results:
        all_issues.extend(t.get("issues", []))
    return {
        "page": page_num,
        "page_has_issues": any(t.get("page_has_issues") for t in tile_results),
        "issues": all_issues,
        "summary": " | ".join(t.get("summary", "") for t in tile_results if t.get("summary"))
    }


def _print_page_summary(result, console):
    if result.get("page_has_issues"):
        console.print(f"  [red]⚠ {len(result.get('issues', []))} issue(s) found[/red]")
        for issue in result.get("issues", []):
            sev_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "blue"}.get(issue.get("severity"), "white")
            console.print(f"    [{sev_color}][{issue.get('severity')}] {issue.get('type')} — {issue.get('location')}[/{sev_color}]")
    else:
        console.print("  [green]✅ No issues detected[/green]")


if __name__ == "__main__":
    main()
```

---

## 🔧 core/pdf_utils.py

```python
# core/pdf_utils.py
"""
Converts PDF pages to PNG bytes using PyMuPDF (fitz).
Returns a list of raw PNG bytes, one per page.
"""

import fitz  # pymupdf


def pdf_to_images(pdf_path: str, dpi: int = 300) -> list[bytes]:
    """
    Convert each page of a PDF to a PNG image.

    Args:
        pdf_path: Path to the PDF file
        dpi: Rendering resolution. 300 recommended for engineering drawings.

    Returns:
        List of PNG image bytes, one per page.
    """
    doc = fitz.open(pdf_path)
    images = []
    zoom = dpi / 72  # 72 is PyMuPDF's base DPI
    matrix = fitz.Matrix(zoom, zoom)

    for page_index in range(len(doc)):
        page = doc[page_index]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        images.append(pixmap.tobytes("png"))

    doc.close()
    return images
```

---

## 🖼️ core/image_utils.py

```python
# core/image_utils.py
"""
Handles all image manipulation:
- create_comparison_image: Side-by-side composite with labeled headers
- tile_image: Splits an image into a 2x2 grid for detailed analysis
"""

import io
from PIL import Image, ImageDraw, ImageFont
from config import (
    LABEL_BAR_HEIGHT, DIVIDER_WIDTH,
    REFERENCE_LABEL, REVIEW_LABEL,
    REFERENCE_LABEL_COLOR, REVIEW_LABEL_COLOR
)


def _bytes_to_image(img_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(img_bytes)).convert("RGB")


def _image_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_comparison_image(
    ref_bytes: bytes,
    review_bytes: bytes,
    label_suffix: str = ""
) -> bytes:
    """
    Creates a side-by-side comparison image.
    Left = Reference (green label), Right = Creo review (red label).

    Args:
        ref_bytes: PNG bytes of reference page
        review_bytes: PNG bytes of Creo page
        label_suffix: Optional string appended to both labels (e.g. " — Quadrant 1")

    Returns:
        PNG bytes of the combined comparison image
    """
    ref_img = _bytes_to_image(ref_bytes)
    review_img = _bytes_to_image(review_bytes)

    # Normalize heights
    target_h = max(ref_img.height, review_img.height)
    ref_img = ref_img.resize(
        (int(ref_img.width * target_h / ref_img.height), target_h),
        Image.LANCZOS
    )
    review_img = review_img.resize(
        (int(review_img.width * target_h / review_img.height), target_h),
        Image.LANCZOS
    )

    total_w = ref_img.width + DIVIDER_WIDTH + review_img.width
    total_h = target_h + LABEL_BAR_HEIGHT

    combined = Image.new("RGB", (total_w, total_h), "white")
    draw = ImageDraw.Draw(combined)

    # Try to load a font, fall back to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except Exception:
        font = ImageFont.load_default()

    # Draw labels
    ref_label = REFERENCE_LABEL + label_suffix
    review_label = REVIEW_LABEL + label_suffix
    draw.text((10, 15), ref_label, fill=REFERENCE_LABEL_COLOR, font=font)
    draw.text((ref_img.width + DIVIDER_WIDTH + 10, 15), review_label, fill=REVIEW_LABEL_COLOR, font=font)

    # Draw divider
    draw.rectangle(
        [ref_img.width, 0, ref_img.width + DIVIDER_WIDTH, total_h],
        fill=(180, 180, 180)
    )

    # Paste images
    combined.paste(ref_img, (0, LABEL_BAR_HEIGHT))
    combined.paste(review_img, (ref_img.width + DIVIDER_WIDTH, LABEL_BAR_HEIGHT))

    return _image_to_bytes(combined)


def tile_image(img_bytes: bytes, grid: tuple = (2, 2)) -> list[bytes]:
    """
    Splits an image into a grid of tiles for detailed sub-region analysis.

    Args:
        img_bytes: PNG bytes of the full page image
        grid: Tuple (cols, rows). Default (2,2) = 4 quadrants.

    Returns:
        List of PNG bytes, one per tile (row-major order)
    """
    img = _bytes_to_image(img_bytes)
    w, h = img.size
    cols, rows = grid
    tile_w, tile_h = w // cols, h // rows
    tiles = []

    for row in range(rows):
        for col in range(cols):
            box = (
                col * tile_w,
                row * tile_h,
                (col + 1) * tile_w,
                (row + 1) * tile_h
            )
            tile = img.crop(box)
            tiles.append(_image_to_bytes(tile))

    return tiles
```

---

## 🤖 core/qa_agent.py

```python
# core/qa_agent.py
"""
Sends comparison images to Llama 3.2 Vision via Ollama and returns structured QA results.
"""

import base64
import json
import ollama
from config import OLLAMA_BASE_URL
from pathlib import Path

# Load prompt from file so it can be edited without touching code
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "qa_system_prompt.txt"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def analyze_page(
    comparison_image_bytes: bytes,
    page_num: int,
    tile: int = None,
    model: str = "llama3.2-vision:11b"
) -> dict:
    """
    Send a comparison image to Llama 3.2 Vision and return parsed QA results.

    Args:
        comparison_image_bytes: PNG bytes of the side-by-side comparison image
        page_num: Page number (for labeling)
        tile: Tile index if tiling is active (1-4), else None
        model: Ollama model string

    Returns:
        Parsed dict with keys: page, tile, page_has_issues, issues[], summary
    """
    prompt = _load_prompt()
    img_b64 = base64.b64encode(comparison_image_bytes).decode("utf-8")

    client = ollama.Client(host=OLLAMA_BASE_URL)

    try:
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [img_b64]
                }
            ]
        )
        raw_text = response["message"]["content"]
    except Exception as e:
        return {
            "page": page_num,
            "tile": tile,
            "page_has_issues": False,
            "issues": [],
            "summary": f"ERROR: Could not get response from Ollama — {str(e)}",
            "error": True
        }

    # Strip markdown code fences if model wraps JSON in ```json ... ```
    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip()

    try:
        result = json.loads(clean)
    except json.JSONDecodeError:
        # Model returned non-JSON — wrap it
        result = {
            "page_has_issues": True,
            "issues": [],
            "summary": raw_text,
            "parse_error": True
        }

    result["page"] = page_num
    result["tile"] = tile
    return result
```

---

## 📝 prompts/qa_system_prompt.txt

```
You are a senior CAD/engineering drawing QA inspector with 15 years of experience reviewing technical drawings for aerospace and manufacturing.

You are looking at TWO engineering drawings placed SIDE BY SIDE in a single image:
  - LEFT side:  REFERENCE drawing (SolidWorks or SolidEdge) — this is the CORRECT, original version
  - RIGHT side: CREO drawing — this is the version under review and MAY have issues

Your task:
Carefully compare both drawings and identify ALL problems visible in the CREO drawing (right side) that are NOT present in the reference (left side).

Issue categories to check:
1. TEXT_OVERLAP       — Any text, dimension, or annotation that overlaps another element (text or geometry)
2. TEXT_MISPLACEMENT  — Any annotation, dimension, or note that has moved to the wrong position
3. MISSING_FEATURE    — Any line, arc, circle, hatch, or geometric feature present in reference but absent in Creo
4. MISSING_ANNOTATION — Any dimension, tolerance, GD&T symbol, surface finish, weld symbol, or note missing in Creo
5. FONT_ISSUE         — Text rendered with wrong size, weight, or style compared to reference
6. TITLE_BLOCK_ISSUE  — Any difference in the title block (text, borders, company info, revision, scale)
7. LEADER_LINE_ISSUE  — Broken, misrouted, or missing leader lines connecting annotations to features
8. OTHER              — Any other visual discrepancy not covered above

Severity guide:
  HIGH   — Issue that would cause misinterpretation or manufacturing error
  MEDIUM — Issue that degrades readability or professionalism
  LOW    — Minor cosmetic issue unlikely to cause problems

IMPORTANT RULES:
- Only flag issues in the CREO side (right). Do NOT critique the reference.
- Be specific about location: use compass directions (top-left, center-right, bottom) or reference features (near Ø12 hole callout, in title block revision field, etc.)
- If both sides look identical or nearly identical, return page_has_issues: false with an empty issues array.
- Do NOT hallucinate issues that are not clearly visible.

Respond ONLY with a valid JSON object. No preamble. No explanation. No markdown fences. Raw JSON only.

Schema:
{
  "page_has_issues": <boolean>,
  "issues": [
    {
      "type": "<TEXT_OVERLAP | TEXT_MISPLACEMENT | MISSING_FEATURE | MISSING_ANNOTATION | FONT_ISSUE | TITLE_BLOCK_ISSUE | LEADER_LINE_ISSUE | OTHER>",
      "severity": "<HIGH | MEDIUM | LOW>",
      "location": "<specific location description>",
      "description": "<detailed description of what is wrong>",
      "reference_has": "<what the reference drawing shows correctly>",
      "creo_shows": "<what the Creo drawing shows instead>"
    }
  ],
  "summary": "<one paragraph overall assessment of the Creo drawing quality on this page>"
}
```

---

## 📊 core/report.py

```python
# core/report.py
"""
Generates the final HTML QA report from all page analysis results.
"""

from jinja2 import Template
from pathlib import Path
import json
from datetime import datetime


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Drawing QA Report</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #f5f5f5; color: #222; }
    header { background: #1a1a2e; color: white; padding: 24px 32px; }
    header h1 { margin: 0; font-size: 1.6rem; }
    header p { margin: 4px 0 0; opacity: 0.7; font-size: 0.9rem; }
    .summary-bar { display: flex; gap: 24px; padding: 16px 32px; background: white; border-bottom: 1px solid #ddd; }
    .stat { text-align: center; }
    .stat .num { font-size: 2rem; font-weight: bold; }
    .stat .label { font-size: 0.8rem; color: #666; }
    .red { color: #c0392b; } .green { color: #27ae60; } .orange { color: #e67e22; }
    .page-section { margin: 24px 32px; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }
    .page-header { padding: 14px 20px; font-size: 1.1rem; font-weight: bold; display: flex; justify-content: space-between; align-items: center; }
    .ok { background: #eafaf1; } .bad { background: #fdf2f2; }
    .comparison-img { width: 100%; display: block; border-top: 1px solid #eee; }
    .issues-list { padding: 16px 20px; }
    .issue-card { border-left: 5px solid; border-radius: 4px; padding: 12px 16px; margin-bottom: 12px; }
    .HIGH  { border-color: #e74c3c; background: #fff5f5; }
    .MEDIUM{ border-color: #f39c12; background: #fffbf0; }
    .LOW   { border-color: #3498db; background: #f0f7ff; }
    .issue-type { font-weight: bold; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; }
    .issue-loc { color: #666; font-size: 0.85rem; margin: 2px 0 6px; }
    .issue-desc { margin: 0 0 8px; }
    .diff-row { display: flex; gap: 16px; font-size: 0.85rem; }
    .diff-ref { color: #27ae60; } .diff-creo { color: #c0392b; }
    .no-issues { padding: 16px 20px; color: #27ae60; font-weight: bold; }
    .summary-text { padding: 12px 20px; font-size: 0.9rem; color: #555; border-top: 1px solid #f0f0f0; font-style: italic; }
  </style>
</head>
<body>
<header>
  <h1>🔍 Engineering Drawing QA Report</h1>
  <p>Generated: {{ generated_at }} &nbsp;|&nbsp; Pages analyzed: {{ total_pages }} &nbsp;|&nbsp; Total issues: {{ total_issues }}</p>
</header>

<div class="summary-bar">
  <div class="stat"><div class="num red">{{ high_count }}</div><div class="label">HIGH</div></div>
  <div class="stat"><div class="num orange">{{ medium_count }}</div><div class="label">MEDIUM</div></div>
  <div class="stat"><div class="num" style="color:#3498db">{{ low_count }}</div><div class="label">LOW</div></div>
  <div class="stat"><div class="num green">{{ ok_pages }}</div><div class="label">CLEAN PAGES</div></div>
  <div class="stat"><div class="num red">{{ bad_pages }}</div><div class="label">PAGES WITH ISSUES</div></div>
</div>

{% for page in pages %}
<div class="page-section">
  <div class="page-header {{ 'bad' if page.page_has_issues else 'ok' }}">
    <span>Page {{ page.page }}{% if page.tile %} — Tile {{ page.tile }}{% endif %}</span>
    <span>{{ '⚠ ' + page.issues|length|string + ' issue(s)' if page.page_has_issues else '✅ No issues' }}</span>
  </div>

  {% if page.comparison_image %}
  <img class="comparison-img" src="{{ page.comparison_image }}" alt="Page {{ page.page }} comparison">
  {% endif %}

  {% if page.page_has_issues %}
  <div class="issues-list">
    {% for issue in page.issues %}
    <div class="issue-card {{ issue.severity }}">
      <div class="issue-type">{{ issue.severity }} — {{ issue.type }}</div>
      <div class="issue-loc">📍 {{ issue.location }}</div>
      <p class="issue-desc">{{ issue.description }}</p>
      <div class="diff-row">
        <span class="diff-ref">✅ Reference: {{ issue.reference_has }}</span>
        <span class="diff-creo">❌ Creo: {{ issue.creo_shows }}</span>
      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="no-issues">✅ This page looks correct. No issues detected.</div>
  {% endif %}

  {% if page.summary %}
  <div class="summary-text">{{ page.summary }}</div>
  {% endif %}
</div>
{% endfor %}
</body>
</html>
"""


def generate_report(results: list[dict], output_path: str = "output/report.html"):
    all_issues = [i for r in results for i in r.get("issues", [])]
    total_issues = len(all_issues)
    high_count   = sum(1 for i in all_issues if i.get("severity") == "HIGH")
    medium_count = sum(1 for i in all_issues if i.get("severity") == "MEDIUM")
    low_count    = sum(1 for i in all_issues if i.get("severity") == "LOW")
    bad_pages    = sum(1 for r in results if r.get("page_has_issues"))
    ok_pages     = len(results) - bad_pages

    # Convert absolute paths to relative for HTML portability
    for r in results:
        if "comparison_image" in r:
            r["comparison_image"] = Path(r["comparison_image"]).as_posix()

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
    )

    Path(output_path).write_text(html, encoding="utf-8")
```

---

## 🛠️ Setup Instructions

### 1. Install Ollama

```bash
# Linux / WSL
curl -fsSL https://ollama.com/install.sh | sh

# macOS
brew install ollama
```

### 2. Pull the Vision Model

```bash
# Minimum (8–12 GB VRAM or 16 GB RAM)
ollama pull llama3.2-vision:11b

# Better accuracy for dense drawings (requires 48+ GB VRAM or 64 GB RAM)
ollama pull llama3.2-vision:90b
```

### 3. Verify Ollama is Running

```bash
ollama serve   # Start server (runs on http://localhost:11434)
ollama list    # Should show llama3.2-vision:11b
```

### 4. Set Up Python Environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run the Agent

```bash
python main.py --ref drawings/solidworks_part.pdf --review drawings/creo_part.pdf
```

### 6. View the Report

Open `output/report.html` in any browser.

---

## 🧪 Testing Strategy

| Test Case | How to Test |
|---|---|
| Identical PDFs | Run both args pointing to the same file — expect 0 issues |
| Known text overlap | Use a manually corrupted test PDF |
| Multi-page drawing | Use a 3+ page drawing to verify tiling and page iteration |
| Ollama offline | Kill ollama and run — expect graceful error messages |
| Single-page drawing | Standard DIN A4 part drawing |

---

## 🔮 Future Enhancements (Do Not Build Now)

```
[ ] Pixel-diff pre-filter  — Use OpenCV to highlight changed bounding boxes before VLM
[ ] OCR text diff layer    — Tesseract/EasyOCR for a parallel text-only comparison
[ ] PDF metadata diff      — Compare embedded fonts, layers, and annotations in PDF structure
[ ] Streamlit UI           — Drag-and-drop web interface instead of CLI
[ ] Batch mode             — Compare entire folders of PDF pairs
[ ] Issue heatmap          — Overlay colored bounding boxes on the report images
[ ] Confidence scoring     — Ask model to score its own confidence (0.0–1.0) per issue
```

---

## 🧠 Cursor AI Instructions

> When Cursor AI reads this file, follow these rules:
>
> 1. **Scaffold the full project structure** exactly as defined in the Project Structure section.
> 2. **Do not deviate from module responsibilities** — each file has a clearly defined role.
> 3. **Use the code skeletons above as the starting implementation** — fill in any missing logic following the patterns shown.
> 4. **The prompt in `prompts/qa_system_prompt.txt` must be written to a file** — do not hardcode it in `qa_agent.py`.
> 5. **All configuration goes in `config.py`** — no magic numbers in other files.
> 6. **Error handling is mandatory** in `qa_agent.py` — Ollama calls can fail silently.
> 7. **Run `python main.py --help`** as the first smoke test after scaffolding.
> 8. **Do not add any cloud APIs, paid services, or external network calls** — everything must run offline.
