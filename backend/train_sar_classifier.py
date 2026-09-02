"""
Train the SAR oil-spill classifier on the repository's dataset.

Usage (from backend/):
    python train_sar_classifier.py                 # train + 5-fold CV
    python train_sar_classifier.py --quick         # fast subset (smoke test)
    python train_sar_classifier.py --skip-cv       # skip cross-validation

Saves the trained model + metadata to app/models/sar_spill_classifier.pkl.

The original project's README claimed a TensorFlow/Keras CNN, but no CNN
code or weights exist in the repository. This script trains an honest,
fully-reproducible classifier using native-resolution SAR texture features
(GLCM co-occurrence, multi-scale block statistics, gradient energy,
directional elongation) + scikit-learn's HistGradientBoostingClassifier.
Reported accuracy comes from cross-validation on the actual dataset.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config
from app.ml.features import extract_features, feature_names

RANDOM_STATE = 42


def load_dataset(limit_per_class: int | None = None) -> tuple[np.ndarray, np.ndarray, list[str]]:
    sar_dir = Path(config.SAR_DIR)
    if not sar_dir.is_dir():
        raise SystemExit(f"SAR dataset not found at {sar_dir}")
    X, y, files = [], [], []
    for cls in (0, 1):
        cls_dir = sar_dir / str(cls)
        if not cls_dir.is_dir():
            raise SystemExit(f"Missing class directory {cls_dir}")
        names = sorted(f for f in cls_dir.iterdir() if f.suffix.lower() in {".jpg", ".jpeg", ".png"})
        if limit_per_class:
            names = names[:limit_per_class]
        for p in names:
            try:
                with Image.open(p) as im:
                    arr = np.asarray(im.convert("L"), dtype=np.float64) / 255.0
                X.append(extract_features(arr))
                y.append(cls)
                files.append(str(p.relative_to(sar_dir)))
            except Exception as e:
                print(f"  skipping {p.name}: {e}")
    return np.asarray(X), np.asarray(y), files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="train on 400/class subset")
    ap.add_argument("--skip-cv", action="store_true", help="skip 5-fold cross-validation")
    args = ap.parse_args()

    print(f"SAR dataset: {config.SAR_DIR}")
    t0 = time.time()
    limit = 400 if args.quick else None
    X, y, files = load_dataset(limit)
    print(f"Loaded {len(X)} images ({(y == 0).sum()} clean / {(y == 1).sum()} spill) "
          f"in {time.time() - t0:.0f}s | features: {X.shape[1]}")

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )

    model = HistGradientBoostingClassifier(
        max_iter=350, learning_rate=0.08, random_state=RANDOM_STATE
    )
    t0 = time.time()
    model.fit(X_tr, y_tr)
    holdout_acc = accuracy_score(y_te, model.predict(X_te))
    print(f"Holdout accuracy: {holdout_acc:.4f} (train {time.time() - t0:.0f}s)")
    print(classification_report(y_te, model.predict(X_te), digits=3))

    cv_mean = None
    cv_all = None
    if not args.skip_cv:
        print("Running 5-fold stratified CV ...")
        t0 = time.time()
        cv = cross_val_score(
            HistGradientBoostingClassifier(
                max_iter=350, learning_rate=0.08, random_state=RANDOM_STATE
            ),
            X, y, cv=StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE),
            n_jobs=1,
        )
        cv_all = [round(float(v), 4) for v in cv]
        cv_mean = float(cv.mean())
        print(f"5-fold CV: {cv_all} mean={cv_mean:.4f} ({time.time() - t0:.0f}s)")

    out_path = Path(config.SPILL_CLASSIFIER_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "model_type": "HistGradientBoostingClassifier",
        "params": {"max_iter": 350, "learning_rate": 0.08},
        "n_features": int(X.shape[1]),
        "feature_names": feature_names(),
        "n_train": int(len(y_tr)),
        "n_test": int(len(y_te)),
        "holdout_accuracy": round(float(holdout_acc), 4),
        "cv_accuracy_mean": round(cv_mean, 4) if cv_mean is not None else None,
        "cv_folds": cv_all,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(config.SAR_DIR),
        "dataset_size": int(len(y)),
        "class_balance": {"0": int((y == 0).sum()), "1": int((y == 1).sum())},
        "training_script": "backend/train_sar_classifier.py",
        "note": (
            "Trained on the repository's SAR dataset with native-resolution "
            "texture features. The README's claimed CNN never existed in the "
            "repo; see backend/app/ml/features.py for the honest feature set."
        ),
    }
    with open(out_path, "wb") as f:
        pickle.dump({"model": model, "metadata": metadata}, f)
    print(f"Saved model -> {out_path}")

    # quick self-test of the saved artifact
    from app.ml.features import load_model
    m = load_model()
    assert m is not None
    with Image.open(Path(config.SAR_DIR) / files[0]) as im:
        arr = np.asarray(im.convert("L"), dtype=np.float64) / 255.0
    print("Self-test on first image:", m.decision_stats(arr))


if __name__ == "__main__":
    main()
