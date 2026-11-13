"""Decode uploaded bytes into arrays."""

from __future__ import annotations

import os
import tempfile

import cv2
import numpy as np
from cv2.typing import MatLike


def decode_image(data: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError("file is not a readable image")
    return arr


def sample_video_frames(data: bytes, n: int = 6, max_side: int = 1280) -> list[np.ndarray]:
    """Evenly sample ``n`` frames from an mp4 clip."""
    fd, path = tempfile.mkstemp(suffix=".mp4")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        cap = cv2.VideoCapture(path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            return []
        frames:list[MatLike] = []
        for idx in np.linspace(0, total - 1, num=min(n, total)).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            s = min(1.0, max_side / max(h, w))
            if s < 1.0:
                frame = cv2.resize(frame, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
            frames.append(frame)
        cap.release()
        return frames
    finally:
        os.unlink(path)
