# meikipop/ocr/providers/mida_vocr6/models.py
"""One model-acquisition path for the mida + VOCR6 provider: every model is a sha256-checked Hugging Face
file, served from `<meikipop data dir>/models/mida_vocr6` or $MEIKIPOP_MIDA_VOCR_DIR.

The VOCR weights are non-commercial only (see the model cards in those repos).
"""
import hashlib
import logging
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DIR_ENV = "MEIKIPOP_MIDA_VOCR_DIR"
MIDA_BASE = "https://huggingface.co/rtr46/mida/resolve/main/"
VOCR_BASE = "https://huggingface.co/rtr46/vocr6/resolve/main/"


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    url: str
    sha256: str


MIDA = ModelSpec("mida_l_alpha_v0.0.2.onnx", MIDA_BASE + "mida_l_alpha_v0.0.2.onnx",
                 "7a09988b2596ef3fda2e5dfa815bfebbba6d3dcc385cc905cbb329cd8c95a4fa")
VOCR = ModelSpec("VOCR6.2_L_fast.onnx", VOCR_BASE + "VOCR6.2_L_fast.onnx",
                 "3084fb3bd1332832c872009d869d267d5acd1bd69d26c80f742aa2f31a80c938")
VOCR_V = ModelSpec("VOCR6_V_fast.onnx", VOCR_BASE + "VOCR6_V_fast.onnx",
                   "080f0651fe2f23e87befea16995c21089e02da85be96b6189c26c2ab413ac5eb")


def model_dir() -> Path:
    if os.environ.get(DIR_ENV):
        d = Path(os.environ[DIR_ENV]).expanduser()
    else:
        from meikipop.utils.paths import paths
        d = Path(paths.data_dir) / "models" / "mida_vocr6"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure(spec: ModelSpec) -> Path:
    """The verified local path of a model, downloaded from Hugging Face if missing or corrupt."""
    path = model_dir() / spec.filename
    if path.is_file() and _sha256(path) == spec.sha256:
        return path

    logger.info(f"downloading {spec.filename} from {spec.url} ...")
    part = path.with_name(path.name + ".part")
    try:
        request = urllib.request.Request(spec.url, headers={"User-Agent": "meikipop-mida-vocr6"})
        with urllib.request.urlopen(request, timeout=60) as response:
            part.write_bytes(response.read())
        if _sha256(part) != spec.sha256:
            raise ValueError("sha256 does not match the expected one")
        os.replace(part, path)
    except Exception as e:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"could not obtain {spec.filename} from {spec.url} ({e}). "
            f"Download it by hand and put it in {path.parent}"
        ) from e
    return path


def ensure_mida() -> Path:
    return ensure(MIDA)


def ensure_vocr() -> Path:
    return ensure(VOCR)


def ensure_vocr_v() -> Path:
    return ensure(VOCR_V)
