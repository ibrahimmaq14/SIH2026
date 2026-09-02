"""Tests for environmental providers and labelling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import environment as envsvc


def test_demo_provider_labels_synthetic():
    start = datetime(2021, 2, 1, 12, 0, tzinfo=timezone.utc)
    series = envsvc.DemoEnvironmentProvider().get_series(
        28.5, -94.9, start, start + timedelta(hours=5), step_minutes=60
    )
    assert series.dataClass == "synthetic"
    assert all(s.dataClass == "synthetic" for s in series.samples)
    assert "SYNTHETIC" in series.note
    assert len(series.samples) == 6
    for s in series.samples:
        assert s.current_speed_kmh > 0
        assert 0 <= s.current_direction_deg < 360
        assert s.wind_speed_kmh > 0


def test_demo_provider_deterministic():
    start = datetime(2021, 2, 1, 12, 0, tzinfo=timezone.utc)
    s1 = envsvc.DemoEnvironmentProvider().get_series(28.5, -94.9, start, start + timedelta(hours=2), 60)
    s2 = envsvc.DemoEnvironmentProvider().get_series(28.5, -94.9, start, start + timedelta(hours=2), 60)
    assert [s.timestamp for s in s1.samples] == [s.timestamp for s in s2.samples]
    assert [s.current_speed_kmh for s in s1.samples] == [s.current_speed_kmh for s in s2.samples]


def test_sample_at_nearest():
    start = datetime(2021, 2, 1, 12, 0, tzinfo=timezone.utc)
    series = envsvc.DemoEnvironmentProvider().get_series(
        28.5, -94.9, start, start + timedelta(hours=4), 60
    )
    mid = start + timedelta(hours=2, minutes=10)
    s = envsvc.sample_at(series, mid)
    assert abs(datetime.fromisoformat(s.timestamp.replace("Z", "+00:00")) - start - timedelta(hours=2)).total_seconds() < 3600
