"""Pytest configuration: path setup + shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


@pytest.fixture(scope="session")
def sar_dataset_available() -> bool:
    from app import config
    return Path(config.SAR_DIR).is_dir()


@pytest.fixture(scope="session")
def ais_available() -> bool:
    try:
        from app.services import ais as aissvc
        aissvc.get_dataframe()
        return True
    except Exception:
        return False
