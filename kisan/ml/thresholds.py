"""Starting thresholds. Calibrate on reviewer-labelled pilot data (rule 6) and version
them in the model registry with the weights they were tuned for."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    # quality
    min_short_side: int = 720
    min_blur_var: float = 100.0
    min_brightness: float = 40.0
    max_brightness: float = 220.0
    min_contrast: float = 20.0
    max_clipped_fraction: float = 0.25
    # detection
    det_conf: float = 0.50
    min_body_coverage: float = 0.10  # animal box / frame, full-body views
    second_animal_area: float = 0.15  # a 2nd animal this big => "multiple animals"
    # species / view
    species_conf: float = 0.90
    view_conf: float = 0.70
    # identity (cosine). Tune per Re-ID model version.
    same_animal_sim: float = 0.60
    identity_score_lo: float = 0.30  # weakest match at/below this => score 0
    identity_score_hi: float = 0.80  # weakest match at/above this => score 1
    # duplicate search across listings
    duplicate_sim: float = 0.92
    # fraud: photos within a listing this close in pHash are the same photo
    phash_same_photo: int = 6
    max_capture_span_hours: float = 24.0
    # video sampling
    video_frames: int = 6


DEFAULT = Thresholds()
