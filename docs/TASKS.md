# TASKS — Feature Tickets

> **This week:** follow [WEEK1](WEEK1.md) — it picks tickets from M1–M5 in learning order.
> **How to use:** pick the first unchecked ticket in the current milestone. Each ticket has an ID, size and a "done when". Tick it here in the same PR that finishes it, and add a line to [MEMORY](MEMORY.md) if you made a decision.
> Sizes: **S** ≤ 1 day · **M** 2–4 days · **L** 1–2 weeks

---

## 🗺️ Milestones

```
 M0 Backend core ──► M1 Pilot-ready backend ──► M2 Models ──► M3 Seller app ──► M4 Review console ──► M5 Go live (RJ)
      done ✅              in progress            parallel        parallel           parallel          exit gate → M6
```

---

## M0 · Backend core ✅

- [x] **KSN-001** · S · Repo, Dockerfile, docker-compose (Citus, Kafka, Temporal, Qdrant, MinIO) — *done when* `docker compose up` starts all services
- [x] **KSN-002** · M · Schema + migrations: Citus distribution by `seller_id`, monthly `animal_images` partitions, outbox, `state_rules` — *done when* migrations apply on Postgres 16
- [x] **KSN-003** · M · Listing + media API with presigned S3 uploads and upload confirmation
- [x] **KSN-004** · S · Pilot gate (`KISAN_ENABLED_STATES`) and app-version gate (426)
- [x] **KSN-005** · S · Outbox relay with Postgres advisory-lock leader election
- [x] **KSN-006** · S · Kafka trigger → Temporal, idempotent workflow IDs, DLQ
- [x] **KSN-007** · M · `VerifyAnimal` workflow: review wait, 4 h SLA escalation, identity indexing
- [x] **KSN-008** · L · Stages: quality, detect, species, views (LEFT/RIGHT auto-fix), identity (video-anchored)
- [x] **KSN-009** · M · Fraud stage (same photo twice, gallery, capture span, KYC, duplicates) + state rules engine
- [x] **KSN-010** · S · Scoring, decision ladder, pilot "human confirms all" mode
- [x] **KSN-011** · M · Seller status API + review queue / detail / decision API
- [x] **KSN-012** · M · Inference backends `fake` / `local` / `triton`, Triton configs, KEDA autoscaling
- [x] **KSN-013** · M · Test suite (36 tests) + real-Postgres smoke run
- [x] **KSN-014** · S · Fix: mixed time-zone `captured_at` values crashed the fraud stage

## M1 · Pilot-ready backend

- [x] **KSN-030** · S · Failed workflow → `NEEDS_REVIEW` with flag "automatic check failed" — *done 2026-11-13*: `ActivityError` in analyze / fraud / score caught in the workflow; test with a failing fake `analyze_media`. Proved live at the Day 2 checkpoint (Qdrant 404). *Still open:* alert ops (with KSN-052)
- [x] **KSN-031** · S · Refuse resubmit of `BLOCKED` listings (409) — *done 2026-11-07*: check runs before the missing-photos check; test asserts the message, not only the 409
- [ ] **KSN-032** · S · On sale / delete, set Qdrant point `status` to `sold` / `removed` (`IdentityIndex.set_status` exists, unused)
- [ ] **KSN-033** · S · Nightly job: delete `animal_images` rows with `uploaded=false` older than 24 h
- [x] **KSN-034** · M · Reason codes next to text in `reupload[]` — *done 2026-11-13*: `ReuploadCode` StrEnum; every stage sets `code`; quality uses the first problem in fix order; `ReuploadOut.code` defaults to `other` for old rows (test). Copy for new codes in DESIGN §4.6
- [x] **KSN-035** · S · Run the 2 Temporal workflow tests — *done 2026-11-13*: fake activities lacked type hints, so Temporal passed `dict`. Run locally; CI still needs network for the test server (KSN-082)
- [ ] **KSN-036** · M · Notification consumer: `verify.decided` → push / SMS in the seller's language
- [x] **KSN-037** · S · `GET /v1/listings` for the seller's own listings (My listings screen) — *done 2026-11-07*: newest first, 3 tests (order, only own, empty)

### Found in code review (2026-11-01)
- [x] **KSN-038** · S · Trigger poison pill → DLQ — *done 2026-11-13*: `parse()` raises `ValueError` for non-object JSON (5-case test); loop catches any parse error; `start()` stays outside the `try`. Checkpoint: `[1]`, `null`, `"x"` landed in `verify.requested.dlq`, trigger stayed up
- [ ] **KSN-039** · S · Stale status after resubmit: `GET …/verification` returns the latest `verifications` row, so until the worker creates the new row the app sees the old `REUPLOAD`. If `listing.status == VERIFYING` and the latest row is decided, return `PENDING` — *done when* test: REUPLOAD → resubmit → status is PENDING
- [ ] **KSN-045** · S · Upload size cap: presigned PUT has no size limit and `analyze_media` reads whole files into memory (5 GB "video" → worker OOM ×3 retries). Use presigned POST with `content-length-range`, or HEAD-check size in `complete_upload` (photo ≤ 5 MB, video ≤ 50 MB, numbers in `rules/policy.py`) — *done when* oversized file gets 413/422 and never reaches the worker
- [ ] **KSN-046** · M · Relay leadership: lock is held on one idle-in-transaction connection and never re-checked; if it drops, two relays send at once. Session advisory locks are also unsafe behind PgBouncer transaction mode. Use a direct (non-PgBouncer) connection and re-check every loop, or drop the leader and claim rows with `FOR UPDATE SKIP LOCKED` — *done when* killing the lock connection stops the old relay from sending
- [ ] **KSN-047** · S · Relay throughput: `send_and_wait` per row = one round-trip each. Batch `send()` then await all futures before marking `published_at` — *done when* relay benchmark shows ≥ 10× rows/s
- [ ] **KSN-048** · M · Review submit consistency: `submit_review` commits the `Review` row + `review.closed` before signalling Temporal; a failed signal leaves a saved label for a decision that never happened, and two reviewers can both pass the `NEEDS_REVIEW` check. Lock the verification row (`SELECT … FOR UPDATE`) / mark it `IN_REVIEW`, signal first or emit `review.closed` from the workflow's `record_decision("review")` — *done when* concurrent reviews produce exactly one `review.closed` (pairs with KSN-053)
- [ ] **KSN-049** · S · Upload rules: `request_upload` only refuses during `VERIFYING`; also refuse `LIVE` / `BLOCKED` / `SOLD` (RULES §6). Make the 48-upload cap atomic (count + insert race) — *done when* tests cover each status and parallel requests can't exceed the cap

### Found on Day 0–1 (2026-11-07) · week 2+
- [ ] **KSN-065** · S · Check `state_rules` at `POST /v1/listings`: refuse a species that can't be sold in the seller's state *before* the farmer takes 8 photos. Keep the pipeline rules stage too (rules and docs change). Unreviewed rules (`legally_reviewed=false`) never block — *done when* a blocked species gets 403/409 with a plain message at create time
- [ ] **KSN-066** · M · Seller suspension: `sellers.status` (`ACTIVE` / `SUSPENDED`); after N `BLOCKED` listings (N in config) open a case for a human to confirm — never auto-suspend on AI blocks alone; appeal path; suspended sellers get 403 on create/submit — *done when* tests cover threshold, human confirm and 403
- [ ] **KSN-067** · S · Dev seller validation: `POST /dev/sellers` with `"state": "string"` crashes with 500 (`value too long for type character(2)`). Validate `state` as `^[A-Z]{2}$` → 422
- [ ] **KSN-068** · S · Repo hygiene: add `.gitignore` (`.env`, `.venv/`, `*.egg-info/`, `models/weights/`, `__pycache__/`) and a `.env.example` with placeholder values; keep docs only in `docs/` (remove root duplicates)
- [ ] **KSN-069** · S · Decide: should `SOLD` listings also be refused on submit (same as `BLOCKED`)? Record the decision in MEMORY

### Found on Day 2 (2026-11-13)
- [x] **KSN-086** · S · Create the Qdrant collection on worker start — *done 2026-11-13*: `main()` calls `index.ensure_collection(backend.dim, shards, replicas)`; `KISAN_QDRANT_SHARDS/REPLICAS` (default 1/1, prod 6/2); no-op in the in-memory index. *Note:* two workers starting at once can race on create — make it tolerate "already exists" before scaling workers
- [ ] **KSN-087** · S · Fail fast on config errors: a missing Qdrant collection (404) was retried 10× (~2.5 min) before the workflow gave up. Raise non-retryable `ApplicationError` for 4xx config errors in `fraud_and_rules` — *done when* a 404 fails on the 1st attempt and the listing goes to `NEEDS_REVIEW`
- [ ] **KSN-088** · S · Animals verified by a reviewer after an analysis failure have no centroid, so they are never indexed and duplicate search misses them. Re-run `analyze_media` before `index_identity`, or queue them for indexing later — *done when* such an animal has a Qdrant point
- [ ] **KSN-089** · S · `wrong_view` copy needs `{seen}` ("This looks like the FACE photo"), but `reupload[]` only has `view`. Add `seen` to `ReuploadItem`/`ReuploadOut` (default `null`) — *done when* the app can fill both placeholders

### Security & compliance
- [ ] **KSN-040** · L · Gateway: phone OTP login, JWT validation, sets `X-Seller-Id` / `X-Reviewer-Id` only from verified tokens, staff SSO — **blocks public exposure**
- [ ] **KSN-041** · M · Verify `capture_meta.sig` with a per-install key + Play Integrity attestation
- [ ] **KSN-042** · M · KYC provider integration → `sellers.kyc_status`
- [ ] **KSN-043** · M · Postgres row-level security on tenant tables (defence in depth)
- [ ] **KSN-044** · S · Gateway rate limits per user and per device
- [ ] **KSN-063** · M · Consent capture (listing, verification, training opt-in) and store it
- [ ] **KSN-064** · M · Seller deletion job: S3 prefix + DB rows + Qdrant points, with audit record

## M2 · Models

- [ ] **KSN-020** · L · Collect pilot dataset with consent: ~2,000 animals in RJ, all views + video, plus same-animal re-shoots a week apart
- [ ] **KSN-021** · L · Train YOLO11m detector, 6 species — *done when* mAP50 ≥ 0.90 on a held-out RJ set
- [ ] **KSN-022** · M · Train view classifier (7 views) — *done when* accuracy ≥ 95 %
- [ ] **KSN-023** · L · Re-ID: test MegaDescriptor zero-shot, then fine-tune on labelled pairs — *done when* ≥ 98 % of "same animal" pairs pass at ≤ 1 % false match
- [ ] **KSN-027** · M · Zero-shot `LocalBackend`: YOLO11 COCO detector, CLIP species + views, MegaDescriptor / DINOv2 embeddings (stopgap until KSN-021/022). Must expose `dim` (used by `ensure_collection`)
- [ ] **KSN-028** · S · CLI `python -m kisan.tools.try_photos <folder>` printing every stage result
- [ ] **KSN-029** · S · `eval/same_animal.py`: same vs different pairs → similarity histogram + match rate per threshold
- [ ] **KSN-024** · M · Calibrate `ml/thresholds.py` on labelled data; version thresholds with weights
- [ ] **KSN-025** · M · Export TensorRT FP16, benchmark on L4 — *done when* throughput per GPU is measured (plan assumes ~40 img/s)
- [ ] **KSN-026** · M · On-device YOLO11n TFLite — *done when* ≤ 5 MB and < 150 ms on a 2 GB Android phone

## M3 · Seller app (Flutter)

- [ ] **KSN-070** · M · App skeleton, OTP login, Hindi + English, design tokens from DESIGN §2
- [ ] **KSN-071** · M · New listing form (DESIGN §4.2)
- [ ] **KSN-072** · L · Guided camera with live checks + silhouettes (DESIGN §4.3) — needs KSN-026
- [ ] **KSN-073** · S · 5-second walk-around video step
- [ ] **KSN-074** · M · Resumable background upload queue that survives app kill (DESIGN §4.4)
- [ ] **KSN-075** · M · Submit, checking and result screens (DESIGN §4.5–4.6) — map `reupload[].code` (KSN-034 ✅)
- [ ] **KSN-076** · S · Push notifications (needs KSN-036)
- [ ] **KSN-077** · S · My listings screen (needs KSN-037 ✅)

## M4 · Review console (React)

- [ ] **KSN-050** · M · Queue screen with SLA colours and keyboard navigation
- [ ] **KSN-051** · L · Case screen: photo grid with per-photo similarity, outlier outline, duplicate side-by-side, decision + labels, shortcuts
- [ ] **KSN-052** · S · Alert ops when a case passes the 4 h SLA, and when a workflow hits "automatic check failed"
- [ ] **KSN-053** · S · Lock a case to one reviewer while open
- [ ] **KSN-091** · S · Reviewer playbook: what "same animal" means, when to block

## M5 · Go live in Rajasthan

- [ ] **KSN-080** · L · Terraform (ap-south-1): VPC, EKS, MSK, S3, Citus cluster, Qdrant ×3, Temporal (Cloud or HA)
- [ ] **KSN-081** · M · Helm charts for api, relay, trigger, worker, Triton
- [ ] **KSN-082** · S · CI: ruff, pytest (incl. Temporal tests, needs network), image build and scan
- [ ] **KSN-083** · M · Observability: OpenTelemetry traces, Prometheus, dashboard for the **exit-gate metrics** (PRD §5)
- [ ] **KSN-084** · M · Load test at 2× planned peak (~125 photos/s)
- [ ] **KSN-085** · S · Backups (PITR, S3 replication, Qdrant snapshots) + one restore drill
- [ ] **KSN-090** · S · Lawyer reviews RJ `state_rules`; set `legally_reviewed = true`
- [ ] **KSN-060** · M · Buyer read model: only `LIVE` listings, public fields
- [ ] **KSN-061** · S · Buyer image access via CDN signed URLs
- [ ] **KSN-062** · S · Strip EXIF/GPS from buyer-facing images

## M6 · After the exit gate (later)

- [ ] **KSN-100** · M · Breed stage (Indian bovine breeds model, validated on own photos)
- [ ] **KSN-101** · L · Ear-tag detection + OCR, cross-check with `animals.tag_id`
- [ ] **KSN-102** · L · Document upload + OCR (vet, ownership)
- [ ] **KSN-103** · M · Muzzle Re-ID as a second identity signal
- [ ] **KSN-104** · L · Age-range consistency (dental stage + records)
- [ ] **KSN-105** · M · Turn off `pilot_human_confirms_all` where precision is proven; enable 2nd state
