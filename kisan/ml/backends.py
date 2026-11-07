"""Inference backends (rule 3).

``triton``  production: NVIDIA Triton over gRPC, TensorRT engines, dynamic batching.
``local``   single machine: Ultralytics + timm in-process (dev laptops, early pilot).
``fake``    deterministic, no weights: tests and local end-to-end runs.

All backends take ``MediaItem`` lists so stages never care where the model runs.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Protocol

import cv2
import numpy as np

from kisan.config import Settings, get_settings
from kisan.ml import yolo
from kisan.ml.types import Detection, MediaItem

SPECIES_LABELS = ["cow", "buffalo", "goat", "sheep", "camel", "horse"]
VIEW_LABELS = ["FRONT", "LEFT", "RIGHT", "REAR", "FACE", "MUZZLE", "TAG"]
# Fine-tuned detector classes. A stock COCO model only knows cow/sheep/horse.
DETECTOR_LABELS = SPECIES_LABELS
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class InferenceBackend(Protocol):
    animal_labels: frozenset[str]

    def detect(self, items: list[MediaItem]) -> list[list[Detection]]: ...
    def classify_species(self, items: list[MediaItem]) -> list[dict[str, float]]: ...
    def classify_view(self, items: list[MediaItem]) -> list[dict[str, float]]: ...
    def embed(self, items: list[MediaItem]) -> np.ndarray: ...
    def versions(self) -> dict[str, str]: ...


def _square(bgr: np.ndarray, size: int) -> np.ndarray:
    rgb = cv2.resize(bgr, (size, size), interpolation=cv2.INTER_AREA)[:, :, ::-1].astype(np.float32) / 255.0
    return rgb


def _l2(x: np.ndarray) -> np.ndarray:
    return x / np.clip(np.linalg.norm(x, axis=1, keepdims=True), 1e-12, None)


# --------------------------------------------------------------------------- fake
class FakeBackend:
    """Scriptable stand-in. By default every image shows one ``default_species`` animal,
    is classified as its declared view, and belongs to identity group ``"A"``."""

    animal_labels = frozenset(DETECTOR_LABELS)
    dim = 256

    def __init__(
        self,
        default_species: str = "cow",
        detections: dict[str, list[Detection]] | None = None,
        species: dict[str, dict[str, float]] | None = None,
        views: dict[str, dict[str, float]] | None = None,
        identity_group: dict[str, str] | None = None,
    ):
        self.default_species = default_species
        self._det = detections or {}
        self._species = species or {}
        self._views = views or {}
        self._group = identity_group or {}

    def detect(self, items):
        out = []
        for it in items:
            if it.image_id in self._det:
                out.append(self._det[it.image_id])
                continue
            h, w = it.bgr.shape[:2]
            out.append([Detection((0.1 * w, 0.1 * h, 0.9 * w, 0.9 * h), 0.92, self.default_species)])
        return out

    def classify_species(self, items):
        return [self._species.get(it.image_id, {self.default_species: 0.97}) for it in items]

    def classify_view(self, items):
        return [self._views.get(it.image_id, {it.view: 0.95}) for it in items]

    def _seed(self, s: str) -> int:
        return int.from_bytes(hashlib.sha256(s.encode()).digest()[:4], "little")

    def embed(self, items):
        vecs = []
        for it in items:
            group = self._group.get(it.image_id, "A")
            base = np.random.default_rng(self._seed("group:" + group)).normal(size=self.dim)
            base /= np.linalg.norm(base)
            noise = np.random.default_rng(self._seed("img:" + it.image_id)).normal(size=self.dim)
            noise /= np.linalg.norm(noise)
            vecs.append(base + 0.25 * noise)
        return _l2(np.asarray(vecs, dtype=np.float32))

    def versions(self):
        return {"backend": "fake"}


# --------------------------------------------------------------------------- local
class LocalBackend:
    """In-process models. Install with ``pip install .[local-ml]``."""

    animal_labels = frozenset(DETECTOR_LABELS) | {"cow", "sheep", "horse"}  # COCO fallback

    def __init__(
        self,
        detector: str = "models/weights/detector.pt",
        species_cls: str = "models/weights/species_cls.pt",
        view_cls: str = "models/weights/view_cls.pt",
        reid: str = "hf-hub:BVRA/MegaDescriptor-L-384",
    ):
        import timm
        import torch
        from ultralytics import YOLO

        self._torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.detector = YOLO(detector)
        self.species_cls = YOLO(species_cls)
        self.view_cls = YOLO(view_cls)
        self.reid = timm.create_model(reid, num_classes=0, pretrained=True).eval().to(self.device)
        self._versions = {"detector": detector, "species": species_cls, "view": view_cls, "reid": reid}

    def detect(self, items):
        results = self.detector.predict([it.bgr for it in items], verbose=False, conf=0.25)
        out = []
        for r in results:
            names = r.names
            dets = [
                Detection(tuple(map(float, b.xyxy[0].tolist())), float(b.conf[0]), names[int(b.cls[0])])
                for b in r.boxes
            ]
            out.append(dets)
        return out

    def _cls(self, model, items):
        results = model.predict([it.crop for it in items], verbose=False)
        return [{r.names[i]: float(p) for i, p in enumerate(r.probs.data.tolist())} for r in results]

    def classify_species(self, items):
        return self._cls(self.species_cls, items)

    def classify_view(self, items):
        return self._cls(self.view_cls, items)

    def embed(self, items):
        torch = self._torch
        batch = np.stack([(_square(it.crop, 384) - IMAGENET_MEAN) / IMAGENET_STD for it in items])
        x = torch.from_numpy(batch.transpose(0, 3, 1, 2).copy()).to(self.device)
        with torch.inference_mode():
            emb = self.reid(x).float().cpu().numpy()
        return _l2(emb)

    def versions(self):
        return dict(self._versions)


# --------------------------------------------------------------------------- triton
class TritonBackend:
    """gRPC client for the model repository in ``infra/triton_repo``. Triton batches
    concurrent requests from all workers (dynamic batching), so we send per-listing batches."""

    animal_labels = frozenset(DETECTOR_LABELS)

    def __init__(self, url: str, max_batch: int = 32):
        import tritonclient.grpc as grpcclient

        self._g = grpcclient
        self.client = grpcclient.InferenceServerClient(url=url)
        self.max_batch = max_batch
        self._versions = {m: self._model_version(m) for m in ("detector", "species_cls", "view_cls", "reid")}

    def _model_version(self, name: str) -> str:
        try:
            meta = self.client.get_model_metadata(name)
            return f"{name}:{','.join(meta.versions)}"
        except Exception:  # noqa: BLE001 - metadata is informational only
            return f"{name}:unknown"

    def _infer(self, model: str, input_name: str, output_name: str, batch: np.ndarray) -> np.ndarray:
        outs = []
        for i in range(0, len(batch), self.max_batch):
            chunk = np.ascontiguousarray(batch[i : i + self.max_batch], dtype=np.float32)
            inp = self._g.InferInput(input_name, list(chunk.shape), "FP32")
            inp.set_data_from_numpy(chunk)
            res = self.client.infer(model, [inp], outputs=[self._g.InferRequestedOutput(output_name)])
            outs.append(res.as_numpy(output_name))
        return np.concatenate(outs, axis=0)

    def detect(self, items):
        prepped = [yolo.letterbox(it.bgr, 640) for it in items]
        raw = self._infer("detector", "images", "output0", np.stack([p[0] for p in prepped]))
        return [
            yolo.decode(raw[i], DETECTOR_LABELS, prepped[i][1], prepped[i][2], items[i].bgr.shape[:2])
            for i in range(len(items))
        ]

    def _cls(self, model: str, labels: list[str], items) -> list[dict[str, float]]:
        batch = np.stack([_square(it.crop, 224).transpose(2, 0, 1) for it in items])
        probs = self._infer(model, "images", "output0", batch)
        return [dict(zip(labels, map(float, p), strict=True)) for p in probs]

    def classify_species(self, items):
        return self._cls("species_cls", SPECIES_LABELS, items)

    def classify_view(self, items):
        return self._cls("view_cls", VIEW_LABELS, items)

    def embed(self, items):
        batch = np.stack(
            [((_square(it.crop, 384) - IMAGENET_MEAN) / IMAGENET_STD).transpose(2, 0, 1) for it in items]
        )
        return _l2(self._infer("reid", "input", "embedding", batch))

    def versions(self):
        return dict(self._versions)


@lru_cache
def get_backend() -> InferenceBackend:
    return build_backend(get_settings())


def build_backend(s: Settings) -> InferenceBackend:
    if s.inference_backend == "triton":
        return TritonBackend(s.triton_url)
    if s.inference_backend == "local":
        return LocalBackend()
    return FakeBackend()
