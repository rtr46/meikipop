import os


def is_wayland_session() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def is_kde_desktop() -> bool:
    current = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    session = os.environ.get("XDG_SESSION_DESKTOP", "").lower()
    full_session = os.environ.get("KDE_FULL_SESSION", "").lower()
    return any(token in current for token in ("kde", "plasma")) or \
        any(token in session for token in ("kde", "plasma")) or full_session == "true"


def is_kde_wayland_session() -> bool:
    return is_wayland_session() and is_kde_desktop()
