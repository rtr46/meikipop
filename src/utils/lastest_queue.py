# src/utils/latest_queue.py
import threading


class LatestValueQueue():
    def __init__(self):
        self._value = None
        self._lock = threading.Lock()
        self._event = threading.Event()

    def put(self, item):
        with self._lock:
            self._value = item
            self._event.set()

    def get(self):
        self._event.wait()
        with self._lock:
            value = self._value
            self._event.clear()
            return value
