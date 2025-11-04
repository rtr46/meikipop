import logging
from typing import List, Optional

import cv2
import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from PIL import Image
import re

# the "contract" classes that a new provider MUST use for its return value.
from src.ocr.interface import BoundingBox, OcrProvider, Paragraph, Word

logger = logging.getLogger(__name__)

# --- model configuration ---
DET_MODEL_REPO = "rtr46/meiki.text.detect.v0"
DET_MODEL_NAME = "meiki.text.detect.v0.1.960x544.onnx"
REC_MODEL_REPO = "rtr46/meiki.txt.recognition.v0"
REC_MODEL_NAME = "meiki.text.rec.v0.960x32.onnx"

# --- pipeline configuration ---
INPUT_DET_WIDTH = 960
INPUT_DET_HEIGHT = 544
INPUT_REC_HEIGHT = 32
INPUT_REC_WIDTH = 960
DET_CONFIDENCE_THRESHOLD = 0.5
REC_CONFIDENCE_THRESHOLD = 0.1
X_OVERLAP_THRESHOLD = 0.3
EPSILON = 1e-6

JAPANESE_REGEX = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')


class MeikiOcrProvider(OcrProvider):
    """
    An OCR provider that uses the high-performance meikiocr pipeline.
    This provider is specifically optimized for recognizing Japanese text from video games.
    """
    NAME = "meikiocr (local)"

    def __init__(self):
        """
        Initializes the provider and lazy-loads the ONNX models.
        This is called once when the provider is selected in MeikiPop.
        """
        logger.info(f"initializing {self.NAME} provider...")
        self.det_session = None
        self.rec_session = None
        try:
            det_model_path = hf_hub_download(repo_id=DET_MODEL_REPO, filename=DET_MODEL_NAME)
            rec_model_path = hf_hub_download(repo_id=REC_MODEL_REPO, filename=REC_MODEL_NAME)

            # prioritize gpu if available, fallback to cpu.
            available_providers = ort.get_available_providers()
            desired_providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            providers_to_use = [p for p in desired_providers if p in available_providers]
            ort.set_default_logger_severity(3)  # suppress verbose logs

            self.det_session = ort.InferenceSession(det_model_path, providers=providers_to_use)
            self.rec_session = ort.InferenceSession(rec_model_path, providers=providers_to_use)

            active_provider = self.det_session.get_providers()[0]
            logger.info(f"{self.NAME} initialized successfully, running on: {active_provider}")

        except Exception as e:
            logger.error(f"failed to initialize {self.NAME}: {e}", exc_info=True)

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        """
        Performs OCR on the given image using the full meikiocr pipeline.
        """
        if not self.det_session or not self.rec_session:
            logger.error(f"{self.NAME} was not initialized correctly. cannot perform scan.")
            return None

        try:

            # convert pil (rgb) image to numpy array for opencv processing.
            image_np = np.array(image.convert("RGB"))
            img_height, img_width = image_np.shape[:2]
            if img_width == 0 or img_height == 0:
                logger.error("invalid image dimensions received.")
                return None

            # --- 1. run detection stage ---
            det_input, scale = self._preprocess_for_detection(image_np)
            det_raw = self._run_detection_inference(det_input, scale)
            text_boxes = self._postprocess_detection_results(det_raw)

            if not text_boxes:
                return []

            # --- 2. run recognition stage ---
            rec_batch, valid_indices, crop_meta = self._preprocess_for_recognition(image_np, text_boxes)
            if rec_batch is None:
                return []

            rec_raw = self._run_recognition_inference(rec_batch)
            ocr_results = self._postprocess_recognition_results(rec_raw, valid_indices, crop_meta, len(text_boxes))

            # --- 3. transform data to meikipop's format ---
            return self._to_meikipop_paragraphs(ocr_results, img_width, img_height)

        except Exception as e:
            logger.error(f"an error occurred in {self.NAME}: {e}", exc_info=True)
            return None  # returning none indicates a failure.

    def _to_normalized_bbox(self, bbox_pixels: list, img_width: int, img_height: int) -> BoundingBox:
        """converts an [x1, y1, x2, y2] pixel bbox to a normalized meikipop BoundingBox."""
        x1, y1, x2, y2 = bbox_pixels
        box_w, box_h = x2 - x1, y2 - y1

        center_x = (x1 + box_w / 2) / img_width
        center_y = (y1 + box_h / 2) / img_height
        norm_w = box_w / img_width
        norm_h = box_h / img_height

        return BoundingBox(center_x, center_y, norm_w, norm_h)

    def _to_meikipop_paragraphs(self, ocr_results: list, img_width: int, img_height: int) -> List[Paragraph]:
        """converts the final meikiocr result list into meikipop's Paragraph format."""
        paragraphs: List[Paragraph] = []
        for line_result in ocr_results:
            full_text = line_result.get("text", "").strip()
            chars = line_result.get("chars", [])
            if not full_text or not chars or not JAPANESE_REGEX.search(full_text):
                continue

            # create word objects for each character (best for precise lookups).
            words_in_para: List[Word] = []
            for char_info in chars:
                char_box = self._to_normalized_bbox(char_info['bbox'], img_width, img_height)
                words_in_para.append(Word(text=char_info['char'], separator="", box=char_box))

            # meikiocr doesn't provide a line-level box, so we must compute it
            # by finding the union of all character boxes in the line.
            min_x = min(c['bbox'][0] for c in chars)
            min_y = min(c['bbox'][1] for c in chars)
            max_x = max(c['bbox'][2] for c in chars)
            max_y = max(c['bbox'][3] for c in chars)
            line_pixel_bbox = [min_x, min_y, max_x, max_y]
            line_box = self._to_normalized_bbox(line_pixel_bbox, img_width, img_height)

            # meikiocr currently only supports horizontal text.
            is_vertical = False

            paragraph = Paragraph(
                full_text=full_text,
                words=words_in_para,
                box=line_box,
                is_vertical=is_vertical
            )
            paragraphs.append(paragraph)

        return paragraphs

    # --- meikiocr pipeline methods (adapted from meiki_ocr.py) ---

    def _preprocess_for_detection(self, image: np.ndarray):
        h_orig, w_orig = image.shape[:2]

        scale = min(INPUT_DET_WIDTH / w_orig, INPUT_DET_HEIGHT / h_orig)
        w_resized, h_resized = int(w_orig * scale), int(h_orig * scale)

        resized = cv2.resize(image, (w_resized, h_resized), interpolation=cv2.INTER_LINEAR)
        normalized_resized = resized.astype(np.float32) / 255.0

        tensor = np.zeros((INPUT_DET_HEIGHT, INPUT_DET_WIDTH, 3), dtype=np.float32)
        tensor[:h_resized, :w_resized] = normalized_resized
        tensor = np.transpose(tensor, (2, 0, 1))
        tensor = np.expand_dims(tensor, axis=0)

        return tensor, scale

    def _run_detection_inference(self, tensor: np.ndarray, scale: float):
        inputs = {
            self.det_session.get_inputs()[0].name: tensor,
            self.det_session.get_inputs()[1].name: np.array([[INPUT_DET_WIDTH / scale, INPUT_DET_HEIGHT / scale]],
                                                            dtype=np.int64)
        }
        return self.det_session.run(None, inputs)

    def _postprocess_detection_results(self, raw_outputs: list):
        _, boxes, scores = raw_outputs
        boxes, scores = boxes[0], scores[0]
        confident_boxes = boxes[scores > DET_CONFIDENCE_THRESHOLD]
        if confident_boxes.shape[0] == 0:
            return []

        clamped_boxes = np.maximum(0, confident_boxes.astype(np.int32))

        text_boxes = [{'bbox': box.tolist()} for box in clamped_boxes]
        return text_boxes

    def _preprocess_for_recognition(self, image: np.ndarray, text_boxes: list):
        tensors, valid_indices, crop_meta = [], [], []
        for i, tb in enumerate(text_boxes):
            x1, y1, x2, y2 = tb['bbox']
            w, h = x2 - x1, y2 - y1
            if w < h or w <= 0 or h <= 0: continue
            crop = image[y1:y2, x1:x2]
            ch, cw = crop.shape[:2]
            nh, nw = INPUT_REC_HEIGHT, int(round(cw * (INPUT_REC_HEIGHT / ch)))
            if nw > INPUT_REC_WIDTH:
                scale = INPUT_REC_WIDTH / nw
                nw, nh = INPUT_REC_WIDTH, int(round(nh * scale))
            resized = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_LINEAR)
            pw, ph = INPUT_REC_WIDTH - nw, INPUT_REC_HEIGHT - nh
            padded = np.pad(resized, ((0, ph), (0, pw), (0, 0)), constant_values=0)
            tensor = (padded.astype(np.float32) / 255.0)
            tensor = np.transpose(tensor, (2, 0, 1))
            tensors.append(tensor)
            valid_indices.append(i)
            crop_meta.append({'orig_bbox': [x1, y1, x2, y2], 'effective_w': nw})
        if not tensors: return None, [], []
        return np.stack(tensors, axis=0), valid_indices, crop_meta

    def _run_recognition_inference(self, batch_tensor: np.ndarray):
        inputs = {
            "images": batch_tensor,
            "orig_target_sizes": np.array([[INPUT_REC_WIDTH, INPUT_REC_HEIGHT]], dtype=np.int64)
        }
        return self.rec_session.run(None, inputs)

    def _postprocess_recognition_results(self, raw_outputs: list, valid_indices: list, crop_meta: list, num_boxes: int):
        labels_batch, boxes_batch, scores_batch = raw_outputs
        results = [{'text': '', 'chars': []} for _ in range(num_boxes)]
        for i, (labels, boxes, scores) in enumerate(zip(labels_batch, boxes_batch, scores_batch)):
            meta = crop_meta[i]
            gx1, gy1, gx2, gy2 = meta['orig_bbox']
            cw, ch = gx2 - gx1, gy2 - gy1
            ew = meta['effective_w']

            candidates = []
            for lbl, box, scr in zip(labels, boxes, scores):
                if scr < REC_CONFIDENCE_THRESHOLD: continue

                char = chr(lbl)
                rx1, ry1, rx2, ry2 = box
                rx1, rx2 = min(rx1, ew), min(rx2, ew)

                # map: recognition space -> crop space -> global image
                cx1 = (rx1 / ew) * cw
                cx2 = (rx2 / ew) * cw
                cy1 = (ry1 / INPUT_REC_HEIGHT) * ch
                cy2 = (ry2 / INPUT_REC_HEIGHT) * ch

                gx1_char = gx1 + int(cx1)
                gy1_char = gy1 + int(cy1)
                gx2_char = gx1 + int(cx2)
                gy2_char = gy1 + int(cy2)

                candidates.append({
                    'char': char,
                    'bbox': [gx1_char, gy1_char, gx2_char, gy2_char],
                    'conf': float(scr),
                    'x_interval': (gx1_char, gx2_char)
                })

            # sort by confidence (descending) to prepare for deduplication
            candidates.sort(key=lambda c: c['conf'], reverse=True)

            # spatial deduplication on x-axis (non-maximum suppression)
            accepted = []
            for cand in candidates:
                x1_c, x2_c = cand['x_interval']
                width_c = x2_c - x1_c + EPSILON
                keep = True
                for acc in accepted:
                    x1_a, x2_a = acc['x_interval']
                    overlap = max(0, min(x2_c, x2_a) - max(x1_c, x1_a))
                    if overlap / width_c > X_OVERLAP_THRESHOLD:
                        keep = False
                        break
                if keep:
                    accepted.append(cand)

            # sort by x for final reading order
            accepted.sort(key=lambda c: c['x_interval'][0])

            text = ''.join(c['char'] for c in accepted)
            # keep the confidence score in the final output as it can be useful
            final_chars = [{'char': c['char'], 'bbox': c['bbox'], 'conf': c['conf']} for c in accepted]

            results[valid_indices[i]] = {'text': text, 'chars': final_chars}

        return results
