# config.py

# --- PDF Rendering ---
PDF_DPI = 300                        # Resolution to render PDF pages (300 DPI is standard for engineering drawings)

# --- Analysis Tolerances ---
# PyMuPDF uses PDF points (1/72 inch). 
# At 300 DPI, 1 point = 300 / 72 ≈ 4.17 pixels.
# A tolerance of 3 points is ~12.5 pixels (approx. 1 mm on physical paper).
TEXT_DISTANCE_TOLERANCE = 3.0        # Max shift in PDF points before a text block is considered misplaced
MAX_MISPLACEMENT_SHIFT = 50.0        # Max shift in PDF points to still match text; above this, it is classified as missing

# --- OpenCV Pixel Diffing ---
IMAGE_DIFF_THRESHOLD = 30            # Pixel value difference threshold (0-255) to mark a pixel as changed
MIN_DIFF_CONTOUR_AREA = 100          # Min pixel area of difference contours to filter out noise and compression artifacts

# --- Comparison Image Layout ---
LABEL_BAR_HEIGHT = 70                # Pixels for the top label bar on comparison images
DIVIDER_WIDTH = 20                   # Pixel gap between left and right images
REFERENCE_LABEL = "REFERENCE (Input)"
REVIEW_LABEL = "CREO (Review)"
REFERENCE_LABEL_COLOR = (0, 140, 0)  # Green
REVIEW_LABEL_COLOR = (200, 0, 0)     # Red

# --- Issue Category Colors (RGB for Pillow) ---
COLOR_MISSING_ANNOTATION = (255, 0, 0)      # Red (exists in reference, missing in review)
COLOR_TEXT_MISPLACEMENT = (0, 0, 255)        # Blue (exists in both but location shifted)
COLOR_TEXT_OVERLAP = (255, 165, 0)          # Orange (text boxes colliding)
COLOR_GEOMETRIC_DIFFERENCE = (255, 0, 255)  # Magenta (line/drawing differences)

# --- Output ---
OUTPUT_DIR = "output"
COMPARISONS_DIR = "output/comparisons"
REPORT_HTML_PATH = "output/report.html"
REPORT_JSON_PATH = "output/report.json"
SAVE_COMPARISON_IMAGES = True
