"""Run with: .runtime/python/Scripts/python.exe platform/tests/test_container_host_access.py"""

from pathlib import Path
import asyncio
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from docker.errors import ImageNotFound

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.container import manager


def test_container_host_access():
    container = SimpleNamespace(attrs={"NetworkSettings": {
        "Networks": {"unrelated": {"IPAddress": "172.20.0.9"}, "pilot": {"IPAddress": "172.21.0.2"}},
        "Ports": {"18080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "43123"}]},
    }})
    with patch.object(manager, "settings", SimpleNamespace(container_host_access=False, container_network="pilot")):
        assert manager._container_endpoint(container) == ("172.21.0.2", 18080)
    with patch.object(manager, "settings", SimpleNamespace(container_host_access=True)):
        assert manager._container_endpoint(container) == ("127.0.0.1", 43123)
        for bindings in ([], [{"HostIp": "0.0.0.0", "HostPort": "43123"}]):
            container.attrs["NetworkSettings"]["Ports"]["18080/tcp"] = bindings
            try:
                manager._container_endpoint(container)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Missing or public Bridge binding must not be accepted")


def test_missing_image_fails_before_db_and_keeps_loop_responsive():
    async def check():
        loop_thread = threading.get_ident()
        db = SimpleNamespace(execute=AsyncMock())
        client = Mock()

        def missing_image(_image):
            assert threading.get_ident() != loop_thread
            time.sleep(0.15)
            raise ImageNotFound("Local runtime image is not built")

        client.images.get.side_effect = missing_image
        with patch.object(manager, "_docker", return_value=client), patch.object(manager, "settings", SimpleNamespace(openclaw_image="pilot:fixed")):
            pending = asyncio.create_task(manager.create_container(db, "user-id"))
            await asyncio.sleep(0.03)
            assert not pending.done(), "Docker calls must not block the event loop"
            try:
                await pending
            except ImageNotFound:
                pass
            else:
                raise AssertionError("Missing local image must fail before creating a DB record")
        db.execute.assert_not_awaited()
        client.containers.create.assert_not_called()
        client.images.pull.assert_not_called()

    asyncio.run(check())


def test_container_creation_never_pulls_images():
    client = Mock()
    client.containers.create.side_effect = ImageNotFound("Image removed after initial local check")
    try:
        manager._create_and_start(client, {"image": "pilot:fixed", "detach": True})
    except ImageNotFound:
        pass
    else:
        raise AssertionError("Container creation must not pull a missing private image")
    client.images.pull.assert_not_called()


if __name__ == "__main__":
    test_container_host_access()
    test_missing_image_fails_before_db_and_keeps_loop_responsive()
    test_container_creation_never_pulls_images()
    print("Container endpoint checks passed")
