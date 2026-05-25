# core/pdf_utils.py
"""
Utility functions to convert PDF pages to images and extract text structure.
Uses PyMuPDF (fitz).
"""

import fitz  # pymupdf
import io
from PIL import Image

def pdf_to_images(pdf_path: str, dpi: int = 300) -> list[bytes]:
    """
    Convert each page of a PDF to a PNG image.
    Caps the maximum image dimension to 4000px to prevent out-of-memory errors on large pages.

    Args:
        pdf_path: Path to the PDF file
        dpi: Rendering resolution. 300 recommended for engineering drawings.

    Returns:
        List of PNG image bytes, one per page.
    """
    doc = fitz.open(pdf_path)
    images = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        w, h = page.rect.width, page.rect.height
        
        # Calculate target zoom factor, capping max dimension to 4000px
        max_dim = max(w, h)
        zoom = dpi / 72.0
        if max_dim * zoom > 4000:
            zoom = 4000.0 / max_dim
            
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        images.append(pixmap.tobytes("png"))

    doc.close()
    return images

def extract_pdf_text_elements(pdf_path: str) -> list[list[dict]]:
    """
    Extracts text elements (text, bbox, font, size) from each page of the PDF.
    Transforms bounding boxes based on page rotation to match user-visible orientation.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        List of lists (one list per page), where each page list contains dictionaries:
        {
            "text": str,
            "bbox": (x0, y0, x1, y1),  # In user-visible/rotated PDF points (72 DPI)
            "font": str,
            "size": float
        }
    """
    doc = fitz.open(pdf_path)
    all_pages_text = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_text_elements = []
        rot_mat = page.rotation_matrix
        
        # Get page dictionary containing blocks, lines, spans
        text_dict = page.get_text("dict")
        
        for block in text_dict.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text_str = span["text"].strip()
                        if not text_str:
                            continue
                        
                        # Rotate bounding box using rotation matrix to match user-visible orientation
                        rect = fitz.Rect(span["bbox"])
                        rect = rect * rot_mat
                        
                        # Span details
                        page_text_elements.append({
                            "text": text_str,
                            "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),  # (x0, y0, x1, y1)
                            "font": span["font"],
                            "size": span["size"]
                        })
        
        all_pages_text.append(page_text_elements)
        
    doc.close()
    return all_pages_text

def extract_pdf_drawings(pdf_path: str) -> list[list[tuple[tuple[float, float], tuple[float, float]]]]:
    """
    Extracts drawing line segments from each page of the PDF.
    Transforms coordinates by page rotation to match user-visible orientation.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        List of lists (one per page), where each page list contains line segments:
        ((x0, y0), (x1, y1))
    """
    doc = fitz.open(pdf_path)
    all_pages_drawings = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        rot_mat = page.rotation_matrix
        
        line_segments = []
        drawings = page.get_drawings()
        
        for d in drawings:
            for item in d.get("items", []):
                shape_type = item[0]
                if shape_type == "l":  # Line
                    p1 = fitz.Point(item[1]) * rot_mat
                    p2 = fitz.Point(item[2]) * rot_mat
                    line_segments.append(((p1.x, p1.y), (p2.x, p2.y)))
                elif shape_type == "re":  # Rectangle
                    r = item[1]
                    r_rot = r * rot_mat
                    edges = [
                        ((r_rot.x0, r_rot.y0), (r_rot.x1, r_rot.y0)),
                        ((r_rot.x1, r_rot.y0), (r_rot.x1, r_rot.y1)),
                        ((r_rot.x1, r_rot.y1), (r_rot.x0, r_rot.y1)),
                        ((r_rot.x0, r_rot.y1), (r_rot.x0, r_rot.y0))
                    ]
                    line_segments.extend(edges)
                elif shape_type == "qu":  # Quad
                    q = item[1]
                    ul = fitz.Point(q.ul) * rot_mat
                    ur = fitz.Point(q.ur) * rot_mat
                    lr = fitz.Point(q.lr) * rot_mat
                    ll = fitz.Point(q.ll) * rot_mat
                    edges = [
                        ((ul.x, ul.y), (ur.x, ur.y)),
                        ((ur.x, ur.y), (lr.x, lr.y)),
                        ((lr.x, lr.y), (ll.x, ll.y)),
                        ((ll.x, ll.y), (ul.x, ul.y))
                    ]
                    line_segments.extend(edges)
                elif shape_type == "c":  # Curve
                    p1 = fitz.Point(item[1]) * rot_mat
                    p2 = fitz.Point(item[2]) * rot_mat
                    p3 = fitz.Point(item[3]) * rot_mat
                    p4 = fitz.Point(item[4]) * rot_mat
                    edges = [
                        ((p1.x, p1.y), (p2.x, p2.y)),
                        ((p2.x, p2.y), (p3.x, p3.y)),
                        ((p3.x, p3.y), (p4.x, p4.y))
                    ]
                    line_segments.extend(edges)
        
        all_pages_drawings.append(line_segments)
        
    doc.close()
    return all_pages_drawings

