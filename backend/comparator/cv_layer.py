"""Computer Vision Layer (Structural Verification).

Rasterizes pages, aligns the candidate image to the reference image using OpenCV
(ORB feature matching), computes difference masks, and isolates localized
structural visual discrepancies using contour detection.
"""

from __future__ import annotations

import cv2
import numpy as np
import fitz

from .config import Config

BBox = tuple[float, float, float, float]


def page_to_numpy(page: fitz.Page, dpi: int) -> np.ndarray:
    """Rasterize a PDF page to a grayscale numpy array (cached)."""
    attr_name = f"_cached_np_image_{dpi}"
    if not hasattr(page, attr_name):
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        setattr(page, attr_name, img)
    return getattr(page, attr_name)



def align_images_orb(
    ref_img: np.ndarray,
    cand_img: np.ndarray,
    config: Config,
) -> tuple[np.ndarray, np.ndarray]:
    """Align candidate image to reference image using ORB feature matching.
    
    Returns (aligned_cand_img, homography_matrix). If alignment fails, returns the
    unaligned candidate image and an identity matrix.
    """
    h_ref, w_ref = ref_img.shape
    h_cand, w_cand = cand_img.shape

    # Initialize ORB detector
    orb = cv2.ORB_create(nfeatures=3000)
    kp_ref, des_ref = orb.detectAndCompute(ref_img, None)
    kp_cand, des_cand = orb.detectAndCompute(cand_img, None)

    # If too few features, fall back to identity (simple scaling)
    if des_ref is None or des_cand is None or len(kp_ref) < 10 or len(kp_cand) < 10:
        # Simple scaling fallback
        scale_x = w_ref / w_cand
        scale_y = h_ref / h_cand
        M = np.array([[scale_x, 0, 0], [0, scale_y, 0], [0, 0, 1]], dtype=float)
        aligned = cv2.resize(cand_img, (w_ref, h_ref), interpolation=cv2.INTER_LINEAR)
        return aligned, M

    # Match descriptors using BFMatcher with Hamming distance
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des_ref, des_cand)

    # Sort matches by distance
    matches = sorted(matches, key=lambda x: x.distance)

    # Keep top 15% matches, but at least 15 matches
    good_matches_count = max(15, int(len(matches) * 0.15))
    good_matches = matches[:good_matches_count]

    if len(good_matches) < 4:
        scale_x = w_ref / w_cand
        scale_y = h_ref / h_cand
        M = np.array([[scale_x, 0, 0], [0, scale_y, 0], [0, 0, 1]], dtype=float)
        aligned = cv2.resize(cand_img, (w_ref, h_ref), interpolation=cv2.INTER_LINEAR)
        return aligned, M

    # Extract source and destination points
    ref_pts = np.float32([kp_ref[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    cand_pts = np.float32([kp_cand[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    # Find homography mapping candidate -> reference
    M, status = cv2.findHomography(cand_pts, ref_pts, cv2.RANSAC, 5.0)

    if M is None or not np.isfinite(M).all() or abs(np.linalg.det(M)) < 1e-9:
        scale_x = w_ref / w_cand
        scale_y = h_ref / h_cand
        M = np.array([[scale_x, 0, 0], [0, scale_y, 0], [0, 0, 1]], dtype=float)
        aligned = cv2.resize(cand_img, (w_ref, h_ref), interpolation=cv2.INTER_LINEAR)
        return aligned, M

    # Warp candidate image to align with reference
    # Background in engineering drawings is white, so fill border with 255
    aligned = cv2.warpPerspective(
        cand_img, M, (w_ref, h_ref),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255
    )
    return aligned, M


from .register import Registration

def find_visual_differences(
    ref_page: fitz.Page,
    cand_page: fitz.Page,
    registration: Registration | None,
    config: Config,
    cand_table_bboxes: list[BBox] = None,
) -> list[tuple[BBox, BBox, float]]:
    """Compare reference and candidate pages visually.
    
    Performs rasterization, alignment (per-view or global), absolute difference, morph filters,
    and contour extraction.
    Returns a list of (bbox_ref, bbox_cand, diff_score) in PDF points.
    """
    dpi = config.render_dpi
    zoom = dpi / 72.0

    ref_img = page_to_numpy(ref_page, dpi)
    cand_img = page_to_numpy(cand_page, dpi)

    h_ref, w_ref = ref_img.shape
    h_cand, w_cand = cand_img.shape

    # 1. Initialize combined threshold image and global regions mask
    cleaned_diff = np.zeros((h_ref, w_ref), dtype=np.uint8)
    global_mask = np.full((h_ref, w_ref), 255, dtype=np.uint8)

    has_local_views = False
    if registration is not None and registration.models and len(registration.models) >= 1:
        has_local_views = True
        margin = 30.0  # padding in PDF points
        for mdl in registration.models:
            anchors = mdl.anchors
            if len(anchors) < 2:
                continue
            x0 = float(np.min(anchors[:, 0])) - margin
            y0 = float(np.min(anchors[:, 1])) - margin
            x1 = float(np.max(anchors[:, 0])) + margin
            y1 = float(np.max(anchors[:, 1])) + margin

            # Clamp to ref page boundaries
            x0, y0 = max(0.0, x0), max(0.0, y0)
            x1, y1 = min(float(ref_page.rect.width), x1), min(float(ref_page.rect.height), y1)

            if x1 - x0 < 5 or y1 - y0 < 5:
                continue

            # Pixel crop coordinates on Ref
            rx0, ry0, rx1, ry1 = int(x0 * zoom), int(y0 * zoom), int(x1 * zoom), int(y1 * zoom)
            
            # Map ref view bbox corners to candidate space
            corners = np.array([
                [x0, y0],
                [x1, y0],
                [x1, y1],
                [x0, y1]
            ], dtype=float)
            mapped_pts = (mdl.matrix[:, :2] @ corners.T).T + mdl.matrix[:, 2]
            cx0 = float(np.min(mapped_pts[:, 0])) - margin
            cy0 = float(np.min(mapped_pts[:, 1])) - margin
            cx1 = float(np.max(mapped_pts[:, 0])) + margin
            cy1 = float(np.max(mapped_pts[:, 1])) + margin

            # Clamp to candidate page boundaries
            cx0, cy0 = max(0.0, cx0), max(0.0, cy0)
            cx1, cy1 = min(float(cand_page.rect.width), cx1), min(float(cand_page.rect.height), cy1)

            # Pixel crop coordinates on Cand
            ccx0, ccy0, ccx1, ccy1 = int(cx0 * zoom), int(cy0 * zoom), int(cx1 * zoom), int(cy1 * zoom)

            if rx1 - rx0 < 5 or ry1 - ry0 < 5 or ccx1 - ccx0 < 5 or ccy1 - ccy0 < 5:
                continue

            ref_crop = ref_img[ry0:ry1, rx0:rx1]
            cand_crop = cand_img[ccy0:ccy1, ccx0:ccx1]

            # Compute relative crop matrix mapping: Ref crop coords -> Cand crop coords
            ref_origin = np.array([x0, y0], dtype=float)
            cand_origin = np.array([cx0, cy0], dtype=float)
            t_cand_offset = mdl.matrix[:, :2] @ ref_origin + mdl.matrix[:, 2] - cand_origin

            M_crop_pixel = np.zeros((2, 3), dtype=float)
            M_crop_pixel[:, :2] = mdl.matrix[:, :2]
            M_crop_pixel[:, 2] = t_cand_offset * zoom

            # Warp candidate crop to match reference crop size
            try:
                aligned_cand_crop = cv2.warpAffine(
                    cand_crop, M_crop_pixel, (ref_crop.shape[1], ref_crop.shape[0]),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=255
                )
                
                # Compute absolute diff
                diff_crop = cv2.absdiff(ref_crop, aligned_cand_crop)
                _, thresh_crop = cv2.threshold(diff_crop, 30, 255, cv2.THRESH_BINARY)
                
                # Update page-wide diff mask
                cleaned_diff[ry0:ry1, rx0:rx1] = np.maximum(cleaned_diff[ry0:ry1, rx0:rx1], thresh_crop)
                
                # Exclude this view from global check
                global_mask[ry0:ry1, rx0:rx1] = 0
            except Exception:
                pass

    # 2. Run global ORB alignment for background/non-view areas
    aligned_cand, M = align_images_orb(ref_img, cand_img, config)
    diff = cv2.absdiff(ref_img, aligned_cand)
    _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

    if has_local_views:
        # Mask out view regions from the global page diff
        thresh_global = cv2.bitwise_and(thresh, thresh, mask=global_mask)
        cleaned_diff = cv2.bitwise_or(cleaned_diff, thresh_global)
    else:
        cleaned_diff = thresh

    # Zero out BOM tables to skip analyzing them
    if cand_table_bboxes:
        for t_bbox in cand_table_bboxes:
            # t_bbox is in candidate PDF coordinates
            # However, cleaned_diff is currently aligned with the Reference image.
            # We map candidate bbox to reference space using M_inv
            try:
                M_inv = np.linalg.inv(M)
                corners_cand = np.array([
                    [t_bbox[0], t_bbox[1]],
                    [t_bbox[2], t_bbox[1]],
                    [t_bbox[2], t_bbox[3]],
                    [t_bbox[0], t_bbox[3]]
                ], dtype=float).reshape(-1, 1, 2)
                
                # Check if we should map locally
                local_mapped = False
                cx_cand = (t_bbox[0] + t_bbox[2]) / 2.0
                cy_cand = (t_bbox[1] + t_bbox[3]) / 2.0
                if registration is not None and registration.models:
                    best_idx = 0
                    best_d = float("inf")
                    for idx, mdl in enumerate(registration.models):
                        # Approximate mapping: use M to guess reference point for distance
                        approx_ref = M_inv @ np.array([cx_cand, cy_cand, 1.0])
                        approx_ref = approx_ref[:2] / approx_ref[2]
                        d = float(np.min(((mdl.anchors[:, 0] - approx_ref[0]) ** 2 + (mdl.anchors[:, 1] - approx_ref[1]) ** 2)))
                        if d < best_d:
                            best_d = d
                            best_idx = idx
                    if best_d < 300.0:
                        m_local = registration.models[best_idx].matrix
                        m_3x3 = np.eye(3)
                        m_3x3[:2, :] = m_local
                        corners_ref = cv2.perspectiveTransform(corners_cand, m_3x3)
                        local_mapped = True
                
                if not local_mapped:
                    corners_ref = cv2.perspectiveTransform(corners_cand, M)

                corners_ref = corners_ref.reshape(-1, 2) * zoom
                rx0, ry0 = int(np.min(corners_ref[:, 0])), int(np.min(corners_ref[:, 1]))
                rx1, ry1 = int(np.max(corners_ref[:, 0])), int(np.max(corners_ref[:, 1]))
                rx0, ry0 = max(0, rx0), max(0, ry0)
                rx1, ry1 = min(w_ref, rx1), min(h_ref, ry1)
                cleaned_diff[ry0:ry1, rx0:rx1] = 0
            except Exception:
                pass

    # 3. Morphological clean-up
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(cleaned_diff, cv2.MORPH_OPEN, kernel_open)
    
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel_close)

    # 4. Find contours
    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = config.cv_min_contour_area
    differences = []

    try:
        M_inv = np.linalg.inv(M)
    except np.linalg.LinAlgError:
        M_inv = np.eye(3)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        rx, ry, rw, rh = cv2.boundingRect(cnt)
        roi_diff = cleaned[ry:ry+rh, rx:rx+rw]
        diff_score = float(np.mean(roi_diff) / 255.0)

        if diff_score < 0.05:
            continue

        bbox_ref = (rx / zoom, ry / zoom, (rx + rw) / zoom, (ry + rh) / zoom)

        # Map corners back to candidate space
        corners_ref = np.array([
            [rx, ry],
            [rx + rw, ry],
            [rx + rw, ry + rh],
            [rx, ry + rh]
        ], dtype=float).reshape(-1, 1, 2)

        cx_ref_pt = rx + rw / 2.0
        cy_ref_pt = ry + rh / 2.0
        
        local_mapped = False
        if registration is not None and registration.models:
            best_idx = 0
            best_d = float("inf")
            for idx, mdl in enumerate(registration.models):
                d = float(np.min(((mdl.anchors[:, 0] - cx_ref_pt / zoom) ** 2 + (mdl.anchors[:, 1] - cy_ref_pt / zoom) ** 2)))
                if d < best_d:
                    best_d = d
                    best_idx = idx
            
            if best_d < 300.0:  # within ~4 inches
                try:
                    m_local = registration.models[best_idx].matrix
                    m_3x3 = np.eye(3)
                    m_3x3[:2, :] = m_local
                    m_local_inv = np.linalg.inv(m_3x3)
                    
                    corners_cand = cv2.perspectiveTransform(corners_ref, m_local_inv)
                    corners_cand = corners_cand.reshape(-1, 2) / zoom
                    local_mapped = True
                except Exception:
                    pass

        if not local_mapped:
            corners_cand = cv2.perspectiveTransform(corners_ref, M_inv)
            corners_cand = corners_cand.reshape(-1, 2) / zoom

        cx0 = float(np.min(corners_cand[:, 0]))
        cy0 = float(np.min(corners_cand[:, 1]))
        cx1 = float(np.max(corners_cand[:, 0]))
        cy1 = float(np.max(corners_cand[:, 1]))
        bbox_cand = (cx0, cy0, cx1, cy1)

        bbox_ref = (
            max(0.0, bbox_ref[0]), max(0.0, bbox_ref[1]),
            min(float(ref_page.rect.width), bbox_ref[2]), min(float(ref_page.rect.height), bbox_ref[3])
        )
        bbox_cand = (
            max(0.0, bbox_cand[0]), max(0.0, bbox_cand[1]),
            min(float(cand_page.rect.width), bbox_cand[2]), min(float(cand_page.rect.height), bbox_cand[3])
        )

        differences.append((bbox_ref, bbox_cand, diff_score))

    return differences
