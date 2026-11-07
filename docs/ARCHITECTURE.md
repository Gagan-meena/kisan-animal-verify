# ARCHITECTURE — How Kisan Verification Fits Together

> **Read this when:** you add a service, a pipeline stage, a table or a Kafka topic.
> **The six rules** everything follows: ① checks on the phone first · ② Kafka + Temporal for background jobs · ③ Triton GPUs that scale · ④ Postgres split across servers + Qdrant · ⑤ fraud checks + India data rules · ⑥ pilot in one state.

---

## 1. The big picture

```
 ┌──────────── SELLER PHONE ① ────────────┐
 │ guided camera → on-device check → WebP │
 └───────┬───────────────────────┬────────┘
         │ API calls (JWT)       │ photos/video PUT straight to S3 (presigned)
         ▼                       ▼
 ┌─ India region ⑤ ───────────────────────────────────────────────────────────┐
 │  API gateway → pilot gate ⑥ → FastAPI services          S3 (ap-south-1)     │
 │                                  │ writes row + outbox row (1 transaction)  │
 │                                  ▼                                          │
 │                      outbox relay ──► Kafka ② ──► trigger ──► Temporal ②     │
 │                                                                  │          │
 │            ┌───────────── VerifyAnimal workflow ─────────────────┘          │
 │            ▼                                                                │
 │   analyze_media ──► Triton GPU pool ③ (autoscaled by KEDA on Kafka lag)     │
 │   fraud_and_rules ──► Qdrant ④ duplicate search · KYC · state rules ⑤       │
 │   score → record_decision ──► Postgres/Citus ④ ──► verify.decided event     │
 │   NEEDS_REVIEW? wait for reviewer signal (escalate after 4 h)               │
 │   VERIFIED? index_identity ──► Qdrant                                       │
 └─────────────────────────────────────────────────────────────────────────────┘
```

**Why this shape**

- Photos never pass through API pods → API stays small and cheap.
- Every write and its event are one DB transaction (outbox) → DB and Kafka never disagree.
- Temporal holds the per-listing state machine → crashes, deploys and 4-hour human waits cost nothing.
- GPU work is batched in Triton → 3–4 L4 GPUs cover the 62 photos/s peak.

## 2. Code map

```
kisan/
├── config.py                  settings (env prefix KISAN_)
├── db/models.py               ORM; all tenant tables keyed (seller_id, id)
├── db/session.py              async engine (PgBouncer-safe)
├── events/__init__.py         topic names + add_event() → outbox
├── events/relay.py            outbox → Kafka, single leader via advisory lock
├── storage.py                 S3 / MinIO / in-memory
├── vector.py                  Qdrant identity index (1 centroid per animal)
├── rules/policy.py            required views per species, file types
├── rules/engine.py            state law evaluation (pure)
├── ml/
│   ├── backends.py            fake | local | triton inference
│   ├── yolo.py                letterbox, decode, NMS, crop
│   ├── thresholds.py          ALL tunable numbers live here
│   ├── analyze.py             runs stages 1–5 in one pass
│   ├── stages/                quality · detect · species · view · identity · fraud · rules
│   └── scoring.py             weights → decision
└── services/
    ├── api.py                 FastAPI app (+ /dev/sellers in local/test)
    ├── deps.py                app-version gate, seller, pilot gate, reviewer
    ├── schemas.py             request / response models
    ├── media/routes.py        listings, upload URLs, submit
    └── verification/
        ├── routes.py          seller status, review queue / detail / decision
        ├── contracts.py       workflow payloads (sandbox-safe)
        ├── workflow.py        VerifyAnimal
        ├── activities.py      the 6 activities
        ├── trigger.py         Kafka → start workflow
        ├── worker.py          Temporal worker
        └── gateway.py         API → Temporal signal
db/migrations/                 001_init.sql, 002_citus.sql
db/seed/state_rules.sql        placeholder rules (legally_reviewed=false)
infra/triton_repo/             model configs
infra/k8s/                     Triton Deployment + KEDA ScaledObject
```

## 3. API

All `/v1` seller routes need `X-App-Version` ≥ `KISAN_MIN_APP_VERSION` and `X-Seller-Id` (set by the gateway from the JWT).

| Method | Path | Who | Does |
|---|---|---|---|
| `POST` | `/v1/listings` | seller (pilot state) | Create listing + animal. Returns `required_views`. |
| `POST` | `/v1/animals/{animal_id}/media` | seller | Register one photo/video, get presigned PUT URL (15 min). |
| `POST` | `/v1/animals/{animal_id}/media/{image_id}/complete` | seller | Confirm upload landed in S3 → `media.uploaded`. |
| `POST` | `/v1/animals/{animal_id}/submit` | seller | All views present → listing `VERIFYING` → `verify.requested`. |
| `GET` | `/v1/animals/{animal_id}/verification` | seller | Status + plain-language message + photos to retake. |
| `GET` | `/v1/review/queue` | reviewer | Oldest `NEEDS_REVIEW` first. |
| `GET` | `/v1/review/{seller_id}/{animal_id}` | reviewer | Full evidence, flags, model versions. |
| `POST` | `/v1/review/{seller_id}/{animal_id}` | reviewer | Decide → signals the workflow → `review.closed`. |
| `GET` | `/healthz` | infra | Liveness. |
| `POST` | `/dev/sellers` | local/test only | Create a seller. |

## 4. The verification pipeline

| # | Stage | Runs in | Model / method | Gate? | Weight |
|---|---|---|---|---|---|
| 1 | `quality` | analyze_media | OpenCV: size, Laplacian blur, brightness, contrast, clipping, pHash | hard | 15 |
| 2 | `detect` | analyze_media | YOLO11 (6 species) → crop | hard | – |
| 3 | `species` | analyze_media | species classifier, averaged over full-body views | flag | 20 |
| 4 | `views` | analyze_media | view classifier; LEFT/RIGHT swaps auto-corrected | hard | 10 |
| 5 | `identity` | analyze_media | Re-ID embeddings; photos vs video frames | flag | 30 |
| 6 | `fraud` | fraud_and_rules | pHash pairs, capture source, capture time span, KYC, Qdrant duplicates | retake / flag | – |
| 7 | `rules` | fraud_and_rules | `state_rules` row | block / flag | – |
| – | breed · tag · age | _not built_ | – | – | 10 · 5 · 10 |

**Hard gate** = stop the pipeline, ask for retakes. **Flag** = keep going, send to a human.
Unbuilt stages are left out and the remaining weights are re-normalised.

### How "same animal" works

```
 with video (normal):  each photo's best match against video frames ≥ 0.60
 without video:        each photo's best match against another photo ≥ 0.60
 video itself:         min frame-to-frame similarity ≥ 0.60
 centroid:             mean of matching embeddings → stored in Qdrant on approval
```
Best-match, not all-pairs: a left side and a right side rarely look alike, but both look like some frame of the walk-around.

### Decision ladder (`ml/scoring.py`)

```
 any stage blocked ............................ BLOCKED
 any photo to retake .......................... REUPLOAD
 score missing or < 60 ........................ REUPLOAD
 any flag, or score < 85 ...................... NEEDS_REVIEW
 pilot_human_confirms_all = true .............. NEEDS_REVIEW (ai_status = VERIFIED)
 otherwise .................................... VERIFIED
```

## 5. Workflow (`VerifyAnimal`)

```
start_verification ─► analyze_media ─(stopped?)─► fraud_and_rules ─► score ─► record_decision("ai")
                                                                               │
                         ┌──────────── NEEDS_REVIEW ───────────────────────────┤
                         ▼                                                     │
              wait for `reviewed` signal ── 4 h ──► record_decision("escalated") ─► keep waiting
                         │
                         ▼
              record_decision("review") ─► VERIFIED? ─► index_identity
```

| Activity | Timeout | Retries | Idempotent because |
|---|---|---|---|
| `start_verification` | 30 s | 10 | looks up existing row by `workflow_id` |
| `analyze_media` | 5 min, heartbeat 90 s | 3 | pure; no writes |
| `fraud_and_rules` | 30 s | 10 | read-only |
| `score` | 30 s | 10 | pure |
| `record_decision` | 30 s | 10 | `evidence.recorded` lists phases already written |
| `index_identity` | 30 s | 10 | Qdrant upsert by `animal_id` |

Workflow ID: `verify-{animal_id}-{attempt}` with `REJECT_DUPLICATE` → a redelivered Kafka event never starts a 2nd run.

## 6. Data

### Postgres (Citus, distributed by `seller_id`, colocated with `sellers`)

| Table | Key | Notes |
|---|---|---|
| `sellers` | `id` | `state`, `kyc_status` |
| `listings` | `(seller_id, id)` | `status`: DRAFT → VERIFYING → LIVE / NEEDS_REUPLOAD / BLOCKED → SOLD |
| `animals` | `(seller_id, id)` | declared species, breed, sex, `age_months`, `tag_id` (12 digits) |
| `animal_images` | `(seller_id, id, created_at)` | **monthly partitions**; `view`, `storage_key`, `capture_meta`, `uploaded` |
| `verifications` | `(seller_id, id)` | `status`, `score`, `evidence` jsonb, `flags`, `reasons`, `model_versions` |
| `reviews` | `(seller_id, id)` | reviewer decision + `labels` for training |
| `outbox` | `(seller_id, id)` | unpublished rows indexed |
| `state_rules` | `(state, species, action)` | **reference table** (copied to every node) |

### Kafka topics (12 partitions, key = `animal_id`)

`media.uploaded` · `verify.requested` · `verify.decided` · `review.closed` · `*.dlq`

### Qdrant `animal_identity`

1 point per **approved** animal · cosine · 6 shards × 2 replicas · int8 quantised · payload `species, status, state, seller_id, listing_id` · search filters `species` + `status=active`, excludes self.

### S3 keys

`sellers/{seller_id}/animals/{animal_id}/{image_id}.{webp|jpg|mp4}` — per-seller prefix makes DPDP deletion one prefix delete.

## 7. Inference backends (`KISAN_INFERENCE_BACKEND`)

| Value | Use | Needs |
|---|---|---|
| `fake` | tests, local end-to-end | nothing |
| `local` | dev laptop, very early pilot | `pip install .[local-ml]`, weights in `models/weights/` |
| `triton` | staging / prod | Triton with `infra/triton_repo` engines |

Triton models: `detector` (YOLO11m, 640², 6 classes) · `species_cls` (224², 6) · `view_cls` (224², 7) · `reid` (384², 1536-d).

## 8. Capacity (planning numbers)

| | |
|---|---|
| Photos / month | 16M (2M listings × 8) |
| Peak photo rate | ~62 / s (10× daily average) |
| GPUs at peak | 3–4 × L4 (~40 img/s each — **benchmark this**) |
| Storage growth | ~5.6 TB / month |
| Qdrant | 24M vectors / year ≈ 24 GB RAM int8 |

## 9. Run it

```bash
cp .env.example .env
docker compose up -d --build     # Citus, Kafka, Temporal, Qdrant, MinIO, api, relay, trigger, worker
make migrate
# API docs  → http://localhost:8080/docs
# Temporal  → http://localhost:8233
pytest -q
```
