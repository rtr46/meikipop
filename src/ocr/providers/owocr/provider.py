import io
import json
import logging
from typing import List, Optional

from PIL import Image
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.sync.client import connect, ClientConnection

from src.ocr.interface import OcrProvider, Paragraph, Word, BoundingBox
from src.ocr.providers.postprocessing import group_lines_into_paragraphs

logger = logging.getLogger(__name__)

# Use the direct IP to avoid localhost resolution delays
OWOCR_WEBSOCKET_URI = "ws://127.0.0.1:7331"


class OwocrWebsocketProvider(OcrProvider):
    """
    An OCR provider that connects to a running owocr instance via websockets.
    This provider uses the synchronous websockets client to maintain a
    persistent connection.
    """
    NAME = "owocr (Websocket)"

    def __init__(self):
        super().__init__()
        self.websocket: Optional[ClientConnection] = None
        self._connection_error_logged = False

    def _connect(self) -> bool:
        """
        Establishes a new websocket connection and stores it.
        """
        try:
            self.websocket = connect(
                OWOCR_WEBSOCKET_URI,
                open_timeout=3,
                ping_interval=20,
                ping_timeout=20
            )
            self._connection_error_logged = False
            logger.info("Successfully connected to owocr websocket server.")
            return True
        except Exception as e:
            if not self._connection_error_logged:
                logger.error(f"Could not connect to owocr at {OWOCR_WEBSOCKET_URI}: {e}")
                logger.info("Please ensure owocr is running with a command like:")
                logger.info("owocr -r websocket -w websocket -of json -e glens")
                self._connection_error_logged = True
            self.websocket = None
            return False

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        for attempt in range(2):
            try:
                if self.websocket is None:
                    if not self._connect():
                        return None

                # 1. Prepare and send the image
                with io.BytesIO() as buffer:
                    image.save(buffer, format="BMP")
                    self.websocket.send(buffer.getvalue())

                # 2. Receive the two-part response
                ack = self.websocket.recv(timeout=5)
                if ack != "True":
                    logger.error(f"owocr sent an unexpected ack: {ack}. Closing connection.")
                    self.websocket.close()
                    self.websocket = None
                    return None  # Bad state, don't retry

                response_json_str = self.websocket.recv(timeout=30)
                owocr_result = json.loads(response_json_str)

                # 3. Process and return the results
                return self._transform_to_meikipop_format(owocr_result)

            except ConnectionClosed:
                logger.warning("Websocket connection lost. Will attempt to reconnect...")
                self.websocket = None
                if attempt == 0:
                    continue
                else:
                    logger.error("Reconnect attempt failed.")
            except WebSocketException as e:
                logger.error(f"A websocket error occurred: {e}", exc_info=True)
                if self.websocket:
                    self.websocket.close()
                self.websocket = None
                return None
            except Exception as e:
                logger.error(f"An unexpected error occurred during owocr scan: {e}", exc_info=True)
                if self.websocket:
                    self.websocket.close()
                self.websocket = None
                return None
        return None

    def _transform_to_meikipop_format(self, owocr_result: dict) -> List[Paragraph]:
        raw_lines: List[Paragraph] = []

        for owocr_para in owocr_result.get("paragraphs", []):
            for owocr_line in owocr_para.get("lines", []):
                line_full_text = "".join(word.get("text", "") for word in owocr_line.get("words", [])).strip()
                if not line_full_text:
                    continue

                meiki_words: List[Word] = []
                for word_data in owocr_line.get("words", []):
                    word_box_data = word_data.get("bounding_box", {})
                    meiki_word_box = BoundingBox(
                        center_x=word_box_data.get("center_x", 0.0),
                        center_y=word_box_data.get("center_y", 0.0),
                        width=word_box_data.get("width", 0.0),
                        height=word_box_data.get("height", 0.0),
                    )
                    meiki_words.append(Word(
                        text=word_data.get("text", ""), separator="", box=meiki_word_box
                    ))

                line_box_data = owocr_line.get("bounding_box", {})
                meiki_line_box = BoundingBox(
                    center_x=line_box_data.get("center_x", 0.0),
                    center_y=line_box_data.get("center_y", 0.0),
                    width=line_box_data.get("width", 0.0),
                    height=line_box_data.get("height", 0.0),
                )
                is_vertical = (owocr_para.get("writing_direction") == "TOP_TO_BOTTOM" or
                               (meiki_line_box.height > meiki_line_box.width))

                raw_lines.append(Paragraph(
                    full_text=line_full_text, words=meiki_words, box=meiki_line_box, is_vertical=is_vertical
                ))

        return group_lines_into_paragraphs(raw_lines)
