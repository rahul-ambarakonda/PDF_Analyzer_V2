# core/image_utils.py
"""
Handles image manipulation, composite side-by-side rendering,
and drawing color-coded bounding box annotations for QA issues.
"""

import io
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Disable Pillow DecompressionBombWarning for very large drawing sheets
Image.MAX_IMAGE_PIXELS = None

from config import (
    LABEL_BAR_HEIGHT, DIVIDER_WIDTH,
    REFERENCE_LABEL, REVIEW_LABEL,
    REFERENCE_LABEL_COLOR, REVIEW_LABEL_COLOR,
    COLOR_MISSING_ANNOTATION, COLOR_TEXT_MISPLACEMENT,
    COLOR_TEXT_OVERLAP, COLOR_GEOMETRIC_DIFFERENCE
)

def _bytes_to_image(img_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(img_bytes)).convert("RGB")

def _image_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def _load_font(size: int = 14) -> ImageFont.ImageFont:
    """Finds a standard font on Windows/Linux or falls back to default."""
    font_paths = [
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\calibrib.ttf",
        "C:\\Windows\\Fonts\\calibri.ttf",
        "C:\\Windows\\Fonts\\segoeuib.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
                
    # Dynamic search on Windows if listed paths fail
    if os.name == "nt":
        font_dir = "C:\\Windows\\Fonts"
        if os.path.exists(font_dir):
            try:
                files = os.listdir(font_dir)
                for f in files:
                    if f.lower().endswith(".ttf"):
                        full_path = os.path.join(font_dir, f)
                        try:
                            return ImageFont.truetype(full_path, size)
                        except Exception:
                            continue
            except Exception:
                pass

    # Try modern default font with size
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        pass
        
    return ImageFont.load_default()

def boxes_overlap(box1, box2):
    """
    Checks if two bounding boxes box1=(x0, y0, x1, y1) and box2=(x0, y0, x1, y1) overlap.
    """
    return not (box1[2] < box2[0] or box1[0] > box2[2] or
                box1[3] < box2[1] or box1[1] > box2[3])

def create_comparison_image(
    ref_bytes: bytes,
    review_bytes: bytes,
    issues: list[dict],
    ref_pdf_size: tuple[float, float],      # (width, height) in PDF points
    review_pdf_size: tuple[float, float],   # (width, height) in PDF points
    label_suffix: str = ""
) -> bytes:
    """
    Renders the target Creo review page with highlighted QA issues and a legend at the bottom.
    """
    review_img = _bytes_to_image(review_bytes)

    target_h = review_img.height
    review_resized_w = review_img.width

    scale_factor = max(1.0, target_h / 1200.0)
    scaled_label_bar_h = int(LABEL_BAR_HEIGHT * scale_factor)
    scaled_legend_bar_h = int(260 * scale_factor)

    total_w = review_resized_w
    total_h = target_h + scaled_label_bar_h + scaled_legend_bar_h

    combined = Image.new("RGB", (total_w, total_h), "white")
    
    # Paste Creo review page
    combined.paste(review_img, (0, scaled_label_bar_h))

    draw = ImageDraw.Draw(combined)

    header_font = _load_font(int(26 * scale_factor))
    review_label = REVIEW_LABEL + label_suffix
    
    # Draw text labels in header bar
    text_y = int((scaled_label_bar_h - (26 * scale_factor)) / 2)
    if text_y < 5:
        text_y = 5
    draw.text((int(20 * scale_factor), text_y), review_label, fill=REVIEW_LABEL_COLOR, font=header_font)

    # Draw legend background (light gray bar at the bottom)
    legend_y0 = total_h - scaled_legend_bar_h
    draw.rectangle(
        [0, legend_y0, total_w, total_h],
        fill=(245, 245, 245)
    )
    # Draw a line separating the drawings from the legend
    draw.line([(0, legend_y0), (total_w, legend_y0)], fill=(200, 200, 200), width=max(2, int(3 * scale_factor)))

    # Draw legend items
    legend_items = [
        ("Missing Annotation", COLOR_MISSING_ANNOTATION, "Exists in Reference, missing in Creo review"),
        ("Text Misplacement", COLOR_TEXT_MISPLACEMENT, "Label position shifted from Reference"),
        ("Text Overlap", COLOR_TEXT_OVERLAP, "Label colliding with other labels or geometry"),
        ("Geometric Difference", COLOR_GEOMETRIC_DIFFERENCE, "Visual discrepancies in lines/curves")
    ]
    
    legend_font_bold = _load_font(max(20, int(26 * scale_factor)))
    legend_font_regular = _load_font(max(16, int(18 * scale_factor)))
    
    box_size = int(32 * scale_factor)
    
    # 2x2 Grid Layout for the Legend (increases horizontal space and readability)
    for idx, (title, color, desc) in enumerate(legend_items):
        row = idx // 2
        col = idx % 2
        
        item_x0 = col * (total_w // 2) + int(80 * scale_factor)
        item_y = legend_y0 + int(35 * scale_factor) + row * int(105 * scale_factor)
        
        # Draw colored rectangle
        draw.rectangle(
            [item_x0, item_y, item_x0 + box_size, item_y + box_size],
            fill=color, outline=(0, 0, 0), width=max(2, int(3 * scale_factor))
        )
        
        # Draw title
        draw.text((item_x0 + box_size + int(15 * scale_factor), item_y - int(4 * scale_factor)), title, fill=(0, 0, 0), font=legend_font_bold)
        
        # Draw description
        draw.text((item_x0 + box_size + int(15 * scale_factor), item_y + box_size - int(5 * scale_factor)), desc, fill=(100, 100, 100), font=legend_font_regular)

    # Scale factors from PDF points to coordinates
    review_pdf_w, review_pdf_h = review_pdf_size
    scale_review = target_h / review_pdf_h

    # Color mapping for issue categories
    color_map = {
        "MISSING_ANNOTATION": COLOR_MISSING_ANNOTATION,
        "TEXT_MISPLACEMENT": COLOR_TEXT_MISPLACEMENT,
        "TEXT_OVERLAP": COLOR_TEXT_OVERLAP,
        "GEOMETRIC_DIFFERENCE": COLOR_GEOMETRIC_DIFFERENCE
    }

    placed_label_boxes = []

    # Bounding box font and styling - made thinner as requested
    box_width = max(2, int(2.5 * scale_factor))
    label_font = _load_font(max(14, int(16 * scale_factor)))

    for idx, issue in enumerate(issues, start=1):
        category = issue.get("type")
        color = color_map.get(category, (128, 128, 128))
        
        review_bbox = issue.get("review_bbox")
        review_polygon = issue.get("review_polygon")
        review_polygon2 = issue.get("review_polygon2")

        def to_review_pixel(x, y):
            px = x * scale_review
            py = scaled_label_bar_h + y * scale_review
            return px, py

        # Determine label text (only the index number like #3)
        label_text = f"#{idx}"

        # Resolve scaled geometry coordinates
        if review_polygon:
            scaled_pts = [to_review_pixel(pt[0], pt[1]) for pt in review_polygon]
            draw.line(scaled_pts + [scaled_pts[0]], fill=color, width=box_width)
            
            if review_polygon2:
                scaled_pts2 = [to_review_pixel(pt[0], pt[1]) for pt in review_polygon2]
                draw.line(scaled_pts2 + [scaled_pts2[0]], fill=color, width=box_width)
                
            xs = [pt[0] for pt in scaled_pts]
            ys = [pt[1] for pt in scaled_pts]
            min_x = min(xs)
            max_x = max(xs)
            min_y = min(ys)
            max_y = max(ys)
        elif review_bbox:
            cx0, cy0 = to_review_pixel(review_bbox[0], review_bbox[1])
            cx1, cy1 = to_review_pixel(review_bbox[2], review_bbox[3])
            draw.rectangle([cx0, cy0, cx1, cy1], outline=color, width=box_width)
            min_x = min(cx0, cx1)
            max_x = max(cx0, cx1)
            min_y = min(cy0, cy1)
            max_y = max(cy0, cy1)
        else:
            continue

        # Get text size
        try:
            bbox = draw.textbbox((0, 0), label_text, font=label_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except AttributeError:
            text_w, text_h = draw.textsize(label_text, font=label_font)

        gap = int(4 * scale_factor)
        margin = int(2 * scale_factor)

        # Dynamic search for non-overlapping position
        found_pos = False
        label_x, label_y = min_x, min_y - text_h - gap

        # Candidate 1: Stack upwards above min_y
        for i in range(10):
            cy = min_y - text_h - gap - i * (text_h + gap)
            cx = min_x
            if cy >= scaled_label_bar_h:
                candidate_box = (cx - margin, cy - margin, cx + text_w + margin, cy + text_h + margin)
                if not any(boxes_overlap(candidate_box, pb) for pb in placed_label_boxes):
                    label_x, label_y = cx, cy
                    found_pos = True
                    break
        
        # Candidate 2: Stack downwards below max_y
        if not found_pos:
            for i in range(10):
                cy = max_y + gap + i * (text_h + gap)
                cx = min_x
                if cy + text_h <= total_h - scaled_legend_bar_h:
                    candidate_box = (cx - margin, cy - margin, cx + text_w + margin, cy + text_h + margin)
                    if not any(boxes_overlap(candidate_box, pb) for pb in placed_label_boxes):
                        label_x, label_y = cx, cy
                        found_pos = True
                        break

        # Candidate 3: Shift horizontally to the right above min_y
        if not found_pos:
            for j in range(1, 5):
                for i in range(5):
                    cy = min_y - text_h - gap - i * (text_h + gap)
                    cx = min_x + j * (text_w + gap * 2)
                    if cy >= scaled_label_bar_h and cx + text_w <= total_w:
                        candidate_box = (cx - margin, cy - margin, cx + text_w + margin, cy + text_h + margin)
                        if not any(boxes_overlap(candidate_box, pb) for pb in placed_label_boxes):
                            label_x, label_y = cx, cy
                            found_pos = True
                            break
                if found_pos:
                    break

        # Fallback to default
        if not found_pos:
            label_x = min_x
            label_y = max(scaled_label_bar_h, min_y - text_h - gap)

        # Place label text and record label bounding box
        draw.text((label_x, label_y), label_text, fill=color, font=label_font)
        placed_label_boxes.append((label_x - margin, label_y - margin, label_x + text_w + margin, label_y + text_h + margin))

    return _image_to_bytes(combined)
