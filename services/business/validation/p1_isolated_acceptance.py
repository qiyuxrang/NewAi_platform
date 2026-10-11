"""Recovered non-overwriting private-file utilities; no legacy DB orchestration."""
import hashlib
import shutil
from .private_path_safety import checked_path, regular_files

def sha256_file(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()

def file_state(root):
    state = {}
    root = checked_path(root)
    if not root.is_dir():
        return state
    for path in regular_files(root):
        state[path.relative_to(root).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return state

def copy_private_files(source, destination):
    """Preflight the complete private tree before non-overwriting copytree."""
    source = checked_path(source, must_exist=True)
    destination = checked_path(destination)
    before = file_state(source)
    shutil.copytree(source, destination, copy_function=shutil.copy2)
    if before != file_state(source):
        raise ValueError("Private source changed during backup copy")
    return before
