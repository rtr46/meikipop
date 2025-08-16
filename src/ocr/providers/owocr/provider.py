import asyncio
import io
import json
import logging
from typing import List, Optional

import websockets
from PIL import Image

# The "contract" classes that a provider MUST use for its return value.
from src.ocr.interface import OcrProvider, Paragraph, Word, BoundingBox

logger = logging.getLogger(__name__)

# Define the connection details for the owocr websocket server
OWOCR_WEBSOCKET_URI = "ws://localhost:7331"


class OwocrWebsocketProvider(OcrProvider):
    """
    An OCR provider that connects to a running owocr instance via websockets.

    This provider acts as a client. It sends an image to the owocr server
    and receives a structured JSON response with text and coordinates, which it
    then transforms into the required meikipop data format.
    """
    NAME = "owocr (Websocket)"

    def __init__(self):
        super().__init__()
        self._connection_error_logged = False

    async def _scan_async(self, image: Image.Image) -> Optional[List[Paragraph]]:
        """Helper to contain the asynchronous websocket communication."""
        try:
            # Set a longer timeout to account for both connection and receiving the result
            async with websockets.connect(OWOCR_WEBSOCKET_URI, open_timeout=3) as websocket:
                # If connection succeeds, reset the error flag
                self._connection_error_logged = False

                # 1. PREPARE AND SEND THE IMAGE
                with io.BytesIO() as buffer:
                    image.save(buffer, format="PNG")
                    image_bytes = buffer.getvalue()

                await websocket.send(image_bytes)

                # 2. HANDLE THE TWO-MESSAGE RESPONSE FROM OWOCR
                # First, receive the 'True' acknowledgment and check it.
                ack = await asyncio.wait_for(websocket.recv(), timeout=5)
                if ack != "True":
                    logger.error(f"owocr acknowledged the request with an unexpected response: {ack}")
                    return None

                # Now, wait for the second message which contains the actual JSON result.
                # We add a longer timeout here as OCR can take time.
                response_json_str = await asyncio.wait_for(websocket.recv(), timeout=30)
                owocr_result = json.loads(response_json_str)

                # 3. TRANSFORM DATA FROM OWOCR FORMAT TO MEIKIPOP FORMAT
                return self._transform_to_meikipop_format(owocr_result)

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError, asyncio.TimeoutError) as e:
            if not self._connection_error_logged:
                logger.error(f"Could not connect to or get a timely response from owocr at {OWOCR_WEBSOCKET_URI}.")
                logger.info("Please ensure owocr is running with the command:")
                logger.info("python -m owocr -r websocket -w websocket -of json")  # todo log more useful instructions
                self._connection_error_logged = True
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred with the owocr provider: {e}", exc_info=True)
            return None

    def _transform_to_meikipop_format(self, owocr_result: dict) -> List[Paragraph]:
        """
        Converts the JSON response from owocr into a list of meikipop Paragraph objects.
        """
        meiki_paragraphs: List[Paragraph] = []

        for owocr_para in owocr_result.get("paragraphs", []):
            for owocr_line in owocr_para.get("lines", []):

                line_full_text_parts = []
                for word_data in owocr_line.get("words", []):
                    line_full_text_parts.append(word_data.get("text", ""))
                line_full_text = "".join(line_full_text_parts).strip()

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
                        text=word_data.get("text", ""),
                        separator="",
                        box=meiki_word_box
                    ))

                line_box_data = owocr_line.get("bounding_box", {})
                meiki_para_box = BoundingBox(
                    center_x=line_box_data.get("center_x", 0.0),
                    center_y=line_box_data.get("center_y", 0.0),
                    width=line_box_data.get("width", 0.0),
                    height=line_box_data.get("height", 0.0),
                )

                is_vertical = owocr_para.get("writing_direction") == "TOP_TO_BOTTOM" or \
                              (meiki_para_box.height > meiki_para_box.width)

                paragraph = Paragraph(
                    full_text=line_full_text,
                    words=meiki_words,
                    box=meiki_para_box,
                    is_vertical=is_vertical
                )
                meiki_paragraphs.append(paragraph)

        return meiki_paragraphs

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        """
        Performs OCR by sending the image to a running owocr websocket server.
        """
        try:
            return asyncio.run(self._scan_async(image))
        except Exception as e:
            logger.error(f"Failed to run async scan operation: {e}", exc_info=True)
            return None
