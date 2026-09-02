"""
Oil spill detection service.

Pipeline per image:
1. If a trained classifier exists (backend/models/sar_spill_classifier.pkl)
   -> real model inference, labelled dataClass="model".
2. If no model -> honest heuristic fallback (texture homogeneity), labelled
   dataClass="heuristic", with a clear message that no trained model exists.

Weak segmentation (suspected slick region) uses explainable image processing:
adaptive thresholding of low-variance dark regions. It is explicitly labelled
a WEAK/heuristic segmentation — no ground-truth masks exist in the dataset.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

from .. import config
from ..ml import features as ml
from ..schemas import DataClass, DetectionResult, SlickGeometry, SpillCharacterization

logger = logging.getLogger("app.services.detection")

SEGMENTATION_METHOD = "weak-adaptive-threshold"
SEGMENTATION_NOTE = (
    "Weak, explainable segmentation based on adaptive thresholding of "
    "low-texture darker regions. NOT a trained segmentation model — the "
    "repository dataset has no pixel masks. Use as a visual aid only."
)


def _source_label(data_class: DataClass, description: str) -> dict[str, Any]:
    return {"dataClass": data_class, "description": description}


def detect_from_array(
    arr: np.ndarray, image_id: str, acquisition_time: Optional[str] = None
) -> DetectionResult:
    """Run spill classification on a grayscale float array in [0, 1]."""
    model = ml.load_model()
    if model is not None:
        cls, prob = model.predict(arr)
        method = f"{model.metadata.get('model_type', 'HGB')} texture-classifier (trained)"
        return DetectionResult(
            detected=cls == 1,
            confidence=round(prob if cls == 1 else 1 - prob, 4),
            image_id=image_id,
            acquisition_time=acquisition_time,
            detection_method=method,
            source_label=_source_label(
                "model",
                f"Output of a trained classifier "
                f"(5-fold CV accuracy {model.cv_accuracy}) trained on the "
                f"repository's 5,630-image SAR dataset.",
            ),
            model_available=True,
            message=None,
        )

    # Heuristic fallback — clearly labelled
    mean, std = float(arr.mean()), float(arr.std())
    detected = std < 0.05
    confidence = min(0.75, max(0.0, (0.05 - std) / 0.05)) if detected else min(0.7, std)
    return DetectionResult(
        detected=bool(detected),
        confidence=round(confidence, 4),
        image_id=image_id,
        acquisition_time=acquisition_time,
        detection_method="texture-homogeneity heuristic (UNTRAINED)",
        source_label=_source_label(
            "heuristic",
            "No trained classifier found. Result is a simple texture "
            "homogeneity heuristic, NOT a model output. Run "
            "backend/train_sar_classifier.py to train the real classifier.",
        ),
        model_available=False,
        message="Classifier not trained — heuristic result. Run train_sar_classifier.py.",
    )


def detect_from_file(path: str | Path) -> tuple[DetectionResult, np.ndarray]:
    """Convenience: load image from disk, run detection, return result + array."""
    arr = ml.load_image_grayscale(path)
    image_id = Path(path).name
    return detect_from_array(arr, image_id), arr


# ═══════════════════════════════════════════════════════════════════════════
# Weak segmentation of the suspected slick region
# ═══════════════════════════════════════════════════════════════════════════


def _block_std(arr: np.ndarray, k: int) -> np.ndarray:
    """Std within k x k blocks (padded to multiple of k)."""
    H, W = arr.shape
    hh, ww = (H // k) * k, (W // k) * k
    core = arr[:hh, :ww].reshape(H // k, k, W // k, k)
    out = core.std(axis=(1, 3))
    if hh == H and ww == W:
        return out
    # pad borders by repeating edge blocks
    rep_h = int(np.ceil(H / k)) - out.shape[0] + 1
    rep_w = int(np.ceil(W / k)) - out.shape[1] + 1
    out = np.pad(out, ((0, max(0, rep_h - 1)), (0, max(0, rep_w - 1))), mode="edge")
    return out[: int(np.ceil(H / k)), : int(np.ceil(W / k))]


def weak_segment_slick(arr: np.ndarray) -> Optional[SlickGeometry]:
    """
    Segment suspected oil-slick pixels: darker AND smoother than surroundings.

    Method (explainable):
      1. Compute 8x8 block std map (texture smoothness).
      2. Adaptive threshold: blocks with std below (median * 0.6) are candidates.
      3. Candidate blocks must also be darker than the image median.
      4. Keep the largest connected candidate region (simple BFS labelling).
      5. Compute geometry from that region's blocks.

    Returns None when no plausible slick region is found.
    NOTE: heuristic, not a trained segmentation model.
    """
    H, W = arr.shape
    if H < 16 or W < 16:
        return None

    block = 8
    bstd = _block_std(arr, block)
    bmean = arr[: (H // block) * block or H, : (W // block) * block or W]
    # block means via resize trick
    bm = np.asarray(
        Image.fromarray((arr * 255).astype(np.uint8)).resize(
            (bstd.shape[1], bstd.shape[0]), Image.BILINEAR
        ),
        dtype=np.float64,
    ) / 255.0

    med_std = float(np.median(bstd))
    med_val = float(np.median(bm))
    if med_std <= 0:
        return None

    candidate = (bstd < med_std * 0.6) & (bm < med_val)
    if not candidate.any():
        candidate = (bstd < med_std * 0.75) & (bm < med_val * 0.95)
    if not candidate.any():
        return None

    # connected components (4-neighbour BFS) on candidate blocks
    labels = np.zeros(candidate.shape, dtype=int)
    cur = 0
    comps: list[tuple[int, int, list[tuple[int, int]]]] = []  # (label, size, cells)
    gh, gw = candidate.shape
    for sy in range(gh):
        for sx in range(gw):
            if candidate[sy, sx] and labels[sy, sx] == 0:
                cur += 1
                stack = [(sy, sx)]
                labels[sy, sx] = cur
                cells: list[tuple[int, int]] = []
                while stack:
                    y, x = stack.pop()
                    cells.append((y, x))
                    for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                        if 0 <= ny < gh and 0 <= nx < gw and candidate[ny, nx] and labels[ny, nx] == 0:
                            labels[ny, nx] = cur
                            stack.append((ny, nx))
                comps.append((cur, len(cells), cells))

    comps.sort(key=lambda c: c[1], reverse=True)
    if not comps or comps[0][1] < 2:  # need at least 2 blocks for geometry
        return None
    cells = comps[0][2]

    # region geometry in pixel space (block centres scaled up)
    xs = [x * block + block / 2 for _, x in cells]
    ys = [y * block + block / 2 for _, y in cells]
    area_px = len(cells) * block * block
    x0 = int(min(x for x in xs) - block / 2)
    x1 = int(max(x for x in xs) + block / 2)
    y0 = int(min(y for y in ys) - block / 2)
    y1 = int(max(y for y in ys) + block / 2)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)

    cx = float(np.mean(xs))
    cy = float(np.mean(ys))

    # PCA of block centres for length/width/orientation
    pts = np.column_stack([np.array(xs) - cx, np.array(ys) - cy])
    if len(pts) >= 3:
        cov = np.cov(pts.T)
        evals, evecs = np.linalg.eigh(cov)
        order = np.argsort(evals)[::-1]
        evals = np.clip(evals[order], 0, None)
        evec = evecs[:, order[0]]
        length = 4 * np.sqrt(evals[0]) if evals[0] > 0 else block * 2
        width = 4 * np.sqrt(evals[1]) if evals[1] > 0 else block
        ang = float(np.degrees(np.arctan2(evec[1], evec[0])))
        # normalize to [-90, 90] for orientation readability
        if ang > 90:
            ang -= 180
        if ang < -90:
            ang += 180
    else:
        length = width = block * len(cells) ** 0.5
        ang = 0.0

    aspect = float(length / width) if width > 0 else 1.0
    if aspect >= 2.5:
        gtype = "elongated"
    elif aspect >= 1.4:
        gtype = "moderately elongated"
    else:
        gtype = "compact"

    # perimeter: count block boundary edges
    cellset = set(cells)
    perim = 0.0
    for (y, x) in cells:
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if (ny, nx) not in cellset:
                perim += block
    if len(cells) == 1:
        perim = 4 * block

    return SlickGeometry(
        centroid_px=(round(cx, 1), round(cy, 1)),
        bounding_box_px=(x0, y0, x1, y1),
        area_px=int(area_px),
        perimeter_px=round(perim, 1),
        width_px=round(float(width), 1),
        length_px=round(float(length), 1),
        aspect_ratio=round(aspect, 2),
        orientation_deg=round(ang, 1),
        geometry_type=gtype,
    )


# ── Georeferencing support (real when available) ─────────────────────────────

def try_read_geotiff_transform(path: str | Path) -> Optional[dict[str, Any]]:
    """
    Attempt to read a geotransform from a GeoTIFF WITHOUT optional deps.

    Supports plain TIFF files that carry GeoTIFF keys via GDAL-style ASCII
    metadata is unreliable; a proper implementation needs rasterio/GDAL.
    When unavailable, returns None — callers must mark geo data unavailable
    rather than fabricating coordinates.
    """
    # We deliberately do not implement a half-correct TIFF parser: without
    # rasterio/GDAL the geotransform cannot be read reliably.
    return None


def characterize(
    arr: np.ndarray,
    detection: DetectionResult,
    image_path: str | Path,
    acquisition_time: Optional[str] = None,
    geographic: Optional[dict[str, Any]] = None,
) -> SpillCharacterization:
    """Build the full spill characterization (detection + geometry + notes)."""
    geometry = weak_segment_slick(arr) if detection.detected else None

    geo_note = (
        "Source image is not georeferenced (plain JPG from the dataset). "
        "Geographic coordinates are UNAVAILABLE from this image."
    )
    if geographic:
        geo_note = "Geographic coordinates derived from the image's geotransform."

    age_note = (
        "Spill age cannot be estimated from this image. Reported time is the "
        "observation/acquisition time only; age estimation is unavailable."
    )
    if acquisition_time is None:
        acquisition_time = datetime.now(timezone.utc).isoformat()
        age_note = (
            "No acquisition metadata available; current time used as the "
            "observation timestamp (SYSTEM time, not satellite metadata). "
            "Spill age estimation unavailable."
        )

    return SpillCharacterization(
        detection=detection,
        geometry=geometry,
        segmentation_method=SEGMENTATION_METHOD if geometry else "none",
        segmentation_note=SEGMENTATION_NOTE if geometry else
        "No slick region extracted (spill not detected or region too small).",
        geographic=geographic,
        acquisition_time=acquisition_time,
        spill_age_note=age_note,
        source_label=detection.source_label,
    )
