from __future__ import annotations

import json
from types import SimpleNamespace

from meikipop.gui import pointer


def test_hyprland_backend_reads_json_position(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps({"x": 123, "y": 456}))

    monkeypatch.setattr(pointer.subprocess, "run", fake_run)
    backend = pointer.HyprlandPointerBackend(minimum_interval=0)

    assert backend.position() == (123, 456)
    assert calls[0][0] == ["hyprctl", "-j", "cursorpos"]
    assert calls[0][1]["timeout"] == 0.25


def test_hyprland_backend_uses_last_position_after_transient_failure(monkeypatch):
    failure = object()
    results = iter(
        [
            SimpleNamespace(stdout=json.dumps({"x": 50, "y": 60})),
            failure,
        ]
    )

    def fake_run(*_args, **_kwargs):
        result = next(results)
        if result is failure:
            raise TimeoutError("hyprctl stalled")
        return result

    monkeypatch.setattr(pointer.subprocess, "run", fake_run)
    backend = pointer.HyprlandPointerBackend(minimum_interval=0)

    assert backend.position() == (50, 60)
    assert backend.position() == (50, 60)


def test_factory_selects_hyprland_on_hyprland_wayland(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test-instance")
    monkeypatch.setattr(pointer.shutil, "which", lambda command: "/usr/bin/hyprctl" if command == "hyprctl" else None)

    assert isinstance(pointer.create_pointer_backend(), pointer.HyprlandPointerBackend)
