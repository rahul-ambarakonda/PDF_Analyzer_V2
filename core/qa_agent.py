# core/qa_agent.py
"""
Code-based drawing analysis. Performs text comparison (using PyMuPDF extracted text)
and visual difference analysis (using OpenCV pixel diffing) to detect drawing mismatches.
"""

import cv2
import numpy as np
from config import (
    TEXT_DISTANCE_TOLERANCE,
    MAX_MISPLACEMENT_SHIFT,
    IMAGE_DIFF_THRESHOLD,
    MIN_DIFF_CONTOUR_AREA
)

class DrawingAlignment:
    def __init__(self, global_M_pdf, global_M_pixel, view_alignments, ref_pdf_size, review_pdf_size, ref_img_shape, review_img_shape):
        self.global_M_pdf = global_M_pdf
        self.global_M_pixel = global_M_pixel
        self.view_alignments = view_alignments  # List of dicts: {"bbox_pdf": (x0, y0, x1, y1), "bbox_pixel": (x0, y0, w, h), "M_pdf": M_pdf, "M_pixel": M_pixel}
        self.ref_pdf_w, self.ref_pdf_h = ref_pdf_size
        self.review_pdf_w, self.review_pdf_h = review_pdf_size
        self.ref_img_h, self.ref_img_w = ref_img_shape[:2]
        self.review_img_h, self.review_img_w = review_img_shape[:2]

    def _find_best_view(self, x, y, is_pdf=True):
        best_view = None
        for val in self.view_alignments:
            if is_pdf:
                vx0, vy0, vx1, vy1 = val["bbox_pdf"]
                # Give a 10pt padding for tolerance
                if vx0 - 10 <= x <= vx1 + 10 and vy0 - 10 <= y <= vy1 + 10:
                    best_view = val
                    break
            else:
                vx0, vy0, vw, vh = val["bbox_pixel"]
                # Give a 20px padding for tolerance
                if vx0 - 20 <= x <= vx0 + vw + 20 and vy0 - 20 <= y <= vy0 + vh + 20:
                    best_view = val
                    break
        
        if best_view is None and self.view_alignments:
            # Fallback to closest view center
            min_dist = float("inf")
            for val in self.view_alignments:
                if is_pdf:
                    vx0, vy0, vx1, vy1 = val["bbox_pdf"]
                    vc_x = (vx0 + vx1) / 2.0
                    vc_y = (vy0 + vy1) / 2.0
                else:
                    vx0, vy0, vw, vh = val["bbox_pixel"]
                    vc_x = vx0 + vw / 2.0
                    vc_y = vy0 + vh / 2.0
                dist = np.sqrt((vc_x - x)**2 + (vc_y - y)**2)
                if dist < min_dist:
                    min_dist = dist
                    best_view = val
        return best_view

    def map_ref_to_review_pdf(self, x, y):
        best_view = self._find_best_view(x, y, is_pdf=True)
        M = best_view["M_pdf"] if best_view is not None else self.global_M_pdf
        if M is None:
            s = self.review_pdf_w / self.ref_pdf_w
            return x * s, y * s
        rx = M[0, 0] * x + M[0, 1] * y + M[0, 2]
        ry = M[1, 0] * x + M[1, 1] * y + M[1, 2]
        return float(rx), float(ry)

    def map_bbox_ref_to_review_pdf(self, bbox):
        x0, y0, x1, y1 = bbox
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        mapped_corners = [self.map_ref_to_review_pdf(cx, cy) for cx, cy in corners]
        xs = [c[0] for c in mapped_corners]
        ys = [c[1] for c in mapped_corners]
        return [min(xs), min(ys), max(xs), max(ys)]

    def map_review_to_ref_pdf(self, x, y):
        # Find which view contains the point in review coordinates
        best_view = None
        for val in self.view_alignments:
            vx0, vy0, vx1, vy1 = val["bbox_pdf"]
            corners = [(vx0, vy0), (vx1, vy0), (vx1, vy1), (vx0, vy1)]
            M = val["M_pdf"]
            if M is not None:
                mapped_corners = []
                for cx, cy in corners:
                    rx = M[0, 0] * cx + M[0, 1] * cy + M[0, 2]
                    ry = M[1, 0] * cx + M[1, 1] * cy + M[1, 2]
                    mapped_corners.append((rx, ry))
                xs = [c[0] for c in mapped_corners]
                ys = [c[1] for c in mapped_corners]
                rx0, ry0, rx1, ry1 = min(xs), min(ys), max(xs), max(ys)
                if rx0 - 10 <= x <= rx1 + 10 and ry0 - 10 <= y <= ry1 + 10:
                    best_view = val
                    break
        
        if best_view is None and self.view_alignments:
            # Fallback to closest mapped view center
            min_dist = float("inf")
            for val in self.view_alignments:
                vx0, vy0, vx1, vy1 = val["bbox_pdf"]
                M = val["M_pdf"]
                if M is not None:
                    vc_x_ref = (vx0 + vx1) / 2.0
                    vc_y_ref = (vy0 + vy1) / 2.0
                    vc_x = M[0, 0] * vc_x_ref + M[0, 1] * vc_y_ref + M[0, 2]
                    vc_y = M[1, 0] * vc_x_ref + M[1, 1] * vc_y_ref + M[1, 2]
                    dist = np.sqrt((vc_x - x)**2 + (vc_y - y)**2)
                    if dist < min_dist:
                        min_dist = dist
                        best_view = val
                        
        M = best_view["M_pdf"] if best_view is not None else self.global_M_pdf
        if M is None:
            s = self.ref_pdf_w / self.review_pdf_w
            return x * s, y * s
            
        try:
            M_inv = cv2.invertAffineTransform(M)
            rx = M_inv[0, 0] * x + M_inv[0, 1] * y + M_inv[0, 2]
            ry = M_inv[1, 0] * x + M_inv[1, 1] * y + M_inv[1, 2]
            return float(rx), float(ry)
        except Exception:
            s = self.ref_pdf_w / self.review_pdf_w
            return x * s, y * s

    def map_bbox_review_to_ref_pdf(self, bbox):
        x0, y0, x1, y1 = bbox
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        mapped_corners = [self.map_review_to_ref_pdf(cx, cy) for cx, cy in corners]
        xs = [c[0] for c in mapped_corners]
        ys = [c[1] for c in mapped_corners]
        return [min(xs), min(ys), max(xs), max(ys)]

def boxes_overlap(b1: list[float], b2: list[float], threshold: float = 0.15) -> bool:
    """Checks if two bounding boxes (x0, y0, x1, y1) overlap significantly."""
    dx = min(b1[2], b2[2]) - max(b1[0], b2[0])
    dy = min(b1[3], b2[3]) - max(b1[1], b2[1])
    if dx > 0 and dy > 0:
        overlap_area = dx * dy
        area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        min_area = min(area1, area2)
        if min_area > 0 and (overlap_area / min_area) > threshold:
            return True
    return False

def check_bbox_overlap_any(bbox: list[float], target_list: list[dict]) -> bool:
    """Helper to check if a bbox overlaps with any bbox in the target_list of issues."""
    for issue in target_list:
        for t_bbox in [issue.get("ref_bbox"), issue.get("review_bbox")]:
            if t_bbox and boxes_overlap(bbox, t_bbox, threshold=0.10):
                return True
    return False

def check_bbox_overlap_exclude_overlap_type(bbox: list[float], target_list: list[dict]) -> bool:
    """Helper to check if a bbox overlaps with missing or misplaced annotations on the review page."""
    for issue in target_list:
        if issue.get("type") in ("MISSING_ANNOTATION", "TEXT_MISPLACEMENT"):
            t_bbox = issue.get("review_bbox")
            if t_bbox and boxes_overlap(bbox, t_bbox, threshold=0.10):
                return True
    return False

def ccw(A, B, C):
    return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

def line_segment_intersect(A, B, C, D):
    return ccw(A,C,D) != ccw(B,C,D) and ccw(A,B,C) != ccw(A,B,D)

def line_intersects_rect(p1, p2, rect):
    rx0, ry0, rx1, ry1 = rect
    x1, y1 = p1
    x2, y2 = p2

    lx0, ly0 = min(x1, x2), min(y1, y2)
    lx1, ly1 = max(x1, x2), max(y1, y2)
    if lx1 < rx0 or lx0 > rx1 or ly1 < ry0 or ly0 > ry1:
        return False

    if rx0 <= x1 <= rx1 and ry0 <= y1 <= ry1:
        return True
    if rx0 <= x2 <= rx1 and ry0 <= y2 <= ry1:
        return True

    edges = [
        ((rx0, ry0), (rx1, ry0)),
        ((rx0, ry1), (rx1, ry1)),
        ((rx0, ry0), (rx0, ry1)),
        ((rx1, ry0), (rx1, ry1))
    ]
    for edge in edges:
        if line_segment_intersect((x1, y1), (x2, y2), edge[0], edge[1]):
            return True

    return False

def compute_alignment(
    ref_cv: np.ndarray,
    review_cv: np.ndarray,
    ref_pdf_size: tuple[float, float],
    review_pdf_size: tuple[float, float],
    ref_text: list[dict],
    review_text: list[dict],
    dpi: int = 300
) -> DrawingAlignment:
    """
    Computes a hybrid local/global alignment mapping Reference page to Creo review page.
    Segments page views, extracts SIFT matches, incorporates exact text matches,
    and estimates RANSAC affine transforms.
    """
    ref_pdf_w, ref_pdf_h = ref_pdf_size
    review_pdf_w, review_pdf_h = review_pdf_size
    img_ref_h, img_ref_w = ref_cv.shape[:2]
    img_rev_h, img_rev_w = review_cv.shape[:2]

    ref_pdf_w_safe = max(1.0, ref_pdf_w)
    ref_pdf_h_safe = max(1.0, ref_pdf_h)
    review_pdf_w_safe = max(1.0, review_pdf_w)
    review_pdf_h_safe = max(1.0, review_pdf_h)

    scale_ref_w = img_ref_w / ref_pdf_w_safe
    scale_ref_h = img_ref_h / ref_pdf_h_safe
    scale_rev_w = img_rev_w / review_pdf_w_safe
    scale_rev_h = img_rev_h / review_pdf_h_safe

    actual_dpi = (img_ref_w / ref_pdf_w_safe) * 72.0
    dpi_scale = actual_dpi / 150.0
    pad = int(3 * dpi_scale)

    # 1. Mask out text blocks to get clean images for SIFT geometry matching
    ref_cv_clean = ref_cv.copy()
    for el in ref_text:
        eb = el["bbox"]
        tx0 = max(0, int(eb[0] * scale_ref_w) - pad)
        ty0 = max(0, int(eb[1] * scale_ref_h) - pad)
        tx1 = min(img_ref_w - 1, int(eb[2] * scale_ref_w) + pad)
        ty1 = min(img_ref_h - 1, int(eb[3] * scale_ref_h) + pad)
        cv2.rectangle(ref_cv_clean, (tx0, ty0), (tx1, ty1), 255, -1)

    rev_cv_clean = review_cv.copy()
    for el in review_text:
        eb = el["bbox"]
        tx0 = max(0, int(eb[0] * scale_rev_w) - pad)
        ty0 = max(0, int(eb[1] * scale_rev_h) - pad)
        tx1 = min(img_rev_w - 1, int(eb[2] * scale_rev_w) + pad)
        ty1 = min(img_rev_h - 1, int(eb[3] * scale_rev_h) + pad)
        cv2.rectangle(rev_cv_clean, (tx0, ty0), (tx1, ty1), 255, -1)

    # 2. Compute dense SIFT matches between the clean images
    sift = cv2.SIFT_create(nfeatures=20000)
    kp1, des1 = sift.detectAndCompute(ref_cv_clean, None)
    kp2, des2 = sift.detectAndCompute(rev_cv_clean, None)

    good_matches = []
    if des1 is not None and des2 is not None:
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        flann = cv2.FlannBasedMatcher(index_params, search_params)
        try:
            matches = flann.knnMatch(des1, des2, k=2)
            for m, n in matches:
                if m.distance < 0.85 * n.distance:
                    good_matches.append(m)
        except Exception:
            pass

    all_matches_pdf = []
    all_matches_px = []
    for m in good_matches:
        p_ref = kp1[m.queryIdx].pt
        p_rev = kp2[m.trainIdx].pt
        pt_ref_pdf = (p_ref[0] / scale_ref_w, p_ref[1] / scale_ref_h)
        pt_rev_pdf = (p_rev[0] / scale_rev_w, p_rev[1] / scale_rev_h)
        all_matches_pdf.append((pt_ref_pdf, pt_rev_pdf))
        all_matches_px.append((p_ref, p_rev))

    # Estimate preliminary global transform
    global_M_pdf = None
    global_M_pixel = None
    if len(all_matches_pdf) >= 3:
        src_pdf = np.float32([m[0] for m in all_matches_pdf]).reshape(-1, 1, 2)
        dst_pdf = np.float32([m[1] for m in all_matches_pdf]).reshape(-1, 1, 2)
        global_M_pdf, _ = cv2.estimateAffinePartial2D(src_pdf, dst_pdf, method=cv2.RANSAC, ransacReprojThreshold=10.0)

        src_px = np.float32([m[0] for m in all_matches_px]).reshape(-1, 1, 2)
        dst_px = np.float32([m[1] for m in all_matches_px]).reshape(-1, 1, 2)
        global_M_pixel, _ = cv2.estimateAffinePartial2D(src_px, dst_px, method=cv2.RANSAC, ransacReprojThreshold=10.0)

    s_pdf_fallback = review_pdf_w / ref_pdf_w_safe
    s_px_fallback = img_rev_w / img_ref_w
    if global_M_pdf is None:
        global_M_pdf = np.array([[s_pdf_fallback, 0.0, 0.0], [0.0, s_pdf_fallback, 0.0]], dtype=np.float32)
    if global_M_pixel is None:
        global_M_pixel = np.array([[s_px_fallback, 0.0, 0.0], [0.0, s_px_fallback, 0.0]], dtype=np.float32)

    # 3. If ref_text is empty but review_text is not, map review text back to ref_cv_clean
    if not ref_text and review_text:
        try:
            M_inv = cv2.invertAffineTransform(global_M_pixel)
        except Exception:
            s_inv = img_ref_w / img_rev_w
            M_inv = np.array([[s_inv, 0.0, 0.0], [0.0, s_inv, 0.0]], dtype=np.float32)

        for el in review_text:
            eb = el["bbox"]
            rx0 = eb[0] * scale_rev_w
            ry0 = eb[1] * scale_rev_h
            rx1 = eb[2] * scale_rev_w
            ry1 = eb[3] * scale_rev_h

            corners = [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)]
            mapped_corners = []
            for cx, cy in corners:
                mc_x = M_inv[0, 0] * cx + M_inv[0, 1] * cy + M_inv[0, 2]
                mc_y = M_inv[1, 0] * cx + M_inv[1, 1] * cy + M_inv[1, 2]
                mapped_corners.append((mc_x, mc_y))

            xs = [c[0] for c in mapped_corners]
            ys = [c[1] for c in mapped_corners]
            tx0 = max(0, int(min(xs)) - pad)
            ty0 = max(0, int(min(ys)) - pad)
            tx1 = min(img_ref_w - 1, int(max(xs)) + pad)
            ty1 = min(img_ref_h - 1, int(max(ys)) + pad)
            cv2.rectangle(ref_cv_clean, (tx0, ty0), (tx1, ty1), 255, -1)

        # Recompute SIFT on updated ref_cv_clean
        kp1, des1 = sift.detectAndCompute(ref_cv_clean, None)
        good_matches = []
        if des1 is not None and des2 is not None:
            try:
                matches = flann.knnMatch(des1, des2, k=2)
                for m, n in matches:
                    if m.distance < 0.85 * n.distance:
                        good_matches.append(m)
            except Exception:
                pass

        all_matches_pdf = []
        all_matches_px = []
        for m in good_matches:
            p_ref = kp1[m.queryIdx].pt
            p_rev = kp2[m.trainIdx].pt
            pt_ref_pdf = (p_ref[0] / scale_ref_w, p_ref[1] / scale_ref_h)
            pt_rev_pdf = (p_rev[0] / scale_rev_w, p_rev[1] / scale_rev_h)
            all_matches_pdf.append((pt_ref_pdf, pt_rev_pdf))
            all_matches_px.append((p_ref, p_rev))

        if len(all_matches_pdf) >= 3:
            src_pdf = np.float32([m[0] for m in all_matches_pdf]).reshape(-1, 1, 2)
            dst_pdf = np.float32([m[1] for m in all_matches_pdf]).reshape(-1, 1, 2)
            global_M_pdf, _ = cv2.estimateAffinePartial2D(src_pdf, dst_pdf, method=cv2.RANSAC, ransacReprojThreshold=10.0)

            src_px = np.float32([m[0] for m in all_matches_px]).reshape(-1, 1, 2)
            dst_px = np.float32([m[1] for m in all_matches_px]).reshape(-1, 1, 2)
            global_M_pixel, _ = cv2.estimateAffinePartial2D(src_px, dst_px, method=cv2.RANSAC, ransacReprojThreshold=10.0)

        if global_M_pdf is None:
            global_M_pdf = np.array([[s_pdf_fallback, 0.0, 0.0], [0.0, s_pdf_fallback, 0.0]], dtype=np.float32)
        if global_M_pixel is None:
            global_M_pixel = np.array([[s_px_fallback, 0.0, 0.0], [0.0, s_px_fallback, 0.0]], dtype=np.float32)

    # 4. Extract unique exact-matching text element centers (if both text collections exist)
    ref_counts = {}
    for el in ref_text:
        ref_counts[el["text"]] = ref_counts.get(el["text"], 0) + 1

    review_counts = {}
    for el in review_text:
        review_counts[el["text"]] = review_counts.get(el["text"], 0) + 1

    text_matches_pdf = []
    text_matches_px = []
    for el_ref in ref_text:
        text = el_ref["text"]
        if text and ref_counts[text] == 1 and review_counts.get(text, 0) == 1:
            el_rev = next(el for el in review_text if el["text"] == text)
            ref_bbox = el_ref["bbox"]
            rev_bbox = el_rev["bbox"]
            ref_center_pdf = ((ref_bbox[0] + ref_bbox[2]) / 2.0, (ref_bbox[1] + ref_bbox[3]) / 2.0)
            rev_center_pdf = ((rev_bbox[0] + rev_bbox[2]) / 2.0, (rev_bbox[1] + rev_bbox[3]) / 2.0)
            text_matches_pdf.append((ref_center_pdf, rev_center_pdf))

            ref_center_px = (ref_center_pdf[0] * scale_ref_w, ref_center_pdf[1] * scale_ref_h)
            rev_center_px = (rev_center_pdf[0] * scale_rev_w, rev_center_pdf[1] * scale_rev_h)
            text_matches_px.append((ref_center_px, rev_center_px))

    # Append unique text matches to matching pool
    all_matches_pdf.extend(text_matches_pdf)
    all_matches_px.extend(text_matches_px)

    # 5. Segment Reference clean image into drawing views using a larger dilation kernel
    _, thresh = cv2.threshold(ref_cv_clean, 240, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    border_rect = None
    max_area = 0
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w > 0.8 * img_ref_w and h > 0.8 * img_ref_h:
            if w * h > max_area:
                max_area = w * h
                border_rect = (x, y, w, h)

    clean_thresh = thresh.copy()
    margin = int(70 * dpi_scale)
    if border_rect:
        bx, by, bw, bh = border_rect
        mask = np.zeros_like(thresh)
        mx0 = min(bx + margin, img_ref_w - 1)
        my0 = min(by + margin, img_ref_h - 1)
        mx1 = max(bx + bw - margin, 0)
        my1 = max(by + bh - margin, 0)
        if mx1 > mx0 and my1 > my0:
            cv2.rectangle(mask, (mx0, my0), (mx1, my1), 255, -1)
            clean_thresh = cv2.bitwise_and(thresh, mask)

    kernel_size = max(10, int(80 * dpi_scale))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    dilated = cv2.dilate(clean_thresh, kernel, iterations=1)
    inner_contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    ref_views_px = []
    for c in inner_contours:
        if cv2.contourArea(c) > 0.005 * (img_ref_h * img_ref_w): # Require 0.5% of page area
            ref_views_px.append(cv2.boundingRect(c))

    # 6. For each segmented view, compute local alignment using SIFT geometry matches
    view_alignments = []
    for rx, ry, rw, rh in ref_views_px:
        vx0 = rx / scale_ref_w
        vy0 = ry / scale_ref_h
        vx1 = (rx + rw) / scale_ref_w
        vy1 = (ry + rh) / scale_ref_h

        local_src_pdf = []
        local_dst_pdf = []
        local_src_px = []
        local_dst_px = []

        for m_pdf, m_px in zip(all_matches_pdf, all_matches_px):
            pt_ref_pdf = m_pdf[0]
            if vx0 <= pt_ref_pdf[0] <= vx1 and vy0 <= pt_ref_pdf[1] <= vy1:
                local_src_pdf.append(m_pdf[0])
                local_dst_pdf.append(m_pdf[1])
                local_src_px.append(m_px[0])
                local_dst_px.append(m_px[1])

        local_M_pdf = None
        local_M_pixel = None

        if len(local_src_pdf) >= 3:
            src_arr_pdf = np.float32(local_src_pdf).reshape(-1, 1, 2)
            dst_arr_pdf = np.float32(local_dst_pdf).reshape(-1, 1, 2)
            local_M_pdf, inliers = cv2.estimateAffinePartial2D(src_arr_pdf, dst_arr_pdf, method=cv2.RANSAC, ransacReprojThreshold=5.0)
            if local_M_pdf is not None and np.sum(inliers) < 3:
                local_M_pdf = None

            src_arr_px = np.float32(local_src_px).reshape(-1, 1, 2)
            dst_arr_px = np.float32(local_dst_px).reshape(-1, 1, 2)
            local_M_pixel, inliers_px = cv2.estimateAffinePartial2D(src_arr_px, dst_arr_px, method=cv2.RANSAC, ransacReprojThreshold=5.0)
            if local_M_pixel is not None and np.sum(inliers_px) < 3:
                local_M_pixel = None

        # Sanity check: if local scale is degenerate (e.g. 0.0) or deviates too much from global, fall back to global
        global_scale = np.sqrt(global_M_pixel[0, 0]**2 + global_M_pixel[0, 1]**2)

        is_degenerate_pdf = True
        if local_M_pdf is not None:
            s_pdf = np.sqrt(local_M_pdf[0, 0]**2 + local_M_pdf[0, 1]**2)
            if 0.5 * global_scale <= s_pdf <= 2.0 * global_scale:
                is_degenerate_pdf = False

        if is_degenerate_pdf:
            local_M_pdf = global_M_pdf

        is_degenerate_px = True
        if local_M_pixel is not None:
            s_px = np.sqrt(local_M_pixel[0, 0]**2 + local_M_pixel[0, 1]**2)
            if 0.5 * global_scale <= s_px <= 2.0 * global_scale:
                is_degenerate_px = False

        if is_degenerate_px:
            local_M_pixel = global_M_pixel

        view_alignments.append({
            "bbox_pdf": (vx0, vy0, vx1, vy1),
            "bbox_pixel": (rx, ry, rw, rh),
            "M_pdf": local_M_pdf,
            "M_pixel": local_M_pixel
        })

    return DrawingAlignment(
        global_M_pdf, global_M_pixel, view_alignments,
        ref_pdf_size, review_pdf_size, ref_cv.shape, review_cv.shape
    )

def compare_text_elements(
    ref_elements: list[dict],
    review_elements: list[dict],
    ref_pdf_size: tuple[float, float],
    alignment: DrawingAlignment,
    review_drawings: list = None
) -> list[dict]:
    """
    Compares text annotations from Reference and Creo review drawing pages.
    Identifies:
    - MISSING_ANNOTATION: exist in Reference, missing in Creo.
    - TEXT_MISPLACEMENT: exist in both but coordinates shifted > TEXT_DISTANCE_TOLERANCE.
    - TEXT_OVERLAP: check if Creo text blocks collide with each other or with drawing geometry.

    Font differences are ignored.
    """
    issues = []
    matched_review_indices = set()
    ref_w, ref_h = ref_pdf_size

    # 1. Match reference elements to closest matching text in Creo
    for ref in ref_elements:
        ref_text = ref["text"]
        ref_bbox = ref["bbox"]
        ref_center = ((ref_bbox[0] + ref_bbox[2]) / 2.0, (ref_bbox[1] + ref_bbox[3]) / 2.0)
        
        # Align reference center using local/global transform
        aligned_ref_center = alignment.map_ref_to_review_pdf(ref_center[0], ref_center[1])

        best_dist = float("inf")
        best_rev_idx = -1

        for rev_idx, rev in enumerate(review_elements):
            if rev_idx in matched_review_indices:
                continue

            if rev["text"] == ref_text:
                rev_bbox = rev["bbox"]
                rev_center = ((rev_bbox[0] + rev_bbox[2]) / 2.0, (rev_bbox[1] + rev_bbox[3]) / 2.0)
                dist = ((aligned_ref_center[0] - rev_center[0])**2 + (aligned_ref_center[1] - rev_center[1])**2)**0.5
                if dist < best_dist:
                    best_dist = dist
                    best_rev_idx = rev_idx

        if best_rev_idx != -1 and best_dist < MAX_MISPLACEMENT_SHIFT:
            matched_review_indices.add(best_rev_idx)
            rev_el = review_elements[best_rev_idx]
            
            if best_dist > TEXT_DISTANCE_TOLERANCE:
                issues.append({
                    "type": "TEXT_MISPLACEMENT",
                    "severity": "MEDIUM",
                    "location": f"Near coordinates ({int(ref_center[0])}, {int(ref_center[1])})",
                    "description": f"Text label '{ref_text}' has shifted by {best_dist:.1f} points.",
                    "reference_has": f"'{ref_text}' at { [round(v, 1) for v in ref_bbox] }",
                    "creo_shows": f"'{ref_text}' at { [round(v, 1) for v in rev_el['bbox']] }",
                    "ref_bbox": ref_bbox,
                    "review_bbox": rev_el["bbox"]
                })
        else:
            # Missing in Creo
            issues.append({
                "type": "MISSING_ANNOTATION",
                "severity": "HIGH",
                "location": f"Near coordinates ({int(ref_center[0])}, {int(ref_center[1])})",
                "description": f"Annotation '{ref_text}' is missing in Creo drawing.",
                "reference_has": f"'{ref_text}'",
                "creo_shows": "Missing",
                "ref_bbox": ref_bbox,
                "review_bbox": alignment.map_bbox_ref_to_review_pdf(ref_bbox)
            })

    # 2. Check for overlapping annotations in Creo elements (text-to-text)
    for i, rev1 in enumerate(review_elements):
        b1 = rev1["bbox"]
        for j, rev2 in enumerate(review_elements):
            if i >= j:
                continue
            b2 = rev2["bbox"]

            if boxes_overlap(b1, b2, threshold=0.15):
                center = ((b1[0] + b1[2]) / 2.0, (b1[1] + b1[3]) / 2.0)
                issues.append({
                    "type": "TEXT_OVERLAP",
                    "severity": "HIGH",
                    "location": f"Near coordinates ({int(center[0])}, {int(center[1])})",
                    "description": f"Overlap detected between '{rev1['text']}' and '{rev2['text']}' in Creo.",
                    "reference_has": "Separate, legible labels",
                    "creo_shows": f"Overlapping labels '{rev1['text']}' and '{rev2['text']}'",
                    "ref_bbox": None,
                    "review_bbox": [min(b1[0], b2[0]), min(b1[1], b2[1]), max(b1[2], b2[2]), max(b1[3], b2[3])]
                })

    # 3. Check for text-to-geometry overlaps
    if review_drawings:
        grid_size = 100.0
        grid = {}

        def get_grid_cells(bbox):
            gx0, gy0, gx1, gy1 = bbox
            col_start = int(max(0, gx0) // grid_size)
            col_end = int(max(0, gx1) // grid_size)
            row_start = int(max(0, gy0) // grid_size)
            row_end = int(max(0, gy1) // grid_size)
            
            cells = []
            for r in range(row_start, row_end + 1):
                for c in range(col_start, col_end + 1):
                    cells.append((r, c))
            return cells

        for p1, p2 in review_drawings:
            lx0, ly0 = min(p1[0], p2[0]), min(p1[1], p2[1])
            lx1, ly1 = max(p1[0], p2[0]), max(p1[1], p2[1])
            
            cells = get_grid_cells((lx0, ly0, lx1, ly1))
            for cell in cells:
                if cell not in grid:
                    grid[cell] = []
                grid[cell].append((p1, p2))

        padding = 2.0
        for rev in review_elements:
            b = rev["bbox"]
            if (b[2] - b[0] > 2 * padding) and (b[3] - b[1] > 2 * padding):
                shrunk_b = [b[0] + padding, b[1] + padding, b[2] - padding, b[3] - padding]
            else:
                shrunk_b = list(b)

            span_cells = get_grid_cells(shrunk_b)
            
            candidate_lines = set()
            for cell in span_cells:
                if cell in grid:
                    candidate_lines.update(grid[cell])
                    
            intersected = False
            for p1, p2 in candidate_lines:
                if line_intersects_rect(p1, p2, shrunk_b):
                    intersected = True
                    break
                    
            if intersected:
                if check_bbox_overlap_any(list(b), issues):
                    continue
                    
                center = ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
                issues.append({
                    "type": "TEXT_OVERLAP",
                    "severity": "MEDIUM",
                    "location": f"Near coordinates ({int(center[0])}, {int(center[1])})",
                    "description": f"Dimension or text block '{rev['text']}' overlaps with drawing lines/geometry.",
                    "reference_has": "Clear label/dimension spacing",
                    "creo_shows": f"Overlap between text '{rev['text']}' and drawing vector geometry",
                    "ref_bbox": None,
                    "review_bbox": list(b)
                })

    return issues

def detect_geometric_differences(
    ref_cv: np.ndarray,
    review_cv: np.ndarray,
    ref_pdf_size: tuple[float, float],
    review_pdf_size: tuple[float, float],
    text_issues: list[dict],
    alignment: DrawingAlignment,
    review_text_elements: list[dict] = None
) -> list[dict]:
    """
    Warps the Reference image view-by-view using Voronoi distance transform partitioning
    to align with the Review image, calculates pixel differences, applies outer border
    masking, and filters discrepancy contours using a dual-threshold filter based on
    proximity to selectable text regions.
    """
    img_ref_h, img_ref_w = ref_cv.shape[:2]
    img_rev_h, img_rev_w = review_cv.shape[:2]
    review_pdf_w, review_pdf_h = review_pdf_size

    # 1. Warp ref_cv to review_cv size using Voronoi distance transform partitioning
    dist_maps = []
    for val in alignment.view_alignments:
        vx0, vy0, vw, vh = val["bbox_pixel"]
        mask = np.full_like(ref_cv, 255)
        cv2.rectangle(mask, (vx0, vy0), (vx0 + vw, vy0 + vh), 0, -1)
        dist = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
        dist_maps.append(dist)
        
    if dist_maps:
        stacked = np.stack(dist_maps, axis=2)
        closest_view = np.argmin(stacked, axis=2)
        
        warped_ref = np.full((img_rev_h, img_rev_w), 255, dtype=np.uint8)
        for idx, val in enumerate(alignment.view_alignments):
            local_M_pixel = val["M_pixel"]
            ref_mask = ((closest_view == idx) * 255).astype(np.uint8)
            
            warped_view = cv2.warpAffine(ref_cv, local_M_pixel, (img_rev_w, img_rev_h), borderValue=255)
            warped_mask = cv2.warpAffine(ref_mask, local_M_pixel, (img_rev_w, img_rev_h), borderValue=0)
            warped_ref[warped_mask > 127] = warped_view[warped_mask > 127]
    else:
        warped_ref = cv2.warpAffine(ref_cv, alignment.global_M_pixel, (img_rev_w, img_rev_h), borderValue=255)

    # 2. Calculate tolerance-based difference
    actual_dpi = (img_rev_w / max(1.0, review_pdf_w)) * 72.0
    dpi_scale = actual_dpi / 150.0
    
    # Moderate morphological tolerance D=2 at 300 DPI to avoid erasures
    D = max(1, int(1.0 * dpi_scale))
    
    kernel_tol = cv2.getStructuringElement(cv2.MORPH_RECT, (2*D + 1, 2*D + 1))
    
    # Erode the grayscale images (making black lines thicker, since background is white 255)
    ref_thick = cv2.erode(warped_ref, kernel_tol)
    review_thick = cv2.erode(review_cv, kernel_tol)
    
    # Find pixels that are black in review but white in ref_thick (added geometries/chars)
    mismatch_rev = (review_cv < 200) & (ref_thick > 200)
    # Find pixels that are black in warped_ref but white in review_thick (missing geometries/chars)
    mismatch_ref = (warped_ref < 200) & (review_thick > 200)
    
    thresh = (mismatch_rev | mismatch_ref).astype(np.uint8) * 255
    
    # 3. Outer Border Masking (to eliminate page edges and margin discrepancies)
    _, thresh_rev = cv2.threshold(review_cv, 240, 255, cv2.THRESH_BINARY_INV)
    contours_rev, _ = cv2.findContours(thresh_rev, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    border_rect_rev = None
    max_area_rev = 0
    for c in contours_rev:
        x, y, w, h = cv2.boundingRect(c)
        if w > 0.8 * img_rev_w and h > 0.8 * img_rev_h:
            if w * h > max_area_rev:
                max_area_rev = w * h
                border_rect_rev = (x, y, w, h)

    _, thresh_warped = cv2.threshold(warped_ref, 240, 255, cv2.THRESH_BINARY_INV)
    contours_warped, _ = cv2.findContours(thresh_warped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    border_rect_warped = None
    max_area_warped = 0
    for c in contours_warped:
        x, y, w, h = cv2.boundingRect(c)
        if w > 0.8 * img_rev_w and h > 0.8 * img_rev_h:
            if w * h > max_area_warped:
                max_area_warped = w * h
                border_rect_warped = (x, y, w, h)

    border_mask = np.ones_like(review_cv) * 255
    if border_rect_rev is not None and border_rect_warped is not None:
        rx0 = max(border_rect_rev[0], border_rect_warped[0])
        ry0 = max(border_rect_rev[1], border_rect_warped[1])
        rx1 = min(border_rect_rev[0] + border_rect_rev[2], border_rect_warped[0] + border_rect_warped[2])
        ry1 = min(border_rect_rev[1] + border_rect_rev[3], border_rect_warped[1] + border_rect_warped[3])
        
        border_margin = int(15 * dpi_scale)
        border_mask = np.zeros_like(review_cv)
        if rx1 - border_margin > rx0 + border_margin and ry1 - border_margin > ry0 + border_margin:
            cv2.rectangle(border_mask, (rx0 + border_margin, ry0 + border_margin), (rx1 - border_margin, ry1 - border_margin), 255, -1)

    thresh = cv2.bitwise_and(thresh, border_mask)
    
    # Filter out single-pixel noise using morphological opening
    kernel_noise = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_noise)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 4. Construct a binary text mask in Review coordinates for dual-thresholding
    text_region_mask = np.zeros_like(review_cv)
    if review_text_elements:
        text_pad = int(5 * dpi_scale)
        for el in review_text_elements:
            eb = el["bbox"]
            tx0 = max(0, int(eb[0] * (img_rev_w / review_pdf_w)) - text_pad)
            ty0 = max(0, int(eb[1] * (img_rev_h / review_pdf_h)) - text_pad)
            tx1 = min(img_rev_w - 1, int(eb[2] * (img_rev_w / review_pdf_w)) + text_pad)
            ty1 = min(img_rev_h - 1, int(eb[3] * (img_rev_h / review_pdf_h)) + text_pad)
            cv2.rectangle(text_region_mask, (tx0, ty0), (tx1, ty1), 255, -1)

    raw_geo_issues = []

    for c in contours:
        area = cv2.contourArea(c)
        px0, py0, w, h = cv2.boundingRect(c)
        px1, py1 = px0 + w, py0 + h

        # Check if the contour intersects with text_region_mask
        sub_mask = text_region_mask[py0:py1, px0:px1]
        is_text = np.any(sub_mask > 0)
        
        limit = 3 if is_text else MIN_DIFF_CONTOUR_AREA
        if area < limit:
            continue

        # Convert to review PDF points
        rx0 = px0 * (review_pdf_w / img_rev_w)
        ry0 = py0 * (review_pdf_h / img_rev_h)
        rx1 = px1 * (review_pdf_w / img_rev_w)
        ry1 = py1 * (review_pdf_h / img_rev_h)

        bbox_points = [rx0, ry0, rx1, ry1]

        # Filter out if it overlaps with MISSING_ANNOTATION or TEXT_MISPLACEMENT
        if check_bbox_overlap_exclude_overlap_type(bbox_points, text_issues):
            continue

        center_x = (rx0 + rx1) / 2.0
        center_y = (ry0 + ry1) / 2.0

        raw_geo_issues.append({
            "type": "GEOMETRIC_DIFFERENCE",
            "severity": "HIGH",
            "location": f"Near coordinates ({int(center_x)}, {int(center_y)})",
            "description": f"Visual discrepancy detected in drawing geometry or annotations (area: {int(area)}px).",
            "reference_has": "Reference geometry",
            "creo_shows": "Creo geometry discrepancy",
            "ref_bbox": alignment.map_bbox_review_to_ref_pdf(bbox_points),
            "review_bbox": bbox_points
        })

    # 5. Coalesce numerous minor geometric differences inside views or globally
    view_diffs = {idx: [] for idx in range(len(alignment.view_alignments))}
    outside_diffs = []
    
    for issue in raw_geo_issues:
        review_bbox = issue["review_bbox"]
        cx = (review_bbox[0] + review_bbox[2]) / 2.0
        cy = (review_bbox[1] + review_bbox[3]) / 2.0
        
        best_view_idx = -1
        for idx, val in enumerate(alignment.view_alignments):
            vx0, vy0, vx1, vy1 = val["bbox_pdf"]
            corners = [(vx0, vy0), (vx1, vy0), (vx1, vy1), (vx0, vy1)]
            M = val["M_pdf"] if val["M_pdf"] is not None else alignment.global_M_pdf
            if M is not None:
                mapped_corners = []
                for cx_ref, cy_ref in corners:
                    rx = M[0, 0] * cx_ref + M[0, 1] * cy_ref + M[0, 2]
                    ry = M[1, 0] * cx_ref + M[1, 1] * cy_ref + M[1, 2]
                    mapped_corners.append((rx, ry))
                xs = [c[0] for c in mapped_corners]
                ys = [c[1] for c in mapped_corners]
                rx0, ry0, rx1, ry1 = min(xs), min(ys), max(xs), max(ys)
                if rx0 - 5 <= cx <= rx1 + 5 and ry0 - 5 <= cy <= ry1 + 5:
                    best_view_idx = idx
                    break
                    
        if best_view_idx != -1:
            view_diffs[best_view_idx].append(issue)
        else:
            outside_diffs.append(issue)
            
    final_geo_issues = []
    for idx, issues_in_view in view_diffs.items():
        if len(issues_in_view) > 15:
            # Coalesce into a single drawing view mismatch issue
            xs = []
            ys = []
            total_area = 0
            for iss in issues_in_view:
                import re
                match = re.search(r'area:\s*(\d+)px', iss["description"])
                area_val = int(match.group(1)) if match else 10
                total_area += area_val
                
                rb = iss["review_bbox"]
                xs.extend([rb[0], rb[2]])
                ys.extend([rb[1], rb[3]])
                
            rx0, ry0, rx1, ry1 = min(xs), min(ys), max(xs), max(ys)
            
            val = alignment.view_alignments[idx]
            final_geo_issues.append({
                "type": "GEOMETRIC_DIFFERENCE",
                "severity": "MEDIUM",
                "location": f"Drawing View {idx+1}",
                "description": f"CAD platform rendering style/projection variations detected in View {idx+1} (coalesced {len(issues_in_view)} cosmetic differences, total area: {total_area}px).",
                "reference_has": "Reference drawing geometry/projection",
                "creo_shows": "Creo drawing geometry/projection with cosmetic line variations",
                "ref_bbox": val["bbox_pdf"],
                "review_bbox": [rx0, ry0, rx1, ry1]
            })
        else:
            final_geo_issues.extend(issues_in_view)
            
    if len(outside_diffs) > 30:
        xs = []
        ys = []
        total_area = 0
        for iss in outside_diffs:
            rb = iss["review_bbox"]
            xs.extend([rb[0], rb[2]])
            ys.extend([rb[1], rb[3]])
            import re
            match = re.search(r'area:\s*(\d+)px', iss["description"])
            total_area += int(match.group(1)) if match else 10
            
        rx0, ry0, rx1, ry1 = min(xs), min(ys), max(xs), max(ys)
        final_geo_issues.append({
            "type": "GEOMETRIC_DIFFERENCE",
            "severity": "LOW",
            "location": "Global Sheet",
            "description": f"Systemic visual style/border variations detected across sheet frame (coalesced {len(outside_diffs)} cosmetic differences, total area: {total_area}px). Likely due to template or title borders.",
            "reference_has": "Reference sheet border",
            "creo_shows": "Creo sheet border variations",
            "ref_bbox": None,
            "review_bbox": [rx0, ry0, rx1, ry1]
        })
    else:
        final_geo_issues.extend(outside_diffs)

    return final_geo_issues

CATEGORIES_LIST = [
    "Drawing Layout",
    "Views & Geometry",
    "Dimensions & Tolerances",
    "Notes & Annotations",
    "Title Block",
    "Revision History",
    "BOM / Tables",
    "Symbols & Standards",
    "Styling & Layers",
    "Scale & Proportion",
    "Visual Quality",
    "Conversion Integrity",
    "Compliance Rules"
]

def classify_issue(issue: dict, page_w: float, page_h: float) -> str:
    category = "Visual Quality"  # default
    issue_type = issue.get("type")
    
    # Extract bounding box to inspect location
    bbox = issue.get("review_bbox") or issue.get("ref_bbox")
    bbox_x0, bbox_y0, bbox_x1, bbox_y1 = 0.0, 0.0, 0.0, 0.0
    if bbox:
        bbox_x0, bbox_y0, bbox_x1, bbox_y1 = bbox[0], bbox[1], bbox[2], bbox[3]
    
    # Normalize coordinates
    norm_x0 = bbox_x0 / max(1.0, page_w)
    norm_y0 = bbox_y0 / max(1.0, page_h)
    norm_x1 = bbox_x1 / max(1.0, page_w)
    norm_y1 = bbox_y1 / max(1.0, page_h)
    
    description = issue.get("description", "").upper()
    ref_has = issue.get("reference_has", "").upper()
    creo_shows = issue.get("creo_shows", "").upper()
    combined_text = f"{description} {ref_has} {creo_shows}"

    if issue_type == "LAYOUT_MISMATCH":
        return "Drawing Layout"
    if issue_type == "SCALE_DISCREPANCY":
        return "Scale & Proportion"

    if issue_type == "GEOMETRIC_DIFFERENCE":
        if "CONVERSION" in combined_text or "INTEGRITY" in combined_text:
            return "Conversion Integrity"
        return "Views & Geometry"

    if issue_type == "TEXT_OVERLAP":
        return "Visual Quality"

    if issue_type in ("MISSING_ANNOTATION", "TEXT_MISPLACEMENT"):
        # 1. Revision History Area (typically top-right corner)
        if norm_x0 > 0.7 and norm_y1 < 0.35:
            if any(k in combined_text for k in ["REV", "REVISION", "ZONE", "DATE", "HISTORY"]):
                return "Revision History"

        # 2. Title Block Area (typically bottom-right corner)
        if norm_x0 > 0.65 and norm_y0 > 0.65:
            title_block_keywords = ["MATERIAL", "WEIGHT", "SCALE", "UNIT", "DRAWN", "CHECKED", "APPROVED", "FINISH", "COATING", "PART NO", "ASSY", "SIZE", "TITLE"]
            if any(kw in combined_text for kw in title_block_keywords):
                return "Title Block"

        # 3. BOM / Tables Area (typically on the right side)
        if norm_x0 > 0.6 or "BOM" in combined_text or "TABLE" in combined_text:
            bom_keywords = ["QTY", "PART NUMBER", "DESCRIPTION", "ITEM", "FERRULE", "HOSE", "WELDED PIPE", "ACTUATOR", "LIST"]
            if any(kw in combined_text for kw in bom_keywords):
                return "BOM / Tables"

        # 4. Dimensions & Tolerances (numeric values, fractions, ±, degree, diameter, mm/inch)
        import re
        dim_pattern = re.compile(r'(\d+/\d+|\d+\.\d+|\b\d+\b|±|ø|DIA|MM|INCH|DEG|RAD|°|UNITS)')
        if dim_pattern.search(combined_text) or "DIMENSION" in combined_text or "TOLERANCE" in combined_text:
            return "Dimensions & Tolerances"

        # 5. Notes & Annotations
        if "NOTE" in combined_text or "BALLOON" in combined_text or "CALLOUT" in combined_text:
            return "Notes & Annotations"
        
        # Check if it has mostly alphabetical words
        alphabetic_words = len([w for w in combined_text.split() if w.isalpha()])
        if alphabetic_words > 1:
            return "Notes & Annotations"

    return category

def analyze_page(
    ref_img_bytes: bytes,
    review_img_bytes: bytes,
    ref_text_elements: list[dict],
    review_text_elements: list[dict],
    ref_pdf_size: tuple[float, float],
    review_pdf_size: tuple[float, float],
    page_num: int,
    review_drawings: list = None,
    dpi: int = 300
) -> dict:
    """
    Analyzes a page by running text comparisons followed by visual difference analysis.
    Classifies all results according to the 13-category engineering QA audit framework.
    """
    # Grayscale decodes
    ref_arr = np.frombuffer(ref_img_bytes, np.uint8)
    ref_cv = cv2.imdecode(ref_arr, cv2.IMREAD_GRAYSCALE)

    review_arr = np.frombuffer(review_img_bytes, np.uint8)
    review_cv = cv2.imdecode(review_arr, cv2.IMREAD_GRAYSCALE)

    # 1. Compute alignment mappings
    alignment = compute_alignment(
        ref_cv, review_cv, ref_pdf_size, review_pdf_size,
        ref_text_elements, review_text_elements, dpi=dpi
    )

    # 2. Analyze text issues
    text_issues = compare_text_elements(
        ref_text_elements,
        review_text_elements,
        ref_pdf_size,
        alignment,
        review_drawings=review_drawings
    )

    # 3. Analyze visual differences (passing review_text_elements for dual thresholding)
    geo_issues = detect_geometric_differences(
        ref_cv, review_cv, ref_pdf_size, review_pdf_size, text_issues, alignment,
        review_text_elements=review_text_elements
    )

    all_issues = text_issues + geo_issues

    # 4. Integrate Drawing Layout and Scale Proportion checks
    ref_w, ref_h = ref_pdf_size
    rev_w, rev_h = review_pdf_size
    
    # Page size layout mismatch check
    if abs(ref_w - rev_w) > 0.05 * ref_w or abs(ref_h - rev_h) > 0.05 * ref_h:
        all_issues.append({
            "type": "LAYOUT_MISMATCH",
            "severity": "HIGH",
            "location": "Page Dimensions",
            "description": f"Page size mismatch: Reference is {ref_w:.1f}x{ref_h:.1f} pts, Creo is {rev_w:.1f}x{rev_h:.1f} pts.",
            "reference_has": f"{ref_w:.1f}x{ref_h:.1f}",
            "creo_shows": f"{rev_w:.1f}x{rev_h:.1f}",
            "ref_bbox": None,
            "review_bbox": None
        })

    # Scale proportion consistency check
    for idx, val in enumerate(alignment.view_alignments):
        local_M = val["M_pixel"]
        if local_M is not None:
            local_scale = np.sqrt(local_M[0, 0]**2 + local_M[0, 1]**2)
            global_scale = np.sqrt(alignment.global_M_pixel[0, 0]**2 + alignment.global_M_pixel[0, 1]**2)
            if abs(local_scale - global_scale) > 0.05 * global_scale:
                all_issues.append({
                    "type": "SCALE_DISCREPANCY",
                    "severity": "MEDIUM",
                    "location": f"Drawing View {idx+1}",
                    "description": f"Drawing view {idx+1} scale differs from global sheet scale by {abs(local_scale - global_scale)/global_scale*100:.1f}%.",
                    "reference_has": f"Scale {global_scale:.3f}",
                    "creo_shows": f"Scale {local_scale:.3f}",
                    "ref_bbox": None,
                    "review_bbox": list(val["bbox_pdf"])
                })

    # 5. Classify all issues into the 13 categories and compile the audits report
    categories_map = {name: [] for name in CATEGORIES_LIST}
    for issue in all_issues:
        cat_name = classify_issue(issue, rev_w, rev_h)
        categories_map[cat_name].append(issue)

    categories_report = []
    for cat_name in CATEGORIES_LIST:
        cat_issues = categories_map[cat_name]
        status = "FAIL" if len(cat_issues) > 0 else "PASS"
        categories_report.append({
            "name": cat_name,
            "status": status,
            "issues": [iss.get("description") for iss in cat_issues]
        })

    page_has_issues = len(all_issues) > 0
    page_status = "FAIL" if page_has_issues else "PASS"
    total_checks = len(CATEGORIES_LIST)
    failed_checks = sum(1 for c in categories_report if c["status"] == "FAIL")
    passed_checks = total_checks - failed_checks

    summary_counts = {
        "total_checks": total_checks,
        "passed": passed_checks,
        "failed": failed_checks
    }

    if page_has_issues:
        summary = (
            f"Page {page_num} has {len(all_issues)} identified discrepancies. "
            f"Failed categories: {', '.join([c['name'] for c in categories_report if c['status'] == 'FAIL'])}."
        )
    else:
        summary = f"Page {page_num} is correct and matches the reference drawing in all audit categories."

    return {
        "page": page_num,
        "page_has_issues": page_has_issues,
        "issues": all_issues,
        "summary": summary,
        "status": page_status,
        "summary_counts": summary_counts,
        "categories_report": categories_report
    }

