"""
AIS Data Service — wraps the AIS CSV data and SVR anomaly detection
methodology from the Analysis of AIS Data notebook.

The notebook uses SVR (Support Vector Regression) to predict SOG from
[LAT, hour, Cargo, COG], then flags observations where the prediction
error exceeds a threshold as anomalous.

This service replicates that methodology on the actual repository CSV.
"""

import os
import math
import pandas as pd
import numpy as np
from sklearn.svm import SVR
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score
from functools import lru_cache
from typing import Optional

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data"))

_df: Optional[pd.DataFrame] = None
_anomaly_cache: dict = {}
_analytics_cache: Optional[dict] = None


def _find_ais_csv() -> str:
    """Find the AIS CSV file in the data directory."""
    ais_dir = os.path.join(DATA_DIR, "AIS Dataset")
    if os.path.isdir(ais_dir):
        for f in os.listdir(ais_dir):
            if f.endswith(".csv"):
                return os.path.join(ais_dir, f)
    raise FileNotFoundError(f"No AIS CSV found in {ais_dir}")


def get_dataframe() -> pd.DataFrame:
    """Load and preprocess the AIS CSV. Cached after first load."""
    global _df
    if _df is not None:
        return _df

    csv_path = _find_ais_csv()
    df = pd.read_csv(csv_path)

    # Preprocessing (replicating notebook methodology)
    # 1. Convert BaseDateTime to datetime
    df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"], errors="coerce")

    # 2. Extract time features
    df["Year"] = df["BaseDateTime"].dt.year
    df["Month"] = df["BaseDateTime"].dt.month
    df["Day"] = df["BaseDateTime"].dt.day
    df["Hour"] = df["BaseDateTime"].dt.hour
    df["Minute"] = df["BaseDateTime"].dt.minute

    # 3. Handle missing values via linear interpolation + forward/backward fill
    # (replicating: data.interpolate(method='linear', axis=0).ffill().bfill())
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].interpolate(method="linear", axis=0).ffill().bfill()

    # Fill remaining string NaNs
    string_cols = df.select_dtypes(include=["object"]).columns
    for col in string_cols:
        df[col] = df[col].fillna("Unknown")

    # Sort by vessel and time
    df = df.sort_values(["MMSI", "BaseDateTime"]).reset_index(drop=True)

    _df = df
    return _df


def get_vessels(page: int = 1, page_size: int = 50, search: str = "",
                sort_by: str = "MMSI", sort_order: str = "asc",
                vessel_type: Optional[str] = None) -> dict:
    """Get paginated vessel list with search/filter/sort."""
    df = get_dataframe()

    # Get unique vessels with their latest position
    vessel_groups = df.groupby("MMSI")
    vessels = vessel_groups.agg({
        "VesselName": "first",
        "IMO": "first",
        "CallSign": "first",
        "VesselType": "first",
        "LAT": "last",
        "LON": "last",
        "SOG": "last",
        "COG": "last",
        "Heading": "last",
        "Status": "last",
        "Length": "first",
        "Width": "first",
        "Draft": "first",
        "Cargo": "first",
        "BaseDateTime": "last",
    }).reset_index()

    vessels["ObservationCount"] = vessel_groups.size().values

    # Search
    if search:
        search_lower = search.lower()
        mask = (
            vessels["MMSI"].astype(str).str.contains(search, na=False) |
            vessels["VesselName"].str.lower().str.contains(search_lower, na=False) |
            vessels["IMO"].str.lower().str.contains(search_lower, na=False) |
            vessels["CallSign"].str.lower().str.contains(search_lower, na=False)
        )
        vessels = vessels[mask]

    # Filter by vessel type
    if vessel_type:
        vessels = vessels[vessels["VesselType"].astype(str) == vessel_type]

    # Sort
    ascending = sort_order == "asc"
    if sort_by in vessels.columns:
        vessels = vessels.sort_values(sort_by, ascending=ascending)

    total = len(vessels)
    total_pages = max(1, math.ceil(total / page_size))

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    page_data = vessels.iloc[start:end]

    # Convert BaseDateTime to string for JSON serialization
    records = page_data.to_dict(orient="records")
    for r in records:
        if isinstance(r.get("BaseDateTime"), pd.Timestamp):
            r["BaseDateTime"] = r["BaseDateTime"].isoformat()

    return {
        "vessels": records,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
    }


def get_vessel_types() -> list:
    """Get unique vessel types for filtering."""
    df = get_dataframe()
    types = df["VesselType"].dropna().unique().tolist()
    return sorted([str(t) for t in types])


def get_vessel_track(mmsi: int) -> dict:
    """Get the full track (trajectory) for a specific vessel by MMSI."""
    df = get_dataframe()
    vessel_data = df[df["MMSI"] == mmsi].sort_values("BaseDateTime")

    if vessel_data.empty:
        return {"mmsi": mmsi, "track": [], "info": None}

    # Vessel info from first record
    first = vessel_data.iloc[0]
    info = {
        "mmsi": int(mmsi),
        "vesselName": str(first.get("VesselName", "Unknown")),
        "imo": str(first.get("IMO", "Unknown")),
        "callSign": str(first.get("CallSign", "Unknown")),
        "vesselType": float(first.get("VesselType", 0)),
        "length": float(first.get("Length", 0)),
        "width": float(first.get("Width", 0)),
        "draft": float(first.get("Draft", 0)),
        "cargo": float(first.get("Cargo", 0)),
        "observationCount": len(vessel_data),
    }

    # Track points
    track = []
    for _, row in vessel_data.iterrows():
        track.append({
            "lat": float(row["LAT"]),
            "lon": float(row["LON"]),
            "sog": float(row["SOG"]),
            "cog": float(row["COG"]),
            "heading": float(row["Heading"]),
            "status": str(row.get("Status", "")),
            "timestamp": row["BaseDateTime"].isoformat() if isinstance(row["BaseDateTime"], pd.Timestamp) else str(row["BaseDateTime"]),
        })

    return {"mmsi": int(mmsi), "track": track, "info": info}


def run_anomaly_detection(mmsi: int, threshold: float = 6.0) -> dict:
    """
    Run SVR anomaly detection on a specific vessel.

    Replicates the notebook methodology:
    - Features: [LAT, Hour, Cargo, COG]
    - Target: SOG
    - SVR(gamma='scale', C=100000, epsilon=1, degree=3)
    - Anomaly threshold: |Actual - Predicted| >= threshold
    """
    if mmsi in _anomaly_cache:
        return _anomaly_cache[mmsi]

    df = get_dataframe()
    vessel_data = df[df["MMSI"] == mmsi].copy()

    if len(vessel_data) < 10:
        return {
            "mmsi": int(mmsi),
            "error": "Insufficient data for anomaly detection (need at least 10 observations)",
            "anomalies": [],
            "model_info": None,
        }

    # Replicate notebook feature selection
    features = ["LAT", "Hour", "Cargo", "COG"]
    target = "SOG"

    # Ensure all features exist and are numeric
    for feat in features + [target]:
        vessel_data[feat] = pd.to_numeric(vessel_data[feat], errors="coerce")

    vessel_data = vessel_data.dropna(subset=features + [target])

    if len(vessel_data) < 10:
        return {
            "mmsi": int(mmsi),
            "error": "Insufficient valid data after cleaning",
            "anomalies": [],
            "model_info": None,
        }

    X = vessel_data[features].values
    y = vessel_data[target].values

    # Train/test split (85/15 as in notebook)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=4
    )

    # SVR model (replicating notebook parameters exactly)
    regressor = SVR(gamma="scale", C=100000, epsilon=1, degree=3)
    regressor.fit(X_train, y_train)

    # Predict on ALL data for comprehensive anomaly detection
    y_pred_all = regressor.predict(X.copy())
    differences = np.round(y - y_pred_all, 0)

    # Also compute test metrics
    y_pred_test = regressor.predict(X_test)
    r2 = round(r2_score(y_test, y_pred_test), 4)

    # Identify anomalies (replicating notebook: |difference| >= threshold)
    anomaly_mask = np.abs(differences) >= threshold
    anomaly_indices = np.where(anomaly_mask)[0]

    anomalies = []
    for idx in anomaly_indices:
        row = vessel_data.iloc[idx]
        anomalies.append({
            "lat": float(row["LAT"]),
            "lon": float(row["LON"]),
            "sog": float(row["SOG"]),
            "predictedSog": round(float(y_pred_all[idx]), 1),
            "difference": float(differences[idx]),
            "cog": float(row["COG"]),
            "heading": float(row["Heading"]),
            "timestamp": row["BaseDateTime"].isoformat() if isinstance(row["BaseDateTime"], pd.Timestamp) else str(row["BaseDateTime"]),
            "status": str(row.get("Status", "")),
        })

    result = {
        "mmsi": int(mmsi),
        "anomalies": anomalies,
        "totalObservations": len(vessel_data),
        "anomalyCount": len(anomalies),
        "threshold": threshold,
        "model_info": {
            "type": "SVR",
            "features": features,
            "target": target,
            "params": {"gamma": "scale", "C": 100000, "epsilon": 1, "degree": 3},
            "r2Score": r2,
            "trainSize": len(X_train),
            "testSize": len(X_test),
            "methodology": "Replicates notebook SVR approach: predicts SOG from [LAT, Hour, Cargo, COG], flags deviations >= threshold as anomalous",
        },
    }

    _anomaly_cache[mmsi] = result
    return result


def get_all_anomalies(threshold: float = 6.0, max_vessels: int = 20) -> dict:
    """Run anomaly detection across top vessels (by observation count)."""
    df = get_dataframe()
    top_mmsis = df["MMSI"].value_counts().head(max_vessels).index.tolist()

    all_anomalies = []
    vessel_results = []

    for mmsi in top_mmsis:
        result = run_anomaly_detection(int(mmsi), threshold)
        if result.get("anomalies"):
            vessel_results.append({
                "mmsi": int(mmsi),
                "vesselName": df[df["MMSI"] == mmsi]["VesselName"].iloc[0],
                "anomalyCount": result["anomalyCount"],
                "totalObservations": result["totalObservations"],
                "r2Score": result["model_info"]["r2Score"] if result.get("model_info") else None,
            })
            all_anomalies.extend(result["anomalies"])

    return {
        "vessels": vessel_results,
        "allAnomalies": all_anomalies,
        "threshold": threshold,
        "vesselsAnalyzed": len(top_mmsis),
    }


def get_analytics() -> dict:
    """Compute analytics replicating notebook EDA insights."""
    global _analytics_cache
    if _analytics_cache is not None:
        return _analytics_cache

    df = get_dataframe()

    # Basic stats
    total_records = len(df)
    unique_vessels = df["MMSI"].nunique()
    date_range = {
        "start": df["BaseDateTime"].min().isoformat() if pd.notna(df["BaseDateTime"].min()) else None,
        "end": df["BaseDateTime"].max().isoformat() if pd.notna(df["BaseDateTime"].max()) else None,
    }
    geo_bounds = {
        "latMin": float(df["LAT"].min()),
        "latMax": float(df["LAT"].max()),
        "lonMin": float(df["LON"].min()),
        "lonMax": float(df["LON"].max()),
    }

    # Speed distribution (SOG)
    sog_stats = {
        "mean": round(float(df["SOG"].mean()), 2),
        "median": round(float(df["SOG"].median()), 2),
        "std": round(float(df["SOG"].std()), 2),
        "min": round(float(df["SOG"].min()), 2),
        "max": round(float(df["SOG"].max()), 2),
        "mode": round(float(df["SOG"].mode().iloc[0]), 2) if not df["SOG"].mode().empty else None,
    }

    # SOG distribution histogram
    sog_hist_values, sog_hist_edges = np.histogram(
        df["SOG"].dropna().clip(-5, 30), bins=20
    )
    sog_distribution = [
        {"range": f"{round(sog_hist_edges[i], 1)}-{round(sog_hist_edges[i+1], 1)}",
         "count": int(sog_hist_values[i])}
        for i in range(len(sog_hist_values))
    ]

    # Vessel type distribution
    vtype_counts = df.groupby("VesselType")["MMSI"].nunique().reset_index()
    vtype_counts.columns = ["vesselType", "count"]
    vessel_type_distribution = vtype_counts.to_dict(orient="records")

    # Observations per vessel (top 20)
    obs_per_vessel = df["MMSI"].value_counts().head(20)
    vessel_activity = [
        {"mmsi": int(mmsi), "vesselName": str(df[df["MMSI"] == mmsi]["VesselName"].iloc[0]),
         "observations": int(count)}
        for mmsi, count in obs_per_vessel.items()
    ]

    # Correlations (replicating notebook analysis)
    correlations = {
        "sogVesselType": round(float(df["SOG"].corr(df["VesselType"])), 4),
        "cogVesselType": round(float(df["COG"].corr(df["VesselType"])), 4),
        "lengthSog": round(float(df["Length"].corr(df["SOG"])), 4),
        "lengthCog": round(float(df["Length"].corr(df["COG"])), 4),
        "widthSog": round(float(df["Width"].corr(df["SOG"])), 4),
        "widthCog": round(float(df["Width"].corr(df["COG"])), 4),
    }

    # Average track length (mode as in notebook)
    avg_track_length = round(float(df["Length"].mode().iloc[0]), 2) if not df["Length"].mode().empty else None

    # Status distribution
    status_counts = df["Status"].value_counts().to_dict()
    status_distribution = [{"status": str(k), "count": int(v)} for k, v in status_counts.items()]

    # Hourly activity
    hourly = df.groupby("Hour").size().reset_index(name="count")
    hourly_activity = [{"hour": int(r["Hour"]), "count": int(r["count"])} for _, r in hourly.iterrows()]

    _analytics_cache = {
        "totalRecords": total_records,
        "uniqueVessels": unique_vessels,
        "dateRange": date_range,
        "geoBounds": geo_bounds,
        "sogStats": sog_stats,
        "sogDistribution": sog_distribution,
        "vesselTypeDistribution": vessel_type_distribution,
        "vesselActivity": vessel_activity,
        "correlations": correlations,
        "avgTrackLength": avg_track_length,
        "statusDistribution": status_distribution,
        "hourlyActivity": hourly_activity,
    }
    return _analytics_cache


def get_overview_stats() -> dict:
    """Get high-level stats for the overview dashboard."""
    df = get_dataframe()
    analytics = get_analytics()

    return {
        "totalVessels": analytics["uniqueVessels"],
        "totalObservations": analytics["totalRecords"],
        "dateRange": analytics["dateRange"],
        "geoBounds": analytics["geoBounds"],
        "avgSpeed": analytics["sogStats"]["mean"],
        "dataSource": "AIS Repository Dataset",
    }
