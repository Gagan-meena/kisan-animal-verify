from kisan.ml.analyze import analyze
from kisan.ml.backends import FakeBackend
from kisan.ml.stages.context import AnalyzeContext
from kisan.ml.types import Detection
from tests.helpers import COW_VIEWS, frames, photo_set


def ctx(backend=None, views=COW_VIEWS, with_video=True, species="cow"):
    return AnalyzeContext(
        animal_id="a1",
        species=species,
        photos=photo_set(views),
        video_frames=frames() if with_video else [],
        backend=backend or FakeBackend(),
    )


def by_name(out):
    return {r.name: r for r in out.results}


def test_clean_listing_passes_all_stages():
    out = analyze(ctx())
    assert not out.hard_failed
    r = by_name(out)
    assert all(r[n].passed for n in ("quality", "detect", "species", "views", "identity")), [
        (x.name, x.flags, x.reupload) for x in out.results
    ]
    assert r["identity"].evidence["mode"] == "video_anchor"
    assert out.centroid is not None and len(out.centroid) == FakeBackend.dim
    assert len(out.phashes) == len(COW_VIEWS)


def test_different_animal_in_one_photo_is_flagged():
    out = analyze(ctx(FakeBackend(identity_group={"img_right": "B"})))
    r = by_name(out)["identity"]
    assert not r.passed
    assert r.evidence["outliers"] == ["img_right"]
    assert "RIGHT photo may show a different animal" in r.flags


def test_pairwise_mode_without_video():
    out = analyze(ctx(FakeBackend(identity_group={"img_face": "B"}), with_video=False))
    r = by_name(out)
    # VIDEO is required, so views stage stops the pipeline before identity
    assert out.stopped_at == "views"
    assert any(x.view == "VIDEO" for x in r["views"].reupload)


def test_species_mismatch_flagged_not_rejected():
    probs = {"buffalo": 0.95, "cow": 0.05}
    be = FakeBackend(species={f"img_{v.lower()}": probs for v in COW_VIEWS})
    r = by_name(analyze(ctx(be)))["species"]
    assert not r.passed and r.score == 0.05
    assert r.flags == ["photos look like a buffalo, listed as cow"]


def test_empty_frame_requests_reupload_and_stops():
    be = FakeBackend(detections={"img_left": []})
    out = analyze(ctx(be))
    assert out.stopped_at == "detect"
    assert [(x.view, x.reason) for x in by_name(out)["detect"].reupload] == [
        ("LEFT", "no animal found in this photo")
    ]


def test_two_big_animals_rejected():
    two = [Detection((0, 0, 600, 900), 0.9, "cow"), Detection((650, 0, 1270, 900), 0.88, "cow")]
    out = analyze(ctx(FakeBackend(detections={"img_front": two})))
    assert out.stopped_at == "detect"
    assert "more than one animal" in by_name(out)["detect"].reupload[0].reason


def test_left_right_swap_is_corrected_not_rejected():
    be = FakeBackend(views={"img_left": {"RIGHT": 0.9}, "img_right": {"LEFT": 0.9}})
    c = ctx(be)
    r = by_name(analyze(c))["views"]
    assert r.passed
    assert c.corrected_views == {"img_left": "RIGHT", "img_right": "LEFT"}


def test_wrong_view_requests_reupload():
    be = FakeBackend(views={"img_rear": {"FACE": 0.9}})
    r = by_name(analyze(ctx(be)))["views"]
    assert not r.passed
    assert r.reupload[0].reason == "this looks like a FACE photo, not REAR"
