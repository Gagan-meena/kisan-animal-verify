# Kisan animal verification (pilot backend)

Verifies animal listings before they go live: photo quality, one animal per photo, species,
required views, same animal across all photos and the walk-around video, duplicate listings,
fraud signals and state sale rules. Built to the six architecture rules:

| Rule | Where in code |
|---|---|
| 1. Checks on the phone first | `services/media/routes.py` (in-app camera only, app version gate); server repeats every check in `ml/stages/quality.py` |
| 2. Kafka + Temporal | `events/` (outbox + relay), `services/verification/trigger.py`, `workflow.py`, `activities.py` |
| 3. Triton GPUs that scale | `ml/backends.py` (`TritonBackend`), `infra/triton_repo/`, `infra/k8s/triton-autoscale.yaml` |
| 4. Postgres split + Qdrant | `db/migrations/002_citus.sql` (distributed by `seller_id`), `vector.py` (one centroid per animal) |
| 5. Fraud + India data rules | `ml/stages/fraud.py`, `rules/engine.py`, `db/seed/state_rules.sql` |
| 6. Pilot in one state | `services/deps.py::pilot_gate`, `KISAN_ENABLED_STATES`, `pilot_human_confirms_all` |

## Flow

```
App ── POST /v1/listings ─────────────► Listing + Animal rows
    ── POST /v1/animals/{id}/media ───► presigned URL ──► PUT file straight to S3
    ── POST …/media/{img}/complete ───► outbox: media.uploaded
    ── POST /v1/animals/{id}/submit ──► outbox: verify.requested
                                          │ relay → Kafka → trigger
                                          ▼
                              Temporal VerifyAnimal workflow
     start_verification → analyze_media (GPU: quality, detect, species, views, identity)
     → fraud_and_rules (Qdrant duplicates, KYC, capture provenance, state law)
     → score → record_decision ─► VERIFIED / REUPLOAD / BLOCKED
                              └─► NEEDS_REVIEW: waits for reviewer signal (escalates after SLA)
     → index_identity (Qdrant) when verified
```

## Run locally

```bash
cp .env.example .env
docker compose up -d --build      # Postgres/Citus, Kafka, Temporal, Qdrant, MinIO, services
make migrate
open http://localhost:8080/docs   # API
open http://localhost:8233        # Temporal UI
```

`KISAN_INFERENCE_BACKEND=fake` runs the full pipeline without model weights. Use `local`
(`pip install .[local-ml]`, weights in `models/weights/`) or `triton` (`docker compose --profile gpu up`).

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

The two full Temporal workflow tests download the Temporal test server on first run and are
skipped when offline. Everything else (API, stages, scoring, fraud, relay, activities run
end to end on real images and an mp4) runs offline.

## Before the pilot goes live

- Train/fine-tune: species detector (6 classes), view classifier, Re-ID on your own photos.
- Calibrate `ml/thresholds.py` on reviewer-labelled data; keep `pilot_human_confirms_all=true` until the exit gate.
- Have a lawyer review `state_rules` for the pilot state, then set `legally_reviewed=true`.
- Replace header auth with your gateway's JWT validation; add a KYC provider.
- Add capture-signature verification (the app signs `capture_meta`; server currently checks presence only).
- Next modules: breed (Indian bovine model), ear-tag OCR, documents, age consistency.
