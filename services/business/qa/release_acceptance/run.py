"""Recovered strict pool-evidence validator; not a live pressure-test claim."""
import importlib.metadata
import math

def validate_database_pool_identity(identity):
    """Reject an unpooled PostgreSQL fixture or invented/unsafe pool evidence."""
    from config.database import CONNECT_TIMEOUT_SECONDS, POOL_OPTIONS, POOL_STATS
    evidence = identity.get("database_pool")
    if identity.get("database_kind") not in ("sqlite", "postgresql"):
        raise ValueError("fixture_database_pool_identity_mismatch")
    if identity.get("database_kind") != "postgresql":
        if evidence != {"enabled": False, "scope": "not_postgresql"}:
            raise ValueError("fixture_database_pool_identity_mismatch")
        return
    expected = {"enabled": True, "scope": "per_process", "implementation": "django_psycopg3",
                "version": importlib.metadata.version("psycopg-pool"),
                "min_size": POOL_OPTIONS["min_size"], "max_size": POOL_OPTIONS["max_size"],
                "timeout_seconds": POOL_OPTIONS["timeout"], "max_waiting": POOL_OPTIONS["max_waiting"],
                "conn_max_age": 0, "health_checks": True,
                "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS}
    if not isinstance(evidence, dict) or set(evidence) != set(expected) | {"stats"} or \
            any(evidence.get(key) != value or type(evidence.get(key)) is not type(value)
                for key, value in expected.items()):
        raise ValueError("fixture_database_pool_identity_mismatch")
    stats = evidence["stats"]
    if not isinstance(stats, dict) or set(stats) - set(POOL_STATS) or \
            any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in stats.values()) or \
            stats.get("pool_min") != 1 or stats.get("pool_max") != 4 or \
            type(stats.get("pool_size")) is not int or not 1 <= stats["pool_size"] <= 4 or \
            type(stats.get("pool_available")) is not int or not 0 <= stats["pool_available"] <= stats["pool_size"] or \
            type(stats.get("requests_waiting")) is not int or not 0 <= stats["requests_waiting"] <= 16:
        raise ValueError("fixture_database_pool_identity_mismatch")
