from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from kisan.ml.backends import InferenceBackend
from kisan.ml.thresholds import DEFAULT, Thresholds
from kisan.ml.types import MediaItem


@dataclass
class AnalyzeContext:
    animal_id: str
    species: str  # declared by seller
    photos: list[MediaItem]
    video_frames: list[MediaItem]
    backend: InferenceBackend
    th: Thresholds = DEFAULT
    centroid: np.ndarray | None = None
    # LEFT/RIGHT swaps corrected by the view stage: image_id -> corrected view
    corrected_views: dict[str, str] = field(default_factory=dict)

    def effective_view(self, item: MediaItem) -> str:
        return self.corrected_views.get(item.image_id, item.view)
