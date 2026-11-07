import cv2
import numpy as np

from kisan.ml.stages import quality
from kisan.ml.thresholds import DEFAULT
from tests.helpers import sharp_image


def test_sharp_photo_passes():
    assert quality.problems(quality.measure(sharp_image()), DEFAULT) == []


def test_blurry_photo_rejected():
    blurry = cv2.GaussianBlur(sharp_image(), (51, 51), 20)
    assert any("blurry" in p for p in quality.problems(quality.measure(blurry), DEFAULT))


def test_dark_photo_rejected():
    dark = (sharp_image() * 0.1).astype(np.uint8)
    assert any("dark" in p for p in quality.problems(quality.measure(dark), DEFAULT))


def test_small_photo_rejected():
    small = cv2.resize(sharp_image(), (640, 480))
    assert any("too small" in p for p in quality.problems(quality.measure(small), DEFAULT))


def test_phash_same_for_recompressed_copy():
    img = sharp_image()
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
    copy = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    import imagehash

    d = imagehash.hex_to_hash(quality.phash(img)) - imagehash.hex_to_hash(quality.phash(copy))
    assert d <= DEFAULT.phash_same_photo
