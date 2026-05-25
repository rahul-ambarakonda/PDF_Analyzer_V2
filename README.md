# 🔍 Engineering Drawing QA Agent (Code-Based Comparison)

A local Python command-line tool that compares two engineering drawing PDFs — one Reference drawing (exported from SolidWorks/SolidEdge, in `Input_PDFs`) and one Review drawing (exported from Creo, in `Creo_PDFs`) — and automatically identifies and highlights discrepancies using rule-based text analysis and OpenCV pixel diffing.

It requires **no cloud APIs and no local LLMs/Ollama**. It runs completely offline and finishes in seconds.

---

## 🛠️ Key Features

1. **Text Annotation QA**:
   - Compares searchable text labels (dimensions, tolerances, notes) between drawings.
   - Detects `MISSING_ANNOTATION` (annotations on reference drawing that are missing in Creo review).
   - Detects `TEXT_MISPLACEMENT` (annotations present in both but shifted by coordinates beyond the allowed tolerance).
   - Detects `TEXT_OVERLAP` (colliding labels in Creo).
   - *Ignores font and font styling differences.*
2. **Visual/Geometric QA**:
   - Renders drawing pages at high DPI.
   - Runs pixel-level absolute difference checks (`cv2.absdiff`) to identify drawing geometry changes, missing features, or broken leader lines.
   - Filters out pixel discrepancies overlapping with already flagged text issues to prevent duplicate errors.
   - Flags remaining mismatches as `GEOMETRIC_DIFFERENCE`.
3. **Interactive HTML Report**:
   - Generates a gorgeous dark-mode report in `output/report.html` with a dashboard of issues grouped by severity.
   - Displays side-by-side drawings annotated with color-coded boxes pointing out the exact location of discrepancies.

---

## 🎨 Bounding Box Color Scheme

Visual issues are highlighted directly on the output drawings:
- <span style="color:red">**Red**</span>: `MISSING_ANNOTATION` (missing text/dimensions)
- <span style="color:blue">**Blue**</span>: `TEXT_MISPLACEMENT` (with a line connecting the reference position to the new position)
- <span style="color:orange">**Orange**</span>: `TEXT_OVERLAP` (colliding text in Creo)
- <span style="color:magenta">**Magenta**</span>: `GEOMETRIC_DIFFERENCE` (visual/line discrepancies detected via OpenCV)

---

## 🚀 Setup Instructions

### 1. Set Up Python Virtual Environment
Initialize a virtual environment and install the required dependencies:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

---

## 🏃 Running the Agent

### Compare All Files in input and target folders (Default)
By default, the CLI compares all matching PDFs found in the `Input_PDFs` (Reference source) and `Creo_PDFs` (Creo target) directories:
```bash
python main.py
```

### Compare Single PDF Files
You can also run comparison on a specific pair of files:
```bash
python main.py --ref Input_PDFs/40-P-P011500-018.pdf --review Creo_PDFs/40-P-P011500-018.pdf
```

### Configure Settings
To view configuration flags and options:
```bash
python main.py --help
```
You can customize thresholds, fonts, and layout colors inside `config.py`.

---

## 📊 Viewing the Report
After running, open **`output/report.html`** in any web browser to see the interactive HTML dashboard.
Detailed structured JSON data is saved to **`output/report.json`**.
