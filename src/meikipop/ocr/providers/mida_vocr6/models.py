# meikipop/ocr/providers/mida_vocr6/models.py
"""Model files, downloaded once on first use and sha256-checked: `mida_ocr_l.onnx` (the mida line detector, from its
author's Hugging Face repo) and `VOCR6.2_L_fast.onnx` (the recognizer). Both live in `<meikipop data dir>/models/mida_vocr6`,
or in $MEIKIPOP_MIDA_VOCR_DIR. The VOCR6 weights are for non-commercial use only (see the release's VOCR6-ATTRIBUTION.md)."""
import hashlib
import logging
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

DIR_ENV = "MEIKIPOP_MIDA_VOCR_DIR"

# the detector's decode was tuned on exactly this file; a new mida release would be a new file with a new hash
MIDA_FILE = "mida_ocr_l.onnx"
MIDA_URL = "https://huggingface.co/rtr46/mida/resolve/main/mida_l_alpha_v0.0.1.onnx"
MIDA_SHA256 = "9f72bce58b50b1837bb16e81c5c035d32d9cd45d84dcef56f0b6fb2ef25e8aed"

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


def ensure_mida() -> Path:
    return _ensure(MIDA_FILE, MIDA_URL, MIDA_SHA256)


def ensure_vocr() -> Path:
    return _ensure(VOCR_FILE, VOCR_URL, VOCR_SHA256)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ensure(name: str, url: str, sha256: str) -> Path:
    """The path of a model file, downloaded and verified first if it is missing or its sha256 is wrong."""
    path = model_dir() / name
    if path.is_file() and _sha256(path) == sha256:
        return path

    logger.info(f"downloading {name} from {url} ...")
    part = path.with_name(path.name + ".part")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "meikipop-mida-vocr6"}),
                                    timeout=60) as resp:
            part.write_bytes(resp.read())
        if _sha256(part) != sha256:
            raise ValueError("sha256 does not match the expected one")
        os.replace(part, path)
    except Exception as e:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"could not fetch {name} ({e}). Download it by hand from {url} and put it in {path.parent}") from e
    return path
