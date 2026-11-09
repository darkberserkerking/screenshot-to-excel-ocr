"""Image loading and multi-scale preparation.

Small screenshots are a known failure mode for detection-based OCR: many
engines upscale any image whose short side is below a fixed threshold, which
stretches a tiny crop out of proportion. Scanning the *whole* image at several
scales and voting on the results is more reliable than cropping single lines.
"""

from typing import Iterable, List, Sequence, Tuple

from PIL import Image

SUPPORTED_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")


def load_image(path: str) -> Image.Image:
    """Open an image as RGB. Raises a clear error for unreadable files."""
    try:
        with Image.open(path) as img:
            return img.convert("RGB")
    except Exception as exc:  # pragma: no cover - depends on local files
        raise ValueError(f"cannot read image: {path} ({exc})") from exc


def multiscale(image: Image.Image, scales: Sequence[float]) -> List[Tuple[float, Image.Image]]:
    """Return ``(scale, image)`` pairs for each requested scale."""
    pairs: List[Tuple[float, Image.Image]] = []
    for scale in scales:
        scale = float(scale)
        if scale <= 0:
            continue
        if scale == 1.0:
            pairs.append((1.0, image))
        else:
            size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            pairs.append((scale, image.resize(size, Image.LANCZOS)))
    return pairs


def iter_images(folder: str) -> Iterable[str]:
    """Yield supported image paths in ``folder`` in a stable, sorted order."""
    import os

    names = sorted(
        n for n in os.listdir(folder)
        if n.lower().endswith(SUPPORTED_SUFFIXES)
    )
    for name in names:
        yield os.path.join(folder, name)
