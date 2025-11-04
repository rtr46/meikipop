# src/ocr/ocr.py
import importlib
import inspect
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Type, Optional

from src.config.config import config
from src.ocr.interface import OcrProvider
from src.ocr.providers.glensv2 import GoogleLensOcrV2

logger = logging.getLogger(__name__)  # Get the logger

class OcrProcessor(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="OcrProcessor")
        self.shared_state = shared_state
        self.ocr_backend: Optional[OcrProvider] = None

        self.available_providers = self._discover_providers()
        if not self.available_providers:
            logger.critical("No OCR providers found! The application cannot continue.")
            sys.exit(1)

        self._load_provider_from_config()

    def run(self):
        logger.debug("OCR thread started.")
        while self.shared_state.running:
            try:
                screenshot = self.shared_state.ocr_queue.get()
                if not self.shared_state.running: break

                logger.debug("OCR: Triggered!")

                start_time = time.perf_counter()
                ocr_result = self.ocr_backend.scan(screenshot)
                logger.info(
                    f"{self.ocr_backend.NAME} found {len(ocr_result) if ocr_result else 0} paragraphs in {(time.perf_counter() - start_time):.3f}s.")
                # todo keep last ocr result?

                self.shared_state.hit_scan_queue.put((True, ocr_result))
            except:
                logger.exception("An unexpected error occurred in the ocr loop. Continuing...")
            finally:
                if config.auto_scan_mode:
                    self.shared_state.screenshot_trigger_event.set()
        logger.debug("OCR thread stopped.")

    # todo combine methods?
    def switch_provider(self, provider_name: str):
        if self.ocr_backend and provider_name == self.ocr_backend.NAME:
            return

        if provider_name in self.available_providers:
            logger.info(f"Switching OCR provider to '{provider_name}'...")
            provider_class = self.available_providers[provider_name]
            try:
                self.ocr_backend = provider_class()
                logger.info(f"Successfully switched OCR provider to '{self.ocr_backend.NAME}'")
                if config.auto_scan_mode:
                    self.shared_state.hit_scan_queue.put((True, None))
                    self.shared_state.screenshot_trigger_event.set()
            except Exception as e:
                logger.error(f"Failed to instantiate provider '{provider_name}': {e}", exc_info=True)
                self.ocr_backend = None
        else:
            logger.error(f"Attempted to switch to an unknown provider: '{provider_name}'")

    def _load_provider_from_config(self):
        configured_provider_name = config.ocr_provider
        default_provider_name = GoogleLensOcrV2.NAME

        provider_to_load_name = configured_provider_name

        if configured_provider_name not in self.available_providers:
            logger.warning(
                f"Configured OCR provider '{configured_provider_name}' not found. "
                f"Falling back to default provider '{default_provider_name}'."
            )
            provider_to_load_name = default_provider_name

        if provider_to_load_name not in self.available_providers:
            fallback_provider_name = list(self.available_providers.keys())[0]
            logger.warning(
                f"Default OCR provider '{provider_to_load_name}' not found. "
                f"Falling back to first available provider: '{fallback_provider_name}'."
            )
            provider_to_load_name = fallback_provider_name

        config.ocr_provider = provider_to_load_name

        provider_class = self.available_providers[provider_to_load_name]
        try:
            self.ocr_backend = provider_class()
            logger.info(f"Initialized OCR with '{self.ocr_backend.NAME}' provider.")
        except Exception as e:
            logger.critical(f"Failed to instantiate provider '{provider_to_load_name}' on startup: {e}", exc_info=True)
            self.ocr_backend = None
            sys.exit(1)

    def _discover_providers(self) -> Dict[str, Type[OcrProvider]]:
        providers: Dict[str, Type[OcrProvider]] = {}
        providers_path = Path(__file__).parent / "providers" if getattr(sys, 'frozen', True) else Path(
            sys._MEIPASS) / "src" / "ocr" / "providers"

        logger.debug(f"Scanning for providers in: {providers_path}")
        for subdir in providers_path.iterdir():
            if subdir.is_dir() and (subdir / "__init__.py").exists():
                provider_name = subdir.name
                try:
                    module_name = f"src.ocr.providers.{provider_name}"
                    provider_module = importlib.import_module(module_name)
                    logger.debug(f"Found potential provider package: '{provider_name}'")

                    for _, obj_class in inspect.getmembers(provider_module, inspect.isclass):
                        if issubclass(obj_class,
                                      OcrProvider) and obj_class is not OcrProvider and not inspect.isabstract(
                            obj_class):
                            providers[obj_class.NAME] = obj_class
                            logger.debug(f" -> Discovered provider: '{obj_class.NAME}'")

                except ImportError as e:
                    logger.warning(f"Could not import or inspect provider '{provider_name}': {e}")
        return providers
