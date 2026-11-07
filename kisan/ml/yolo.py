"""YOLO pre/post-processing shared by the Triton and local backends.

Triton serves the raw YOLO11 head (``output0`` shaped ``[N, 4 + num_classes, anchors]``);
letterboxing, decoding and NMS run here on CPU so the GPU only does the network.
"""

from __future__ import annotations

import cv2
import numpy as np

from kisan.ml.types import Detection


def letterbox(bgr: np.ndarray, size: int = 640) -> tuple[np.ndarray, float, tuple[float, float]]:
    """Resize keeping aspect ratio and pad to ``size``. Returns CHW float32 RGB in 0..1."""
    h, w = bgr.shape[:2]
    r = min(size / h, size / w)
    nh, nw = round(h * r), round(w * r)
    resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    pad_y, pad_x = (size - nh) / 2, (size - nw) / 2
    top, left = int(round(pad_y - 0.1)), int(round(pad_x - 0.1))
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[top : top + nh, left : left + nw] = resized
    chw = canvas[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
    return np.ascontiguousarray(chw), r, (left, top)


def decode(
    raw: np.ndarray,
    class_names: list[str],
    ratio: float,
    pad: tuple[float, float],
    orig_shape: tuple[int, int],
    conf_thres: float = 0.25,
    iou_thres: float = 0.5,
) -> list[Detection]:
    """Decode one image's YOLO11 output ``[4 + C, A]`` into detections in original pixels."""
    if raw.ndim != 2 or raw.shape[0] != 4 + len(class_names):
        raise ValueError(f"unexpected YOLO output shape {raw.shape} for {len(class_names)} classes")
    preds = raw.T  # [A, 4 + C]
    scores = preds[:, 4:]
    cls_ids = scores.argmax(axis=1)
    confs = scores[np.arange(len(scores)), cls_ids]
    keep = confs >= conf_thres
    if not keep.any():
        return []
    preds, cls_ids, confs = preds[keep], cls_ids[keep], confs[keep]

    cx, cy, bw, bh = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    left, top = pad
    x1 = (cx - bw / 2 - left) / ratio
    y1 = (cy - bh / 2 - top) / ratio
    x2 = (cx + bw / 2 - left) / ratio
    y2 = (cy + bh / 2 - top) / ratio
    h, w = orig_shape
    x1, x2 = np.clip(x1, 0, w), np.clip(x2, 0, w)
    y1, y2 = np.clip(y1, 0, h), np.clip(y2, 0, h)

    out: list[Detection] = []
    # class-aware NMS
    for c in np.unique(cls_ids):
        idx = np.where(cls_ids == c)[0]
        rects = [[float(x1[i]), float(y1[i]), float(x2[i] - x1[i]), float(y2[i] - y1[i])] for i in idx]
        kept = cv2.dnn.NMSBoxes(rects, confs[idx].tolist(), conf_thres, iou_thres)
        for k in np.array(kept).flatten():
            i = idx[int(k)]
            out.append(
                Detection(
                    box=(float(x1[i]), float(y1[i]), float(x2[i]), float(y2[i])),
                    conf=float(confs[i]),
                    label=class_names[int(c)],
                )
            )
    out.sort(key=lambda d: d.conf, reverse=True)
    return out


def crop(bgr: np.ndarray, det: Detection, margin: float = 0.05) -> np.ndarray:
    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = det.box
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    xa, ya = int(max(0, x1 - mx)), int(max(0, y1 - my))
    xb, yb = int(min(w, x2 + mx)), int(min(h, y2 + my))
    return bgr[ya:yb, xa:xb].copy()
