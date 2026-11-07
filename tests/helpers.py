import cv2
import numpy as np

from kisan.ml.types import MediaItem


def sharp_image(seed: int = 0, w: int = 1280, h: int = 960) -> np.ndarray:
    """Textured, well-exposed synthetic photo that passes the quality gate."""
    rng = np.random.default_rng(seed)
    small = rng.integers(40, 215, size=(h // 16, w // 16, 3), dtype=np.uint8)
    img = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    for _ in range(40):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        cv2.circle(img, (x, y), int(rng.integers(10, 80)), tuple(int(c) for c in rng.integers(0, 255, 3)), 3)
    return img


def photo_set(views, seed: int = 0) -> list[MediaItem]:
    return [
        MediaItem(image_id=f"img_{v.lower()}", view=v, bgr=sharp_image(seed + i)) for i, v in enumerate(views)
    ]


def frames(n: int = 4, seed: int = 100) -> list[MediaItem]:
    return [MediaItem(image_id=f"frame_{i}", view="VIDEO", bgr=sharp_image(seed + i)) for i in range(n)]


COW_VIEWS = ["FRONT", "LEFT", "RIGHT", "REAR", "FACE", "MUZZLE", "TAG"]
