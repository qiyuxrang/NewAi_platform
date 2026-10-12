"""Private, hash-bound checkpoints; deliberately independent of Django and DB."""
import hashlib
import json
import os
import uuid
from pathlib import Path


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def confined(root, relative):
    """Reject absolute paths, traversal, symlinks and Windows junctions."""
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or any(part in {".", ".."} for part in relative.parts):
        raise ValueError("unsafe cache path")
    target = root / relative
    for item in (target, *target.parents):
        if item == root:
            break
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("unsafe cache path")
    if not target.resolve().is_relative_to(root):
        raise ValueError("unsafe cache path")
    return target


def atomic_write(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class StageCache:
    def __init__(self, directory, binding):
        self.directory = Path(directory).resolve()
        self.binding = binding

    def _root(self, stage):
        if stage not in {"assembled", "normalized", "office"}:
            raise ValueError("invalid stage")
        return confined(self.directory, f".stage-cache/{stage}")

    def save(self, stage, files, evidence):
        root = self._root(stage)
        root.mkdir(parents=True, exist_ok=True)
        hashes = {}
        for name in files:
            source = confined(self.directory, name)
            snapshot = confined(root, name)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            atomic_write(snapshot, data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        atomic_write(confined(root, "checkpoint.json"), json.dumps({
            "version": 1, "binding": self.binding, "files": hashes, "evidence": evidence,
            "evidence_sha256": canonical_hash(evidence),
        }, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode())

    def load(self, stage, files):
        try:
            root = self._root(stage)
            value = json.loads(confined(root, "checkpoint.json").read_bytes())
            if (value.get("version") != 1 or value.get("binding") != self.binding
                    or set(value["files"]) != set(files) or not isinstance(value["evidence"], dict)
                    or canonical_hash(value["evidence"]) != value.get("evidence_sha256")):
                return None
            evidence = value["evidence"]
            if stage in {"normalized", "office"} and not isinstance(evidence.get("layout"), dict):
                return None
            if stage == "office" and (not isinstance(evidence.get("field_refresh"), dict)
                    or evidence["field_refresh"].get("status") not in {"completed", "not_run"}):
                return None
            snapshots = {}
            for name in files:
                data = confined(root, name).read_bytes()
                if hashlib.sha256(data).hexdigest() != value["files"][name]:
                    return None
                snapshots[name] = data
            for name, data in snapshots.items():
                target = confined(self.directory, name)
                atomic_write(target, data)
            return value["evidence"]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
