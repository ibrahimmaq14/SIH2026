"""JSON-file-backed persistence for pipeline runs (no database required)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .. import config

logger = logging.getLogger("app.db.store")


def _runs_dir() -> Path:
    d = Path(config.RUNS_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(run_id: str, payload: dict[str, Any]) -> Path:
    path = _runs_dir() / f"{run_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def load_run(run_id: str) -> Optional[dict[str, Any]]:
    # sanitize run_id: only [a-zA-Z0-9_-]
    if not run_id.replace("-", "").replace("_", "").isalnum():
        return None
    path = _runs_dir() / f"{run_id}.json"
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    out = []
    for p in sorted(_runs_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            with open(p, "r", encoding="utf-8") as f:
                run = json.load(f)
            det = run.get("detection", {})
            attr = run.get("attribution", {})
            cands = attr.get("candidates") or []
            hc = run.get("hindcast", {}) or {}
            out.append(
                {
                    "run_id": run.get("run_id", p.stem),
                    "created_at": run.get("created_at"),
                    "status": run.get("status", "unknown"),
                    "detected": det.get("detected", False),
                    "confidence": det.get("confidence"),
                    "origin_lat": (hc.get("origin_location") or {}).get("lat"),
                    "origin_lon": (hc.get("origin_location") or {}).get("lon"),
                    "candidate_count": len(cands),
                    "top_mmsi": cands[0]["mmsi"] if cands else None,
                    "top_score": cands[0]["score"] if cands else None,
                }
            )
        except (OSError, json.JSONDecodeError):
            continue
    return out
