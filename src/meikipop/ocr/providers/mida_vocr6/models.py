# meikipop/ocr/providers/mida_vocr6/models.py
"""One model-acquisition path for the mida + VOCR6 provider.

Every model is described by a ModelSpec (filename, sha256, source). A spec is served either from the
Hugging Face repo `rtr46/vocr6` (both VOCR recognizers) or from a bundled package asset (the mida detector,
which is not in that repo). All files are sha256-checked and live in `<meikipop data dir>/models/mida_vocr6`,
or in $MEIKIPOP_MIDA_VOCR_DIR. The VOCR weights are non-commercial only."""
import hashlib
import logging
import os
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DIR_ENV = "MEIKIPOP_MIDA_VOCR_DIR"
BUNDLED_DIR = Path(__file__).resolve().parent / "assets"
HF_BASE = "https://huggingface.co/rtr46/vocr6/resolve/main/"


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    sha256: str
    url: Optional[str] = None
    bundled: Optional[str] = None


SPECS = {
    "mida": ModelSpec(
        filename="mida_v2.onnx",
        sha256="7a09988b2596ef3fda2e5dfa815bfebbba6d3dcc385cc905cbb329cd8c95a4fa",
        bundled="mida_v2.onnx",
    ),
    "vocr": ModelSpec(
        filename="VOCR6.2_L_fast.onnx",
        sha256="3084fb3bd1332832c872009d869d267d5acd1bd69d26c80f742aa2f31a80c938",
        url=HF_BASE + "VOCR6.2_L_fast.onnx",
    ),
    "vocr_v": ModelSpec(
        filename="VOCR6_V_fast.onnx",
        sha256="080f0651fe2f23e87befea16995c21089e02da85be96b6189c26c2ab413ac5eb",
        url=HF_BASE + "VOCR6_V_fast.onnx",
    ),
}


def model_dir() -> Path:
    if os.environ.get(DIR_ENV):
        d = Path(os.environ[DIR_ENV]).expanduser()
    else:
        from meikipop.utils.paths import paths
        d = Path(paths.data_dir) / "models" / "mida_vocr6"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_mida() -> Path:
    return ensure(SPECS["mida"])


def ensure_vocr() -> Path:
    return ensure(SPECS["vocr"])


def ensure_vocr_v() -> Path:
    return ensure(SPECS["vocr_v"])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid(path: Path, sha256: str) -> bool:
    return path.is_file() and _sha256(path) == sha256


def ensure(spec: ModelSpec) -> Path:
    """The verified local path of a model, fetched from its source first if missing or corrupt."""
    path = model_dir() / spec.filename
    if _valid(path, spec.sha256):
        return path

    part = path.with_name(path.name + ".part")
    source = spec.url or str(BUNDLED_DIR / (spec.bundled or spec.filename))
    try:
        if spec.url:
            logger.info(f"downloading {spec.filename} from {spec.url} ...")
            request = urllib.request.Request(spec.url, headers={"User-Agent": "meikipop-mida-vocr6"})
            with urllib.request.urlopen(request, timeout=60) as response:
                part.write_bytes(response.read())
        elif spec.bundled:
            src = BUNDLED_DIR / spec.bundled
            if not _valid(src, spec.sha256):
                raise RuntimeError(f"the bundled file is missing or does not match its sha256 ({src})")
            shutil.copyfile(src, part)
        else:
            raise RuntimeError(f"no source configured for {spec.filename}")

        if not _valid(part, spec.sha256):
            raise ValueError("sha256 does not match the expected one")
        os.replace(part, path)
    except Exception as e:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"could not obtain {spec.filename} from {source} ({e}). "
            f"Download it by hand and put it in {path.parent}"
        ) from e
    return path
