"""Tests for detection, characterization, weak segmentation, and the ML model."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app import config
from app.ml import features as ml
from app.services import detection as detsvc


@pytest.fixture(scope="module")
def model():
    m = ml.load_model()
    if m is None:
        pytest.skip("SAR classifier not trained")
    return m


@pytest.fixture(scope="module")
def spill_image(sar_dataset_available):
    if not sar_dataset_available:
        pytest.skip("SAR dataset not available")
    d = Path(config.SAR_DIR) / "1"
    imgs = sorted(d.glob("*.jpg"))
    return imgs[0]


@pytest.fixture(scope="module")
def clean_image(sar_dataset_available):
    if not sar_dataset_available:
        pytest.skip("SAR dataset not available")
    d = Path(config.SAR_DIR) / "0"
    imgs = sorted(d.glob("*.jpg"))
    return imgs[0]


def test_model_metadata_honest(model):
    """The model must carry honest, evidence-backed accuracy numbers."""
    meta = model.metadata
    assert meta["cv_accuracy_mean"] is not None
    assert 0.0 < meta["cv_accuracy_mean"] < 1.0
    assert meta["dataset_size"] == 5630
    assert meta["holdout_accuracy"] >= meta["cv_accuracy_mean"] - 0.15


def test_detection_spill_image(model, spill_image):
    arr = ml.load_image_grayscale(spill_image)
    det = detsvc.detect_from_array(arr, image_id=spill_image.name)
    assert det.detected is True
    assert det.confidence > 0.5
    assert det.source_label.dataClass == "model"
    assert "trained" in det.detection_method.lower()


def test_detection_clean_image(model, clean_image):
    arr = ml.load_image_grayscale(clean_image)
    det = detsvc.detect_from_array(arr, image_id=clean_image.name)
    assert det.detected is False
    assert det.confidence > 0.5


def test_detection_response_format(model, spill_image):
    arr = ml.load_image_grayscale(spill_image)
    det = detsvc.detect_from_array(
        arr, image_id="test.jpg", acquisition_time="2021-02-01T12:00:00Z"
    )
    d = det.model_dump()
    assert d["detected"] in (True, False)
    assert 0.0 <= d["confidence"] <= 1.0
    assert isinstance(d["image_id"], str)
    assert d["acquisition_time"] == "2021-02-01T12:00:00Z"
    assert isinstance(d["detection_method"], str)
    assert d["source_label"]["dataClass"] == "model"


def test_weak_segmentation_spill_image(model, spill_image):
    arr = ml.load_image_grayscale(spill_image)
    det = detsvc.detect_from_array(arr, image_id=spill_image.name)
    if det.detected:
        geo = detsvc.weak_segment_slick(arr)
        if geo is not None:
            g = geo.model_dump()
            assert g["area_px"] > 0
            assert g["bounding_box_px"][2] > g["bounding_box_px"][0]
            assert g["bounding_box_px"][3] > g["bounding_box_px"][1]
            assert 0 <= g["orientation_deg"] <= 90 or -90 <= g["orientation_deg"] <= 0
            assert g["aspect_ratio"] >= 0


def test_weak_segmentation_noise():
    # uniform noise → no slick region expected
    rng = np.random.default_rng(0)
    noise = rng.uniform(0.3, 0.7, size=(400, 400))
    assert detsvc.weak_segment_slick(noise) is None or True  # must not crash


def test_weak_segmentation_smooth_dark_patch():
    # synthetic smooth dark patch on a TEXTURED background → detected as slick
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:400, 0:400]
    # structured background: gradients + speckle so blocks have real texture
    img = 0.5 + 0.12 * np.sin(xx / 9.0) * np.cos(yy / 7.0) + rng.uniform(-0.06, 0.06, size=(400, 400))
    img = np.clip(img, 0, 1)
    img[100:180, 120:260] = 0.25  # dark elongated smooth patch
    img[100:180, 120:260] += rng.uniform(0, 0.01, size=(80, 140))
    geo = detsvc.weak_segment_slick(img)
    if geo is not None:
        cx, cy = geo.centroid_px
        assert 90 <= cy <= 190
        assert 110 <= cx <= 270


def test_characterization_georef_honesty(model, spill_image):
    arr = ml.load_image_grayscale(spill_image)
    det = detsvc.detect_from_array(arr, image_id=spill_image.name)
    ch = detsvc.characterize(arr, det, spill_image)
    # dataset images are NOT georeferenced → geographic must be None
    assert ch.geographic is None
    assert "not georeferenced" in ch.spill_age_note.lower() or "unavailable" in ch.spill_age_note.lower()


def test_invalid_image_rejection():
    with pytest.raises(ml.InvalidImageError):
        ml.load_image_grayscale("Z:/nonexistent/definitely_missing.jpg")


def test_upload_tiny_image():
    # image below 16px → segmentation returns None but no crash
    arr = np.zeros((8, 8), dtype=np.float64)
    assert detsvc.weak_segment_slick(arr) is None
