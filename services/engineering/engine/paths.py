"""Operator-configured data directory; code and business rules stay in the deployment."""
import os
from pathlib import Path


def data_path(*parts):
    configured = os.environ.get("ENGINEERING_DATA_ROOT", "").strip()
    root = Path(configured).expanduser() if configured else Path(__file__).resolve().parents[1] / "data"
    if not root.is_absolute():
        raise ValueError("ENGINEERING_DATA_ROOT must be an absolute path")
    return str(root.joinpath(*parts))
