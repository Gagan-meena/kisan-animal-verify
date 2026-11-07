"""Capture policy: which views each species must provide (rules 1 and 5)."""

from kisan.db.models import Species, View

FULL_BODY_VIEWS = frozenset({View.FRONT, View.LEFT, View.RIGHT, View.REAR})
CLOSE_UP_VIEWS = frozenset({View.FACE, View.MUZZLE, View.TAG})

_BASE = frozenset({View.FRONT, View.LEFT, View.RIGHT, View.FACE, View.VIDEO})

REQUIRED_VIEWS: dict[str, frozenset[View]] = {
    # Bovines: muzzle print is a strong biometric, ear tag is the national ID
    Species.COW: _BASE | {View.REAR, View.MUZZLE, View.TAG},
    Species.BUFFALO: _BASE | {View.REAR, View.MUZZLE, View.TAG},
    Species.GOAT: _BASE,
    Species.SHEEP: _BASE,
    Species.CAMEL: _BASE | {View.REAR},
    Species.HORSE: _BASE | {View.REAR},
}

MAX_IMAGES_PER_ANIMAL = 16
PHOTO_CONTENT_TYPES = frozenset({"image/webp", "image/jpeg"})
VIDEO_CONTENT_TYPES = frozenset({"video/mp4"})


def required_views(species: str) -> frozenset[View]:
    return REQUIRED_VIEWS.get(species, _BASE)
