import logging
import threading
from dataclasses import dataclass
from typing import Dict, List

import mss
from PIL import Image

from src.utils.platform import is_kde_wayland_session

logger = logging.getLogger(__name__)


@dataclass
class MonitorGeometry:
    left: int
    top: int
    width: int
    height: int

    @classmethod
    def from_qrect(cls, qrect) -> "MonitorGeometry":
        return cls(left=qrect.left(), top=qrect.top(), width=qrect.width(), height=qrect.height())

    def to_dict(self) -> Dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


class ScreenshotBackend:
    def list_monitors(self) -> List[Dict[str, int]]:
        raise NotImplementedError

    def capture(self, monitor: Dict[str, int]) -> Image.Image:
        raise NotImplementedError


class MSSBackend(ScreenshotBackend):
    def list_monitors(self) -> List[Dict[str, int]]:
        with mss.mss() as sct:
            return list(sct.monitors)

    def capture(self, monitor: Dict[str, int]) -> Image.Image:
        with mss.mss() as sct:
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")


class _QtCaptureDelegate:
    def __init__(self):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Delegate(QObject):
            requestCapture = pyqtSignal(dict)
            finished = pyqtSignal(object, object)

            def __init__(self):
                super().__init__()
                self.requestCapture.connect(self._capture)

            def _capture(self, monitor: Dict[str, int]):
                from PyQt6.QtGui import QGuiApplication, QImage
                from PyQt6.QtCore import QRect

                try:
                    rect = QRect(monitor["left"], monitor["top"], monitor["width"], monitor["height"])
                    screen = self._screen_for_rect(rect)
                    if screen is None:
                        raise RuntimeError("Unable to find screen for requested capture region")
                    pixmap = screen.grabWindow(0, rect.left(), rect.top(), rect.width(), rect.height())
                    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                    self.finished.emit(image, None)
                except Exception as exc:  # pylint: disable=broad-except
                    self.finished.emit(None, exc)

            @staticmethod
            def _screen_for_rect(rect):
                from PyQt6.QtGui import QGuiApplication

                for screen in QGuiApplication.screens():
                    if screen.geometry().intersects(rect):
                        return screen
                return QGuiApplication.primaryScreen()

        self.obj = _Delegate()


class KDEWaylandBackend(ScreenshotBackend):
    def __init__(self):
        self._delegate = _QtCaptureDelegate().obj

    def list_monitors(self) -> List[Dict[str, int]]:
        from PyQt6.QtGui import QGuiApplication

        screens = QGuiApplication.screens()
        if not screens:
            return [{"left": 0, "top": 0, "width": 0, "height": 0}]

        left = min(screen.geometry().left() for screen in screens)
        top = min(screen.geometry().top() for screen in screens)
        right = max(screen.geometry().right() + 1 for screen in screens)
        bottom = max(screen.geometry().bottom() + 1 for screen in screens)

        monitors = [{"left": left, "top": top, "width": right - left, "height": bottom - top}]
        for screen in screens:
            geo = screen.geometry()
            monitors.append({
                "left": geo.left(),
                "top": geo.top(),
                "width": geo.width(),
                "height": geo.height(),
            })
        return monitors

    def capture(self, monitor: Dict[str, int]) -> Image.Image:
        done = threading.Event()
        result = {"image": None, "error": None}

        def handle_finished(image, error):
            result["image"] = image
            result["error"] = error
            done.set()

        self._delegate.finished.connect(handle_finished)
        self._delegate.requestCapture.emit(monitor)
        if not done.wait(timeout=5):
            self._delegate.finished.disconnect(handle_finished)
            raise TimeoutError("Timed out while waiting for Wayland screenshot result")
        self._delegate.finished.disconnect(handle_finished)

        if result["error"]:
            raise result["error"]

        qimage = result["image"]
        ptr = qimage.bits()
        ptr.setsize(qimage.sizeInBytes())
        data = bytes(ptr)
        pil_image = Image.frombytes(
            "RGBA",
            (qimage.width(), qimage.height()),
            data,
            "raw",
            "RGBA",
            qimage.bytesPerLine(),
        )
        return pil_image.convert("RGB")


def create_backend() -> ScreenshotBackend:
    if is_kde_wayland_session():
        try:
            return KDEWaylandBackend()
        except Exception:  # pylint: disable=broad-except
            logger.exception("Falling back to MSS backend after KDE Wayland backend initialization failed")
    return MSSBackend()
