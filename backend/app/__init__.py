"""
Oil Spill Detection — backend application package.

Structure:
- app.config          : settings (env-driven, no hardcoded absolute paths)
- app.core.geo        : geographic math (haversine, bearing, destination)
- app.schemas         : Pydantic API contracts
- app.services.*      : detection, characterization, environment, drift,
                        AIS trajectories, anomaly, attribution, pipeline
- app.api.*           : FastAPI routers
- app.ml              : feature extraction, training, model persistence
- app.db.store        : JSON-file-backed run persistence (no Mongo required)
"""

__version__ = "2.0.0"
