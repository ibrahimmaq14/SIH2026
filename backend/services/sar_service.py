"""
SAR Image Service — serves the SAR image dataset for the oil spill detection UI.

The repository contains a binary classification dataset:
  Class 0 (no oil spill): 3,725 images
  Class 1 (oil spill): 1,905 images
  Format: 400x400 grayscale JPG

No CNN model exists in the repository. This service serves images and
provides demo classification metadata. All demo results are clearly labeled.
"""

import os
import random
from typing import Optional
from pathlib import Path

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data"))

_image_cache: Optional[dict] = None


def _get_sar_dir() -> str:
    return os.path.join(DATA_DIR, "SAR Image Dataset")


def _scan_images() -> dict:
    """Scan SAR image directory and cache file listings."""
    global _image_cache
    if _image_cache is not None:
        return _image_cache

    sar_dir = _get_sar_dir()
    images = {"0": [], "1": []}

    for cls in ["0", "1"]:
        cls_dir = os.path.join(sar_dir, cls)
        if os.path.isdir(cls_dir):
            for fname in os.listdir(cls_dir):
                if fname.lower().endswith((".jpg", ".jpeg", ".png")):
                    # Parse naming convention: {aug}_{id}_{hash}_{region}_cls_{class}.jpg
                    parts = fname.rsplit("_cls_", 1)
                    region = ""
                    if len(parts) >= 1:
                        name_parts = parts[0].rsplit("_", 1)
                        if len(name_parts) == 2:
                            region = name_parts[1]

                    images[cls].append({
                        "filename": fname,
                        "class": int(cls),
                        "className": "Oil Spill" if cls == "1" else "No Oil Spill",
                        "region": region,
                        "path": os.path.join(cls_dir, fname),
                        "dimensions": "400x400",
                        "format": "Grayscale JPG",
                    })

    _image_cache = images
    return _image_cache


def get_sar_summary() -> dict:
    """Get summary of available SAR dataset."""
    images = _scan_images()
    return {
        "totalImages": len(images["0"]) + len(images["1"]),
        "class0Count": len(images["0"]),
        "class1Count": len(images["1"]),
        "classes": [
            {"id": 0, "name": "No Oil Spill", "count": len(images["0"])},
            {"id": 1, "name": "Oil Spill", "count": len(images["1"])},
        ],
        "imageFormat": "400x400 Grayscale JPG",
        "source": "SAR (Synthetic Aperture Radar) Imagery",
        "modelStatus": "Not trained — no CNN model exists in repository",
        "note": "Classification results shown are demo/sample data only",
    }


def get_sar_images(cls: Optional[int] = None, page: int = 1,
                   page_size: int = 20, region: str = "") -> dict:
    """Get paginated SAR image listing."""
    images = _scan_images()

    if cls is not None:
        all_imgs = images.get(str(cls), [])
    else:
        all_imgs = images["0"] + images["1"]

    # Filter by region
    if region:
        region_upper = region.upper()
        all_imgs = [img for img in all_imgs if img["region"].upper() == region_upper]

    total = len(all_imgs)
    total_pages = max(1, (total + page_size - 1) // page_size)

    start = (page - 1) * page_size
    end = start + page_size
    page_data = all_imgs[start:end]

    return {
        "images": page_data,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
    }


def get_image_path(cls: int, filename: str) -> Optional[str]:
    """Get full path to a specific SAR image."""
    sar_dir = _get_sar_dir()
    path = os.path.join(sar_dir, str(cls), filename)
    if os.path.isfile(path):
        return path
    return None


def get_regions() -> list:
    """Get unique region codes from the dataset."""
    images = _scan_images()
    regions = set()
    for cls_images in images.values():
        for img in cls_images:
            if img["region"]:
                regions.add(img["region"])
    return sorted(list(regions))


def get_demo_detections() -> list:
    """
    Generate demo detection results using actual SAR images.
    Clearly labeled as demo data — no real model inference.
    """
    images = _scan_images()

    # Pick a mix of images from both classes
    sample_spill = random.sample(images["1"], min(5, len(images["1"])))
    sample_clean = random.sample(images["0"], min(3, len(images["0"])))

    detections = []
    for i, img in enumerate(sample_spill):
        detections.append({
            "id": f"DET-DEMO-{i+1:03d}",
            "filename": img["filename"],
            "class": 1,
            "className": "Oil Spill Detected",
            "region": img["region"],
            "isDemo": True,
            "note": "Demo classification — no trained model available",
            "status": "Demo",
            "dimensions": img["dimensions"],
        })

    for i, img in enumerate(sample_clean):
        detections.append({
            "id": f"DET-DEMO-{len(sample_spill)+i+1:03d}",
            "filename": img["filename"],
            "class": 0,
            "className": "No Oil Spill",
            "region": img["region"],
            "isDemo": True,
            "note": "Demo classification — no trained model available",
            "status": "Demo",
            "dimensions": img["dimensions"],
        })

    return detections
