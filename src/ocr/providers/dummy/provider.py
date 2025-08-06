# src/ocr/providers/dummy/provider.py
import logging
from typing import List, Optional

from PIL import Image

# The "contract" classes that a new provider MUST use for its return value.
from src.ocr.interface import OcrProvider, Paragraph, Word, BoundingBox

logger = logging.getLogger(__name__)


class DummyProvider(OcrProvider):
    """
    A template for creating new OCR providers.

    This class demonstrates the required structure and data transformations.
    Developers can copy this file to start their own provider implementation.
    When this provider is selected, it returns a fixed set of Japanese text
    to allow for testing of the popup window without a real OCR backend.
    """
    # The NAME is displayed in the settings and tray menu. Make it unique and descriptive.
    NAME = "Dummy OCR (Developer Template)"

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        """
        Performs OCR on the given image.

        This method must be implemented. Its main job is to:
        1. Get OCR data from an external source (library, API, etc.).
        2. Convert the proprietary data format into meikipop's standard format
           (a list of Paragraph objects with normalized coordinates).
        3. Return the list of Paragraphs.
        """
        logger.info(f"{self.NAME} received an image of size {image.size}. Returning mock data.")

        # --- Pro-Tip: Let an AI do the heavy lifting! ---
        # You can provide this file, the contents of `src/ocr/interface.py`,
        # and a sample JSON/text output from your chosen OCR engine to a
        # Large Language Model (like GPT-4, Claude, etc.) and ask it to
        # write the adapter code for you. This can get you 90% of the way there.

        try:
            # --- 1. OBTAIN OCR DATA ---
            # In a real provider, you would call your OCR engine here.
            # This could be a Python library, a REST API, or a command-line tool.
            # We will use a hardcoded, mock result for demonstration.

            # Example: Calling a Python library (if you had one)
            # import my_cool_ocr_library
            # client = my_cool_ocr_library.Client(api_key="...")
            # raw_ocr_results = client.recognize(image)

            # Example: Making a REST API call
            # import requests
            # _, buffer = cv2.imencode('.jpg', image)
            # response = requests.post("https://api.myocr.com/v1/scan", files={'image': buffer.tobytes()})
            # raw_ocr_results = response.json()

            # For this template, we'll define a mock result that simulates the output
            # from a fictional OCR engine. This engine gives us pixel coordinates.
            mock_ocr_result = [
                {
                    "text": "これは横書きテキストです",
                    "bbox": {"x": 100, "y": 150, "w": 400, "h": 40},  # A horizontal bounding box
                    "words": [
                        {"text": "これは", "bbox": {"x": 100, "y": 150, "w": 90, "h": 40}},
                        {"text": "横書き", "bbox": {"x": 200, "y": 150, "w": 90, "h": 40}},
                        {"text": "テキストです", "bbox": {"x": 300, "y": 150, "w": 200, "h": 40}},
                    ]
                },
                {
                    "text": "縦書き",
                    "bbox": {"x": 600, "y": 200, "w": 50, "h": 300},  # A vertical bounding box
                    "words": [
                        # NOTE: A `Word` object can contain multiple characters OR a single character.
                        # meikipop's hit-scanning works well with both approaches.
                        # Providing single-character boxes can lead to more precise lookups.
                        {"text": "縦", "bbox": {"x": 600, "y": 200, "w": 50, "h": 95}},
                        {"text": "書", "bbox": {"x": 600, "y": 305, "w": 50, "h": 95}},
                        {"text": "き", "bbox": {"x": 600, "y": 405, "w": 50, "h": 95}},
                    ]
                }
            ]

            # --- 2. PROCESS AND TRANSFORM THE DATA ---
            # This is the most important part. You must convert the raw results from your
            # OCR engine into the format meikipop understands (`List[Paragraph]`).

            paragraphs: List[Paragraph] = []
            img_width, img_height = image.size
            if img_width == 0 or img_height == 0:
                logger.error("Invalid image dimensions received.")
                return None

            for ocr_line in mock_ocr_result:
                line_text = ocr_line.get("text")
                line_bbox_data = ocr_line.get("bbox")
                if not line_text or not line_bbox_data:
                    continue

                # meikipop requires NORMALIZED coordinates (from 0.0 to 1.0).
                # Here we convert the absolute pixel BBox to a normalized BoundingBox.
                # Our mock 'bbox' has top-left corner (x,y) and width/height (w,h).
                center_x = (line_bbox_data['x'] + line_bbox_data['w'] / 2) / img_width
                center_y = (line_bbox_data['y'] + line_bbox_data['h'] / 2) / img_height
                norm_w = line_bbox_data['w'] / img_width
                norm_h = line_bbox_data['h'] / img_height

                line_box = BoundingBox(
                    center_x=center_x, center_y=center_y,
                    width=norm_w, height=norm_h
                )

                # For Japanese, it's crucial to know the writing direction.
                # If your OCR engine doesn't provide this, you can infer it from
                # the bounding box's aspect ratio.
                is_vertical = line_bbox_data['h'] > line_bbox_data['w']

                # Now, process the words within the line.
                words_in_para: List[Word] = []
                for i, word_data in enumerate(ocr_line.get("words", [])):
                    word_text = word_data.get("text", "")
                    word_bbox_data = word_data.get("bbox")
                    if not word_text or not word_bbox_data:
                        continue

                    # Convert word coordinates, just like we did for the paragraph.
                    word_center_x = (word_bbox_data['x'] + word_bbox_data['w'] / 2) / img_width
                    word_center_y = (word_bbox_data['y'] + word_bbox_data['h'] / 2) / img_height
                    word_norm_w = word_bbox_data['w'] / img_width
                    word_norm_h = word_bbox_data['h'] / img_height

                    word_box = BoundingBox(
                        center_x=word_center_x, center_y=word_center_y,
                        width=word_norm_w, height=word_norm_h
                    )

                    # The separator is important for reconstructing text. In Japanese, it's often empty.
                    separator = ""

                    words_in_para.append(Word(text=word_text, separator=separator, box=word_box))

                # If your OCR only provides line-level data, you might need to
                # create a single `Word` object for the entire line text.
                if not words_in_para:
                    words_in_para.append(Word(text=line_text, separator="", box=line_box))

                # Finally, assemble the Paragraph object.
                paragraph = Paragraph(
                    full_text=line_text,
                    words=words_in_para,
                    box=line_box,
                    is_vertical=is_vertical
                )
                paragraphs.append(paragraph)

            # --- 3. RETURN THE RESULT ---
            # The final result must be a list of Paragraph objects.
            # If no text was found, return an empty list `[]`.
            # If a critical error occurred, return `None`.
            return paragraphs

        except Exception as e:
            logger.error(f"An error occurred in {self.NAME}: {e}", exc_info=True)
            return None  # Returning None indicates a failure.
