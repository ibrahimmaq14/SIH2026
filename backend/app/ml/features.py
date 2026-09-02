"""
SAR image feature extraction + classifier persistence.

The original repository claimed a "Customized CNN" for SAR oil-spill
classification, but NO CNN code or trained weights exist in the repository
(verified: no .h5/.pb/.pt/.pkl/.onnx files). The training script
(`backend/train_sar_classifier.py`) therefore builds an honest, reproducible
model from the shipped 5,630-image dataset:

- Native-resolution SAR texture/intensity features (multi-scale block stats,
  gradient energy, GLCM-style co-occurrence contrast/homogeneity/energy at
  offsets 1/2/4 px, directional elongation, 24x24 downsample)
- HistGradientBoosting classifier (scikit-learn)

If the optional TensorFlow CNN path (config.CNN_MODEL_PATH) exists it will be
used instead — but the shipped system does NOT pretend a CNN exists.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, UnidentifiedImageError

from .. import config

logger = logging.getLogger("app.ml")

GLCM_LEVELS = 32
DOWNSAMPLE = (24, 24)
BLOCK_SIZES = (5, 10, 20, 40)


class InvalidImageError(ValueError):
    """Raised when an uploaded/selected image cannot be opened or is unreadable."""


def load_image_grayscale(path: str | Path) -> np.ndarray:
    """Open an image and return a float64 grayscale array in [0, 1]."""
    try:
        with Image.open(path) as im:
            arr = np.asarray(im.convert("L"), dtype=np.float64) / 255.0
    except FileNotFoundError:
        raise InvalidImageError(f"Image file not found: {path}")
    except UnidentifiedImageError:
        raise InvalidImageError("File is not a valid image")
    except OSError as e:
        raise InvalidImageError(f"Could not read image: {e}")
    if arr.ndim != 2 or arr.size == 0:
        raise InvalidImageError("Image must be a 2D grayscale picture")
    return arr


def extract_features(img: np.ndarray) -> np.ndarray:
    """Extract the feature vector used by the trained classifier."""
    a = img
    H, W = a.shape
    small = np.asarray(
        Image.fromarray((a * 255).astype(np.uint8)).resize(DOWNSAMPLE),
        dtype=np.float64,
    ) / 255.0

    feats: list[float] = [a.mean(), a.std()]

    # Multi-scale block statistics: std of block means (texture homogeneity)
    for k in BLOCK_SIZES:
        if H >= k and W >= k:
            hh, ww = H // k * k, W // k * k
            v = a[:hh, :ww].reshape(H // k, k, W // k, k)
            feats.append(float(v.mean(axis=(1, 3)).std()))
        else:
            feats.append(0.0)

    # Gradient energy
    gx = float(np.abs(np.diff(a, axis=0)).mean())
    gy = float(np.abs(np.diff(a, axis=1)).mean())
    feats += [gx, gy]

    # GLCM-style co-occurrence features (vertical pairs at offsets 1, 2, 4)
    q = np.clip((a * GLCM_LEVELS).astype(int), 0, GLCM_LEVELS - 1)
    i_idx = np.arange(GLCM_LEVELS).reshape(-1, 1)
    j_idx = np.arange(GLCM_LEVELS).reshape(1, -1)
    for d in (1, 2, 4):
        if H > d:
            pair = q[:-d, :] * GLCM_LEVELS + q[d:, :]
            hist = np.bincount(
                pair.ravel(), minlength=GLCM_LEVELS * GLCM_LEVELS
            ).reshape(GLCM_LEVELS, GLCM_LEVELS).astype(float)
        else:
            hist = np.zeros((GLCM_LEVELS, GLCM_LEVELS))
        total = hist.sum()
        hist = hist / total if total > 0 else hist
        contrast = float((hist * (i_idx - j_idx) ** 2).sum())
        homogeneity = float((hist / (1 + np.abs(i_idx - j_idx))).sum())
        energy = float(np.sqrt((hist ** 2).sum()))
        feats += [contrast, homogeneity, energy]

    # Directional elongation (slicks tend to elongate; normal sea does not)
    if H >= 16 and W >= 16:
        hstd = float(a.reshape(H, 1, W // 16, 16).mean(axis=(1, 3)).std())
        vstd = float(a.reshape(H // 16, 16, W, 1).mean(axis=(1, 3)).std())
    else:
        hstd = vstd = 0.0
    feats += [hstd, vstd]

    feats += list(small.ravel())
    return np.asarray(feats, dtype=np.float64)


def feature_names() -> list[str]:
    names = ["mean", "std"]
    names += [f"block{k}_mean_std" for k in BLOCK_SIZES]
    names += ["grad_x", "grad_y"]
    for d in (1, 2, 4):
        names += [f"glcm_d{d}_contrast", f"glcm_d{d}_homogeneity", f"glcm_d{d}_energy"]
    names += ["elong_h_std", "elong_v_std"]
    names += [f"px_{i}" for i in range(DOWNSAMPLE[0] * DOWNSAMPLE[1])]
    return names


# ── Trained-model container ────────────────────────────────────────────────

_MODEL: Optional["SARSpillClassifier"] = None


class SARSpillClassifier:
    """Wrapper around the persisted HGB classifier + metadata."""

    def __init__(self, model, metadata: dict[str, Any]):
        self.model = model
        self.metadata = metadata

    @property
    def cv_accuracy(self) -> Optional[float]:
        return self.metadata.get("cv_accuracy_mean")

    def predict(self, img: np.ndarray) -> tuple[int, float]:
        """Return (class, probability_of_spill)."""
        x = extract_features(img).reshape(1, -1)
        proba = self.model.predict_proba(x)[0]
        cls = int(np.argmax(proba))
        return cls, float(proba[1])

    def decision_stats(self, img: np.ndarray) -> dict[str, Any]:
        cls, p = self.predict(img)
        return {
            "predicted_class": cls,
            "probability_spill": round(p, 4),
            "probability_clean": round(1 - p, 4),
        }


def model_path() -> Path:
    return Path(config.SPILL_CLASSIFIER_PATH)


def is_model_available() -> bool:
    return model_path().is_file()


def load_model() -> Optional[SARSpillClassifier]:
    """Load the trained classifier once; returns None when untrained."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    path = model_path()
    if not path.is_file():
        return None
    try:
        with open(path, "rb") as f:
            payload = pickle.load(f)
        _MODEL = SARSpillClassifier(payload["model"], payload.get("metadata", {}))
        logger.info("Loaded SAR spill classifier from %s", path)
        return _MODEL
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to load model %s: %s", path, e)
        return None


def get_model_info() -> dict[str, Any]:
    m = load_model()
    if m is None:
        return {
            "available": False,
            "message": "Classifier not trained yet — run backend/train_sar_classifier.py",
            "type": None,
        }
    return {
        "available": True,
        "type": m.metadata.get("model_type", "HistGradientBoostingClassifier"),
        "features": m.metadata.get("n_features"),
        "train_samples": m.metadata.get("n_train"),
        "cv_accuracy_mean": m.cv_accuracy,
        "cv_folds": m.metadata.get("cv_folds"),
        "trained_at": m.metadata.get("trained_at"),
        "dataset": m.metadata.get("dataset"),
    }
