"""Small helpers for talking to Hyprland's IPC socket.

Inside the Flatpak sandbox ``hyprctl`` is not available, but the compositor's
Unix socket is (read-only) when ``--filesystem=xdg-run/hypr:ro`` is granted.
These helpers let both the capture backend and the input loop use the
compositor's authoritative monitor layout and cursor position instead of
XWayland's, which does not match Hyprland's multi-monitor coordinates.
"""
import json
import logging
import os
import socket

logger = logging.getLogger(__name__)


def _socket_path():
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    runtime_dir = os.environ.get('XDG_RUNTIME_DIR')
    if not signature or not runtime_dir:
        return None
    return os.path.join(runtime_dir, 'hypr', signature, '.socket.sock')


def request(command: str, timeout: float = 1.0):
    """Send a raw command to Hyprland and return the reply as text."""
    path = _socket_path()
    if not path or not os.path.exists(path):
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(path)
            sock.sendall(command.encode('utf-8'))
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        return b''.join(chunks).decode('utf-8', errors='replace')
    except Exception:
        logger.debug("Hyprland IPC request %r failed", command, exc_info=True)
        return None


def get_monitors():
    """Return Hyprland's monitor list, or None when the IPC is unavailable."""
    reply = request('j/monitors')
    if not reply:
        return None
    try:
        monitors = json.loads(reply)
    except (TypeError, ValueError):
        logger.debug("Could not parse Hyprland monitor reply: %r", reply[:200])
        return None
    return monitors if isinstance(monitors, list) else None


def get_cursor_pos():
    """Return the compositor's global cursor position, or None."""
    reply = request('cursorpos')
    if not reply:
        return None
    try:
        x, y = reply.strip().split(',')
        return int(x.strip()), int(y.strip())
    except (TypeError, ValueError):
        return None


def available():
    return _socket_path() is not None and os.path.exists(_socket_path())
