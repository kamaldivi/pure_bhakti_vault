# pip install pymupdf
from __future__ import annotations

import collections
import dataclasses
import math
from typing import Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF


@dataclasses.dataclass
class BoundaryConfig:
    """
    Configuration for detect_page_boundaries().
    """
    # Pages to ignore (0-based indexes). Useful for front/back matter, plates, etc.
    ignored_pages: Optional[Sequence[int]] = None

    # Minimum fraction of the page height that must remain between header/footer.
    # If the computed gap is smaller, boundaries are relaxed to meet this ratio.
    min_body_ratio: float = 0.65

    # Clustering preferences
    use_dbscan_like: bool = True           # 1D DBSCAN-like (window) clustering
    eps_multiplier: float = 3.0            # eps = eps_multiplier * MAD
    min_samples: Optional[int] = None      # default: max(3, ~3% of observed pages)
    min_cluster_coverage: float = 0.40     # fraction of observed pages to trust cluster

    # Histogram fallback
    hist_bins: int = 60

    # Robust-percentile fallback if no stable cluster
    robust_header_percentile: float = 0.95  # safe header boundary ≈ high quantile of header-bottoms
    robust_footer_percentile: float = 0.05  # safe footer boundary ≈ low quantile of footer-tops

    # Sampling (for very large PDFs)
    max_pages: Optional[int] = None   # if set, only analyze the first N non-ignored pages

    # Output/diagnostics
    return_normalized: bool = False   # top-level return in absolute y by default; set True to return 0..1
    diagnostics: bool = True


@dataclasses.dataclass
class PageLineSummary:
    page_index: int
    page_height: float
    top_line_bbox: Optional[Tuple[float, float, float, float]]  # (x0,y0,x1,y1)
    bottom_line_bbox: Optional[Tuple[float, float, float, float]]
    header_bottom_y_norm: Optional[float]  # topmost line's y1 normalized
    footer_top_y_norm: Optional[float]     # bottommost line's y0 normalized
    in_header_cluster: bool = False
    in_footer_cluster: bool = False
    no_text: bool = False
    ignored: bool = False


def detect_page_boundaries(
    pdf_path: str,
    config: Optional[BoundaryConfig] = None,
) -> Tuple[float, float, Dict, List[Dict]]:
    """
    Detect safe page header/footer boundaries for a book PDF.

    Returns:
        (safe_header_y, safe_footer_y, stats, per_page_report)

        - safe_header_y / safe_footer_y: by default absolute y in points (relative to the
          dominant page height). If config.return_normalized=True, return 0..1 normalized.
        - stats: dictionary with rich diagnostics (chosen methods, cluster centers, MAD, eps, etc.)
        - per_page_report: list of dicts, one per page, with per-page measurements and flags.

    Algorithm (high level):
        1) For each page with >=1 text line, record:
              header_bottom_y = topmost_line.y1
              footer_top_y    = bottommost_line.y0
           Normalize each by that page's height (0..1).
        2) Build distributions across pages (header_bottom_y and footer_top_y).
           Use 1D clustering (DBSCAN-like) with eps derived from MAD to find dominant bands.
        3) For header cluster: safe_header_y_norm = max(values in that cluster)
           For footer cluster: safe_footer_y_norm = min(values in that cluster)
        4) If no stable cluster, fall back to robust percentiles.
        5) Enforce a minimum body ratio (footer - header >= min_body_ratio). Relax boundaries
           inward (i.e., include a bit more page) if needed.
        6) Convert to absolute y using dominant page height; include normalized values in stats.
    """
    cfg = config or BoundaryConfig()
    ignored = set(cfg.ignored_pages or [])

    doc = fitz.open(pdf_path)
    n_pages = len(doc)

    # Per-page line summaries
    page_summaries: List[PageLineSummary] = []

    def _extract_line_bboxes(p: fitz.Page) -> List[Tuple[float, float, float, float]]:
        """
        Extract line-level bounding boxes from PyMuPDF's rawdict.
        Only 'text' blocks are considered (type==0).
        """
        out: List[Tuple[float, float, float, float]] = []
        raw = p.get_text("rawdict")
        for b in raw.get("blocks", []):
            if b.get("type", 0) != 0:
                continue  # skip non-text blocks (images, drawings)
            for l in b.get("lines", []):
                bbox = l.get("bbox")
                if bbox and len(bbox) == 4:
                    x0, y0, x1, y1 = bbox
                    # Guard against inverted boxes
                    if y1 < y0:
                        y0, y1 = y1, y0
                    out.append((x0, y0, x1, y1))
        # Ensure stable order (ascending top->bottom)
        out.sort(key=lambda bb: (bb[1], bb[3]))
        return out

    # Collect observations
    observed_headers: List[float] = []  # normalized y1 of top line
    observed_footers: List[float] = []  # normalized y0 of bottom line
    observed_idx_header: List[int] = []  # page indexes aligned with observed_headers
    observed_idx_footer: List[int] = []  # page indexes aligned with observed_footers
    page_heights: List[float] = []

    processed_pages = 0
    for i in range(n_pages):
        page = doc.load_page(i)
        h = float(page.rect.height)
        page_heights.append(h)
        sumrec = PageLineSummary(
            page_index=i, page_height=h,
            top_line_bbox=None, bottom_line_bbox=None,
            header_bottom_y_norm=None, footer_top_y_norm=None,
            no_text=False, ignored=(i in ignored)
        )
        if sumrec.ignored:
            page_summaries.append(sumrec)
            continue

        bboxes = _extract_line_bboxes(page)
        if len(bboxes) == 0:
            sumrec.no_text = True
            page_summaries.append(sumrec)
            continue

        # Topmost (first) and bottommost (last) by y
        top_bb = bboxes[0]
        bot_bb = bboxes[-1]
        sumrec.top_line_bbox = top_bb
        sumrec.bottom_line_bbox = bot_bb

        header_bottom_y = top_bb[3]  # y1
        footer_top_y = bot_bb[1]     # y0
        header_norm = header_bottom_y / h
        footer_norm = footer_top_y / h

        sumrec.header_bottom_y_norm = header_norm
        sumrec.footer_top_y_norm = footer_norm

        page_summaries.append(sumrec)
        observed_headers.append(header_norm)
        observed_footers.append(footer_norm)
        observed_idx_header.append(i)
        observed_idx_footer.append(i)

        processed_pages += 1
        if cfg.max_pages is not None and processed_pages >= cfg.max_pages:
            # still fill page_heights for all pages, but stop measurements
            break

    def _mad(vals: List[float]) -> float:
        if not vals:
            return 0.0
        med = _median(vals)
        return _median([abs(v - med) for v in vals])

    def _median(vals: List[float]) -> float:
        s = sorted(vals)
        n = len(s)
        if n == 0:
            return float("nan")
        if n % 2:
            return s[n // 2]
        return 0.5 * (s[n // 2 - 1] + s[n // 2])

    def _percentile(vals: List[float], p: float) -> float:
        """p in [0,1]"""
        if not vals:
            return float("nan")
        s = sorted(vals)
        k = (len(s) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return s[int(k)]
        d0 = s[f] * (c - k)
        d1 = s[c] * (k - f)
        return d0 + d1

    def _dbscan_like_cluster(values: List[float], eps: float, min_samples: int) -> Tuple[List[int], Dict]:
        """
        1D DBSCAN-like clustering without external deps.
        Strategy:
          - sort values (keep original indexes)
          - sliding window: expand right pointer while within eps of left
          - choose window with maximum count (>= min_samples) as dominant cluster
        Returns:
          (indices_of_members, info_dict)
        """
        if not values:
            return [], {"method": "dbscan_like", "eps": eps, "center": None, "count": 0}

        pairs = sorted([(v, j) for j, v in enumerate(values)], key=lambda t: t[0])
        best = (0, 0, 0)  # (count, left_idx, right_idx_inclusive)
        left = 0
        n = len(pairs)
        for right in range(n):
            # shrink left until window width <= eps
            while pairs[right][0] - pairs[left][0] > eps:
                left += 1
            count = right - left + 1
            if count > best[0]:
                best = (count, left, right)

        count, left, right = best
        members_sorted = pairs[left:right + 1] if count >= max(1, min_samples) else []
        member_idxs = [j for _, j in members_sorted]
        center = _median([v for v, _ in members_sorted]) if members_sorted else None

        return member_idxs, {
            "method": "dbscan_like",
            "eps": eps,
            "center": center,
            "count": len(member_idxs),
            "window_span": (pairs[left][0], pairs[right][0]) if members_sorted else None,
        }

    def _histogram_cluster(values: List[float], bins: int) -> Tuple[List[int], Dict]:
        """
        Simple histogram peak cluster: pick max-count bin, members are points within that bin.
        """
        if not values:
            return [], {"method": "hist", "center": None, "count": 0}
        vmin, vmax = min(values), max(values)
        if vmin == vmax:
            # all same
            return list(range(len(values))), {"method": "hist", "center": values[0], "count": len(values), "bin": (vmin, vmax)}
        width = (vmax - vmin) / max(1, bins)
        edges = [vmin + k * width for k in range(bins + 1)]
        counts = [0] * bins
        bin_members: List[List[int]] = [[] for _ in range(bins)]
        for j, v in enumerate(values):
            # last edge inclusive
            if v == edges[-1]:
                b = bins - 1
            else:
                b = max(0, min(bins - 1, int((v - vmin) / width)))
            counts[b] += 1
            bin_members[b].append(j)
        bmax = max(range(bins), key=lambda b: counts[b])
        members = bin_members[bmax]
        center = _median([values[j] for j in members]) if members else None
        return members, {"method": "hist", "center": center, "count": len(members), "bin": (edges[bmax], edges[bmax + 1])}

    def _cluster(values: List[float], prefer_dbscan: bool, mad_scale: float, min_samples: int, hist_bins: int):
        mad = _mad(values)
        # If MAD=0 (very tight), give a tiny eps so we still form a window
        eps = mad_scale * mad if mad > 0 else 0.002
        if prefer_dbscan:
            members, info = _dbscan_like_cluster(values, eps=eps, min_samples=min_samples)
        else:
            members, info = _histogram_cluster(values, bins=hist_bins)
        info["mad"] = mad
        info["eps"] = info.get("eps", eps)
        return members, info

    def _dominant_page_height(heights: List[float]) -> float:
        """
        Pick the most common height (rounded to 1 decimal to account for tiny numeric noise).
        If tie, use median height.
        """
        if not heights:
            return float("nan")
        rounded = [round(h, 1) for h in heights]
        freq = collections.Counter(rounded)
        most_common_height, _ = freq.most_common(1)[0]
        # map back to a representative original height near this rounded value (median among those)
        near = [h for h in heights if round(h, 1) == most_common_height]
        return _median(near) if near else _median(heights)

    # Build distributions for clustering
    hvals = [v for v in observed_headers if v is not None]
    fvals = [v for v in observed_footers if v is not None]
    n_obs = max(len(hvals), len(fvals))

    if cfg.min_samples is None:
        cfg_min_samples = max(3, int(0.03 * max(1, n_obs)))
    else:
        cfg_min_samples = cfg.min_samples

    header_members, header_info = _cluster(
        hvals, cfg.use_dbscan_like, cfg.eps_multiplier, cfg_min_samples, cfg.hist_bins
    )
    footer_members, footer_info = _cluster(
        fvals, cfg.use_dbscan_like, cfg.eps_multiplier, cfg_min_samples, cfg.hist_bins
    )

    # Mark cluster membership on per-page records
    header_member_pageidx = {observed_idx_header[j] for j in header_members}
    footer_member_pageidx = {observed_idx_footer[j] for j in footer_members}
    for s in page_summaries:
        if s.header_bottom_y_norm is not None and s.page_index in header_member_pageidx:
            s.in_header_cluster = True
        if s.footer_top_y_norm is not None and s.page_index in footer_member_pageidx:
            s.in_footer_cluster = True

    # Decide if clusters are "stable" (coverage enough)
    def _coverage_ok(members: List[int], total: int) -> bool:
        return (len(members) / max(1, total)) >= cfg.min_cluster_coverage

    header_ok = _coverage_ok(header_members, len(hvals))
    footer_ok = _coverage_ok(footer_members, len(fvals))

    # Safe boundaries (normalized)
    safe_header_norm: float
    safe_footer_norm: float
    method_header: str
    method_footer: str

    if header_ok and header_members:
        safe_header_norm = max(hvals[j] for j in header_members)
        method_header = f"{header_info['method']}_cluster_max"
    else:
        # robust percentile fallback
        safe_header_norm = _percentile(hvals, cfg.robust_header_percentile) if hvals else 0.0
        method_header = f"percentile_{cfg.robust_header_percentile:.2f}"

    if footer_ok and footer_members:
        safe_footer_norm = min(fvals[j] for j in footer_members)
        method_footer = f"{footer_info['method']}_cluster_min"
    else:
        safe_footer_norm = _percentile(fvals, cfg.robust_footer_percentile) if fvals else 1.0
        method_footer = f"percentile_{cfg.robust_footer_percentile:.2f}"

    # Enforce min body ratio
    body_norm = safe_footer_norm - safe_header_norm
    adjust_notes: List[str] = []
    if not math.isnan(body_norm) and body_norm < cfg.min_body_ratio:
        # Relax boundaries inward (less aggressive trimming) to preserve minimum body.
        # Prefer reducing header cut and raising footer cut minimally to meet the gap.
        target_gap = cfg.min_body_ratio
        # First, try lowering header boundary
        new_header = max(0.0, min(safe_header_norm, safe_footer_norm - target_gap))
        # Then ensure footer is at least header + target_gap
        new_footer = max(safe_footer_norm, min(1.0, new_header + target_gap))

        # If still impossible (e.g., target_gap > 1), clamp to [0,1]
        new_header = max(0.0, min(1.0, new_header))
        new_footer = max(0.0, min(1.0, new_footer))

        if new_header != safe_header_norm or new_footer != safe_footer_norm:
            adjust_notes.append(
                f"Adjusted for min_body_ratio={cfg.min_body_ratio:.2f} "
                f"(from gap={body_norm:.3f} to gap={new_footer - new_header:.3f})."
            )
        safe_header_norm, safe_footer_norm = new_header, new_footer

    # Convert to absolute using dominant page height
    dom_height = _dominant_page_height(page_heights[:processed_pages] if cfg.max_pages else page_heights)
    safe_header_abs = safe_header_norm * dom_height
    safe_footer_abs = safe_footer_norm * dom_height

    # Stats & diagnostics
    stats: Dict = {
        "pages_total": n_pages,
        "pages_measured": processed_pages,
        "ignored_pages": sorted(list(ignored)) if ignored else [],
        "dominant_page_height": dom_height,
        "methods": {
            "header": method_header,
            "footer": method_footer,
        },
        "clusters": {
            "header": {
                **header_info,
                "coverage": (len(header_members) / max(1, len(hvals))) if hvals else 0.0,
                "safe_header_norm": safe_header_norm,
            },
            "footer": {
                **footer_info,
                "coverage": (len(footer_members) / max(1, len(fvals))) if fvals else 0.0,
                "safe_footer_norm": safe_footer_norm,
            },
        },
        "mad": {
            "header": header_info.get("mad", None),
            "footer": footer_info.get("mad", None),
        },
        "eps": {
            "header": header_info.get("eps", None),
            "footer": footer_info.get("eps", None),
        },
        "gap_norm": safe_footer_norm - safe_header_norm,
        "min_body_ratio": cfg.min_body_ratio,
        "adjustments": adjust_notes,
        "normalized_boundaries": {
            "header": safe_header_norm,
            "footer": safe_footer_norm,
        },
        "absolute_boundaries_points": {
            "header": safe_header_abs,
            "footer": safe_footer_abs,
        },
        "fallback_percentiles": {
            "header": cfg.robust_header_percentile,
            "footer": cfg.robust_footer_percentile,
        },
        "cluster_coverage_threshold": cfg.min_cluster_coverage,
        "hist_bins": cfg.hist_bins,
        "used_dbscan_like": cfg.use_dbscan_like,
    }

    # Per-page report (dicts only)
    per_page_report: List[Dict] = []
    for s in page_summaries:
        rec = {
            "page_index": s.page_index,
            "page_height": s.page_height,
            "ignored": s.ignored,
            "no_text": s.no_text,
            "top_line_bbox": s.top_line_bbox,
            "bottom_line_bbox": s.bottom_line_bbox,
            "header_bottom_y_norm": s.header_bottom_y_norm,
            "footer_top_y_norm": s.footer_top_y_norm,
            "in_header_cluster": s.in_header_cluster,
            "in_footer_cluster": s.in_footer_cluster,
        }
        # Also include absolute per-page header/footer (derived from normalized * that page's height)
        if s.header_bottom_y_norm is not None:
            rec["header_bottom_y_abs"] = s.header_bottom_y_norm * s.page_height
        if s.footer_top_y_norm is not None:
            rec["footer_top_y_abs"] = s.footer_top_y_norm * s.page_height
        per_page_report.append(rec)

    if cfg.return_normalized:
        return safe_header_norm, safe_footer_norm, stats, per_page_report
    else:
        return safe_header_abs, safe_footer_abs, stats, per_page_report


# ---------------------------
# Example (commented usage):
# ---------------------------
# cfg = BoundaryConfig(
#     ignored_pages=[0, 1, 2],     # ignore front matter if needed
#     min_body_ratio=0.70,
#     use_dbscan_like=True,
#     eps_multiplier=3.0,
#     min_cluster_coverage=0.5,
#     max_pages=None,              # analyze all pages
#     return_normalized=False,     # return absolute points by default
#     diagnostics=True,
# )
# header_y, footer_y, stats, report = detect_page_boundaries("book.pdf", cfg)
# print(header_y, footer_y)
# print(stats["methods"], stats["clusters"])
# # 'report' contains per-page measurements & flags for QA.
