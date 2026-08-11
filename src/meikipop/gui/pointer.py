"""Pointer position backends for X11 and Wayland compositors."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Protocol

logger = logging.getLogger(__name__)


class PointerBackend(Protocol):
    def position(self) -> tuple[int, int]: ...


class PynputPointerBackend:
    def __init__(self):
        from pynput import mouse

        self._controller = mouse.Controller()

    def position(self) -> tuple[int, int]:
        x, y = self._controller.position
        return int(x), int(y)


class HyprlandPointerBackend:
    """Read compositor-global cursor coordinates through Hyprland's IPC CLI."""

    def __init__(self, command: str = "hyprctl", minimum_interval: float = 1 / 60):
        self.command = command
        self.minimum_interval = minimum_interval
        self._last_position: tuple[int, int] | None = None
        self._last_read = 0.0
        self._lock = threading.Lock()

    def position(self) -> tuple[int, int]:
        with self._lock:
            now = time.monotonic()
            if self._last_position is not None and now - self._last_read < self.minimum_interval:
                return self._last_position

            try:
                result = subprocess.run(
                    [self.command, "-j", "cursorpos"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=0.25,
                )
                payload = json.loads(result.stdout)
                position = int(payload["x"]), int(payload["y"])
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                if self._last_position is not None:
                    logger.debug("Hyprland cursor query failed; using the last position: %s", error)
                    return self._last_position
                raise RuntimeError(f"Unable to query Hyprland cursor position: {error}") from error

            self._last_position = position
            self._last_read = now
            return position


def create_pointer_backend() -> PointerBackend:
    is_wayland = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(
        os.environ.get("WAYLAND_DISPLAY")
    )
    if is_wayland and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
        logger.info("Using the native Hyprland cursor-position backend")
        return HyprlandPointerBackend()
    if is_wayland:
        logger.warning(
            "No native cursor backend is available for this Wayland compositor; "
            "falling back to XWayland pointer coordinates."
        )
    return PynputPointerBackend()


_backend: PointerBackend | None = None
_backend_lock = threading.Lock()


def get_pointer_position() -> tuple[int, int]:
    global _backend
    with _backend_lock:
        if _backend is None:
            _backend = create_pointer_backend()
        backend = _backend
    return backend.position()
