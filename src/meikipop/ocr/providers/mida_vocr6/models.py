# meikipop/ocr/providers/mida_vocr6/models.py
"""Model files: `mida_ocr_l.onnx` is supplied by the user (its licence is not stated, so it is never bundled or fetched);
`VOCR6.2_L_fast.onnx` is downloaded once and sha256-checked. Both live in `<meikipop data dir>/models/mida_vocr6`, or in
$MEIKIPOP_MIDA_VOCR_DIR. The VOCR6 weights are for non-commercial use only (see the release's VOCR6-ATTRIBUTION.md)."""
import hashlib
import logging
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

DIR_ENV = "MEIKIPOP_MIDA_VOCR_DIR"
MIDA_FILE = "mida_ocr_l.onnx"
VOCR_FILE = "VOCR6.2_L_fast.onnx"
VOCR_URL = "https://github.com/bee-san/vita-vn-ocr/releases/download/v0.5.1-onnx.2/" + VOCR_FILE
VOCR_SHA256 = "3084fb3bd1332832c872009d869d267d5acd1bd69d26c80f742aa2f31a80c938"


def model_dir() -> Path:
    if os.environ.get(DIR_ENV):
        d = Path(os.environ[DIR_ENV]).expanduser()
    else:
        from meikipop.utils.paths import paths
        d = Path(paths.data_dir) / "models" / "mida_vocr6"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_mida() -> Path:
    path = model_dir() / MIDA_FILE
    if not path.is_file():
        raise FileNotFoundError(
            f"{MIDA_FILE} not found. Copy it to: {path}\n(or set {DIR_ENV} to a directory that holds it)")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_vocr() -> Path:
    """The path of the VOCR6 recognizer, downloaded and verified first if it is missing or wrong."""
    path = model_dir() / VOCR_FILE
    if path.is_file() and _sha256(path) == VOCR_SHA256:
        return path

    logger.info(f"downloading {VOCR_FILE} (2.5 MB) from {VOCR_URL} ...")
    part = path.with_name(path.name + ".part")
    try:
        with urllib.request.urlopen(urllib.request.Request(VOCR_URL, headers={"User-Agent": "meikipop-mida-vocr6"}),
                                    timeout=60) as resp:
            part.write_bytes(resp.read())
        if _sha256(part) != VOCR_SHA256:
            raise ValueError("sha256 does not match the release's")
        os.replace(part, path)
    except Exception as e:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"could not fetch {VOCR_FILE} ({e}). Download it by hand from {VOCR_URL} and put it in {path.parent}") from e
    return path
