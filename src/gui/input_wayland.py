import logging
import threading
import uuid
from typing import Optional

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtDBus import (
    QDBusConnection,
    QDBusInterface,
    QDBusMessage,
    QDBusObjectPath,
)

logger = logging.getLogger(__name__)


class _PortalRequest(QObject):
    def __init__(self, connection: QDBusConnection, handle_path: str, callback):
        super().__init__()
        self._connection = connection
        self._handle_path = handle_path
        self._callback = callback
        self._connected = self._connection.connect(
            "org.freedesktop.portal.Desktop",
            handle_path,
            "org.freedesktop.portal.Request",
            "Response",
            self._on_response,
        )
        if not self._connected:
            raise RuntimeError("Failed to subscribe to portal response signal")

    def _on_response(self, response: int, results: dict):
        self._connection.disconnect(
            "org.freedesktop.portal.Desktop",
            self._handle_path,
            "org.freedesktop.portal.Request",
            "Response",
            self._on_response,
        )
        self._callback(response, results)
        self.deleteLater()


def _as_handle_token(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _preferred_trigger(hotkey: str) -> str:
    mapping = {
        "shift": "Shift_L",
        "ctrl": "Control_L",
        "alt": "Alt_L",
        "win": "Super_L",
        "super": "Super_L",
    }
    return mapping.get(hotkey.lower(), hotkey)


class KDEWaylandKeyboardController:
    def __init__(self, hotkey_str: str):
        self.hotkey_str = hotkey_str
        self._pressed = False
        self._ready = threading.Event()
        self._bus = QDBusConnection.sessionBus()
        if not self._bus.isConnected():
            raise RuntimeError("D-Bus session bus is not available")
        self._portal = QDBusInterface(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.GlobalShortcuts",
            self._bus,
        )
        if not self._portal.isValid():
            raise RuntimeError("GlobalShortcuts portal is unavailable")

        self._session_handle: Optional[str] = None
        self._subscription_connected = False
        QTimer.singleShot(0, self._begin_session)

    def _begin_session(self):
        try:
            options = {
                "handle_token": _as_handle_token("meikipop_shortcuts_request"),
                "session_handle_token": _as_handle_token("meikipop_shortcuts_session"),
            }
            reply = self._portal.call("CreateSession", options)
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                raise RuntimeError(reply.errorMessage())
            handle_path = reply.arguments()[0].path()
        except Exception as exc:  # pylint: disable=broad-except
            logger.critical("GlobalShortcuts CreateSession failed: %s", exc)
            self._ready.set()
            return

        def handle_response(response_code: int, results: dict):
            if response_code != 0:
                error = results.get("error") or "unknown error"
                logger.critical("GlobalShortcuts CreateSession denied: %s", error)
                self._ready.set()
                return
            self._session_handle = results.get("session_handle")
            if not self._session_handle:
                logger.critical("GlobalShortcuts session handle missing in response")
                self._ready.set()
                return
            self._bind_shortcut()

        _PortalRequest(self._bus, handle_path, handle_response)

    def _bind_shortcut(self):
        if not self._session_handle:
            return
        shortcut_id = "primary"
        trigger = _preferred_trigger(self.hotkey_str)
        shortcuts = [(shortcut_id, {
            "description": "Meikipop dictionary trigger",
            "preferred_trigger": trigger,
        })]
        options = {
            "handle_token": _as_handle_token("meikipop_shortcuts_bind"),
            "session_handle": QDBusObjectPath(self._session_handle),
        }
        try:
            reply = self._portal.call("BindShortcuts", options, shortcuts, "")
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                raise RuntimeError(reply.errorMessage())
            handle_path = reply.arguments()[0].path()
        except Exception as exc:  # pylint: disable=broad-except
            logger.critical("GlobalShortcuts BindShortcuts failed: %s", exc)
            self._ready.set()
            return

        def handle_response(response_code: int, results: dict):
            if response_code != 0:
                error = results.get("error") or "unknown error"
                logger.critical("GlobalShortcuts BindShortcuts denied: %s", error)
                self._ready.set()
                return
            self._subscribe_signals()
            self._ready.set()

        _PortalRequest(self._bus, handle_path, handle_response)

    def _subscribe_signals(self):
        if self._subscription_connected or not self._session_handle:
            return

        def on_activated(session_handle: QDBusObjectPath, shortcut_id: str, timestamp: int, options: dict):  # noqa: ARG001
            if session_handle.path() == self._session_handle:
                self._pressed = True

        def on_deactivated(session_handle: QDBusObjectPath, shortcut_id: str, timestamp: int, options: dict):  # noqa: ARG001
            if session_handle.path() == self._session_handle:
                self._pressed = False

        activated_connected = self._bus.connect(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.GlobalShortcuts",
            "Activated",
            on_activated,
        )
        deactivated_connected = self._bus.connect(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.GlobalShortcuts",
            "Deactivated",
            on_deactivated,
        )
        self._subscription_connected = activated_connected and deactivated_connected
        if not self._subscription_connected:
            logger.critical("Failed to subscribe to GlobalShortcuts signals")
            self._ready.set()

    def is_hotkey_pressed(self) -> bool:
        self._ready.wait(timeout=1)
        return self._pressed

    def close(self):
        if not self._session_handle:
            return
        session_iface = QDBusInterface(
            "org.freedesktop.portal.Desktop",
            self._session_handle,
            "org.freedesktop.portal.Session",
            self._bus,
        )
        if session_iface.isValid():
            session_iface.call("Close")

    def __del__(self):
        try:
            self.close()
        except Exception:  # pylint: disable=broad-except
            pass
