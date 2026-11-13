# MEMORY — What We Decided and Learned

> **For humans and AI assistants.** Read this at the start of every session. Add to it at the end of every session.
> It answers: *where are we, what did we decide, and what bit us.*

---

## 📍 Where we are (update every session)

| | |
|---|---|
| **Last updated** | 2026-11-13 |
| **Milestone** | M0 done · Week 1 **Day 2 done** (KSN-035, KSN-038, KSN-030, KSN-034, KSN-086; checkpoint passed) — see [WEEK1](WEEK1.md) |
| **Backend** | Runs on laptop via docker compose. 49 tests pass (incl. Temporal). Worker creates the Qdrant collection on start. Open gaps: KSN-039/045–049, KSN-065–069, KSN-087–089. |
| **Models** | None trained. Pipeline runs on `KISAN_INFERENCE_BACKEND=fake`. |
| **App / console** | Not started. Spec in [DESIGN](DESIGN.md). |
| **Not safe to expose publicly** | Until KSN-040 (gateway auth) and KSN-045 (upload size cap) ship. |
| **Next** | Day 3: KSN-027 (zero-shot `LocalBackend`), KSN-028 (CLI). Use SideViewCows frames + Kaggle; own photos (DATA-1..3) before Day 5. |

---

## 🧭 Decisions (newest first)

Format: **date · decision** — why · what it rules out.

- **2026-11-13 · Worker calls `ensure_collection` on start; dim comes from the backend (`fake` 256, `triton` 1536); shards/replicas from config (`KISAN_QDRANT_SHARDS/REPLICAS`, default 1/1, prod 6/2).** A fresh Qdrant had no `animal_identity` → every `fraud_and_rules` failed with 404. *Rules out:* creating the collection by hand or in a migration script.
- **2026-11-13 · Reason codes: `ReuploadCode` StrEnum in `ml/types.py`; every `ReuploadItem` has a `code`; API `ReuploadOut.code` defaults to `other`.** The app translates codes, not English text. The default keeps old `verifications` rows readable (no 500). Codes: `blurry, too_dark, too_bright, too_small, low_contrast, clipped, too_far, many_animals, no_animal, wrong_view, missing, same_photo, use_camera, other`.
- **2026-11-13 · Quality gives one retake per photo; `code` = first problem in fix order** (too_small → blurry → too_dark/too_bright → low_contrast → clipped); `reason` joins all texts. The seller fixes the most basic thing first.
- **2026-11-13 · `ActivityError` in analyze / fraud / score → decision `NEEDS_REVIEW`, flag `automatic check failed`, then the normal review wait.** A listing must never stay `VERIFYING`. `start_verification` stays uncaught (no `vid` to record). *Known gap:* if a reviewer verifies such a listing, it is not indexed in Qdrant (no centroid) → KSN-088.
- **2026-11-13 · Trigger: `parse()` raises `ValueError` for any non-object JSON; the loop catches `Exception` around `parse()` only → DLQ.** `start()` sits in the `else`, so Temporal errors still crash the trigger and it resumes from the last commit. *Rules out:* a broad `except` around `start_workflow`.
- **2026-11-07 · `BLOCKED` is final; submit refuses it with 409, checked before the missing-photos check.** A blocked seller must not be asked for more photos, and fraudsters must not retry until a check misses. *Open:* same for `SOLD` (KSN-069).
- **2026-11-07 · Status checks come before content checks in submit:** load → `VERIFYING`/`LIVE` → `BLOCKED` → missing photos → submit.
- **2026-11-01 · Days 3–4 use public datasets (Kaggle Indian cattle + a Bristol cattle Re-ID set such as OpenCows2020) instead of own photos.** Couldn't shoot 8 views + video yet. Limits: no walk-around video (identity falls back to photo-vs-photo), few views per animal. Own photos still needed before Day 5.
- **2026-11-01 · MinIO image = `cgr.dev/chainguard/minio`; bucket init via `public.ecr.aws/aws-cli/aws-cli`.** MinIO deleted `minio/minio` and `minio/mc` from Docker Hub (Sep 2026) and quay.io needs an account. *Rules out:* `minio/*` and `quay.io/minio/*` images.
- **2026-11-01 · Container config lives in a `x-kisan-env` anchor in docker-compose; `.env` keeps `localhost` values for laptop pytest.** Inside a container `localhost` is the container itself.
- **2026-10-31 · Week 1 = learning build of a working demo on one machine.** Zero-shot models (YOLO11 COCO + CLIP + MegaDescriptor/DINOv2) instead of training; OTP + JWT lite; deploy with docker compose on one VM. *Rules out this week:* Citus multi-node, Triton/KEDA, Terraform, custom training, on-device YOLO.

- **2026-10-18 · Naive `captured_at` is treated as UTC.** Mixed naive/aware values crashed the fraud stage. Apps should always send an offset.
- **2026-10-09 · Pilot = Rajasthan only, and a human confirms every AI approval** (`pilot_human_confirms_all=true`). We need labelled data and proof of ≥ 98 % precision before trusting auto-approval. *Rules out:* auto-approve in the pilot.
- **2026-10-09 · Unreviewed state rules never auto-approve.** `state_rules.legally_reviewed=false` → flag for review. Seeds are placeholders, not law.
- **2026-10-09 · Walk-around video is required** for every species. It ties all views to one animal; without it, left and right sides rarely match each other.
- **2026-10-09 · "Same animal" uses best match, not all pairs.** Each photo must match at least one video frame (or one other photo). All-pairs fails on opposite sides.
- **2026-10-09 · One Qdrant vector per animal (centroid), written only after approval.** 8× fewer vectors; unapproved listings can't poison duplicate search.
- **2026-10-09 · Stages 1–5 run in one activity (`analyze_media`).** They share decoded images and crops; one activity each would re-download everything 5 times.
- **2026-10-09 · Hard gates vs flags.** Quality, detect and views stop the pipeline and ask the seller to retake. Species and identity only flag for a human, because a wrong "retake" message to an honest seller is worse than a review.
- **2026-10-09 · Sellers never see fraud flags.** They see plain messages; reviewers see evidence.
- **2026-10-09 · Citus, distributed by `seller_id`.** All of a seller's rows sit on one shard → single-shard writes. Every tenant PK starts with `seller_id`.
- **2026-10-09 · Transactional outbox, not direct Kafka writes.** DB and events can never disagree.
- **2026-10-09 · Workflow ID = `verify-{animal_id}-{attempt}`, `REJECT_DUPLICATE`.** Kafka is at-least-once; this makes starts idempotent.
- **2026-10-09 · Age is "consistent", never "verified".** Photos cannot prove age.
- **2026-10-09 · In-app camera only.** No gallery uploads; server refuses `source != in_app_camera`.

---

## ⚠️ Gotchas (things that already bit us)

| Area | Gotcha | Fix |
|---|---|---|
| Temporal | Fake activities in tests got a `dict` (`'dict' object has no attribute 'phase'`). Cause: **no type hint** on the activity parameter, not the Python version | always type-hint activity params (`inp: RecordInput`); Temporal decodes JSON by the hint |
| Temporal | `execute_activity` raises `ActivityError` after the last retry; uncaught → workflow fails → listing stuck | catch it in the workflow (KSN-030) |
| Temporal | History shows only the **final** activity failure; the retries in between are invisible | read the last `ActivityTaskFailed` message, or the worker logs |
| Temporal | Fake backend is too fast to kill the worker "mid-run" | stop the worker **before** submit, then start it again |
| Temporal | With `pilot_human_confirms_all`, a workflow completes only after a review is posted | `POST /v1/review/{seller_id}/{animal_id}` |
| Qdrant | Fresh Qdrant has no `animal_identity` → 404 in `fraud_and_rules`, retried 10× (~2.5 min) | worker `ensure_collection` on start (KSN-086); fail fast on config errors (KSN-087) |
| Pydantic | Adding a required field to a response model breaks reading old JSON rows (500) | give the new field a default |
| SQLAlchemy | `Mapped[dict[str, Any]]` without a column type → `MappedAnnotationError` on import | keep `Mapped[dict]` or give the type: `mapped_column(JSONB)` |
| Tests | `"dark" in ("too_dark", "…")` checks tuple elements, not substrings | assert on the code: `ReuploadCode.TOO_DARK in codes` |
| Docker | `.env` is **not** passed into containers; only `x-kisan-env` is | check inside: `docker compose exec verify-worker python -c "…settings…"` |
| Kafka | `kafka-console-consumer --timeout-ms` ends with `TimeoutException` | normal; it just stopped waiting |
| Kafka | apache/kafka image: tools live in `/opt/kafka/bin/` | `docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh …` |
| Docker | Code is baked into the image: after editing Python, `restart` still runs old code (new route → 405) | `docker compose up -d --build api` (or mount the code as a volume in dev) |
| Docker | `minio/minio`, `minio/mc` gone from Docker Hub; quay.io returns 401. One failed pull aborts the whole `compose up` | Chainguard MinIO image; aws-cli image for bucket init |
| Docker | Chainguard MinIO runs as user 65532 | `chown` bind-mounted data dirs (named volumes are fine) |
| Docker | Services crash-loop with `Connection refused 127.0.0.1:7233` / `localhost:9092` — config defaults are `localhost` | set `KISAN_*` hosts to service names (`kafka:9092`, `temporal:7233`, `postgres`, `qdrant`, `minio`) in compose |
| Docker | Trigger/worker log `dns error` for `temporal` right after `compose up` | Temporal still starting; they restart on their own |
| Docker | `KISAN_S3_PUBLIC_ENDPOINT` must stay `http://localhost:9000` | presigned URLs must be reachable from the laptop / phone, not just containers |
| S3 | Upload URL had `X-Amz-Credential=<MINIO_ROOT_USER>` → MinIO rejects | real values in `KISAN_S3_ACCESS_KEY` / `KISAN_S3_SECRET_KEY` (in `.env` and `x-kisan-env`), rebuild, request a new upload slot |
| curl | `--data-binary path.jpg` uploads the text of the path | `--data-binary @"$IMG"`; put long presigned URLs in a single-quoted variable |
| Swagger | Path params keep the example UUID `3fa85f64-…` → 404 | paste the real `animal_id` / `image_id` |
| Swagger | `/dev/sellers` with `"state": "string"` → 500 (`character(2)`) | send `"RJ"`; validation in KSN-067 |
| Setup | Venv on Python 3.14 (system default); project targets 3.12 | `uv venv -p 3.12 .venv && uv pip install -e ".[dev]"`; old `*.cpython-314.pyc` files linger — `grep --include=*.py` |
| Setup | No `.env.example` in the repo; names come from `kisan/config.py` (`KISAN_` + field name) | KSN-068 |
| Setup | Relay crashes with `relation "outbox" does not exist` | run `make migrate` after first `compose up` |
| Setup | No `requirements.txt` | `pip install -e ".[dev]"` (deps in `pyproject.toml`) |
| Git | `.env` untracked would be pushed by `git add -A` | `.gitignore` (KSN-068); add files by name |
| SQL | Join `listings`↔`animals` on `seller_id` only → every listing × every animal (duplicates) | join on `(seller_id, listing_id)`; filter `where Listing.seller_id == seller.id`. Join = how tables link; where = whose rows |
| Tests | A 409 test can pass for the wrong reason (missing photos also returns 409) | assert the message, not only the status code |
| Temporal | Sandbox validation needs a running event loop | call `prepare_workflow` inside `asyncio.run` (see `test_workflow.py`) |
| Temporal | Test server is downloaded at runtime; blocked in offline sandboxes | tests skip offline; on the laptop they run |
| Temporal | `workflow.py` must only import from `contracts.py` + activities via `imports_passed_through` | keep heavy imports out of workflow code (`temporalio.*` is fine) |
| Config | pydantic-settings tries to JSON-decode `KISAN_ENABLED_STATES=RJ,MP` | field is `Annotated[frozenset[str], NoDecode]` |
| Postgres | Partitioned table PK must include the partition key | `animal_images` PK is `(seller_id, id, created_at)` in SQL; ORM uses `(seller_id, id)` |
| Citus | Distributed tables need the distribution column in every unique key | every tenant PK starts with `seller_id` |
| asyncpg | PgBouncer (transaction mode) breaks prepared statements | `statement_cache_size=0` in `db/session.py` |
| Postgres | Session advisory locks (relay leader) are unreliable behind PgBouncer transaction mode, and the lock connection sits idle-in-transaction forever | direct connection + re-check, or `SKIP LOCKED` (KSN-046) |
| S3 | Presigned PUT URLs do not limit file size | presigned POST with `content-length-range` or HEAD-check size (KSN-045) |
| API | "Latest verification row" lags a resubmit until the worker creates the new row | trust `listing.status == VERIFYING` first (KSN-039) |
| Tests | Tests use SQLite via `Base.metadata.create_all`, prod uses SQL migrations | change both when you change a table; re-run the Postgres smoke |
| FastAPI | `HTTP_422_UNPROCESSABLE_ENTITY` is deprecated | use the literal `422` |
| Fake backend | Puts every image in identity group `"A"` | that's why a 2nd seeded listing is flagged as a duplicate in tests |
| Quality | Blur is measured after resizing to 1024 px long side | thresholds don't depend on upload resolution |

---

## 📖 Words we use

| Word | Means |
|---|---|
| **View** | Which angle a photo shows: FRONT, LEFT, RIGHT, REAR, FACE, MUZZLE, TAG, VIDEO |
| **Hard gate** | A stage failure that stops the pipeline and asks for retakes |
| **Flag** | A note for a human reviewer; never shown to the seller |
| **Attempt** | Nth submission of the same animal; part of the workflow ID |
| **Centroid** | Average Re-ID embedding of an approved animal, stored in Qdrant |
| **Outlier** | A photo whose best match is below `same_animal_sim` (0.60) |
| **Exit gate** | Metrics that must pass before a 2nd state (PRD §5) |
| **ai_status** | What the AI alone decided, kept even when a human confirms |
| **Poison pill** | A message a consumer can never process; without a DLQ it blocks its partition forever |
| **BLOCKED** | Final "no" for a listing: state rules forbid the sale, or a reviewer blocked it (usually fraud). Never resubmittable |
| **Reason code** | Machine name for a retake reason (`blurry`, `too_dark` …); the app shows its own translated text |

---

## 📝 Session log

- **2026-11-13** — Day 2 done. KSN-035 (fake activities lacked type hints), KSN-038 (poison pill → DLQ), KSN-030 (activity failure → NEEDS_REVIEW), KSN-034 (reason codes), KSN-086 (Qdrant collection on start; found at the checkpoint — KSN-030 caught it live). Checkpoint: worker stopped → submit → start → review → Completed + indexed; `[1]`, `null`, `"x"` in DLQ, trigger stayed up. 49 passed. Added KSN-087–089.
- **2026-11-07** — Day 1 done. Checkpoint: seller → listing → presigned PUT → complete → `media.uploaded` published. Built KSN-037 (`GET /v1/listings`, 3 tests; test caught a join bug) and KSN-031 (409 on `BLOCKED` resubmit). 40 passed, 2 Temporal fail. Added KSN-065–069.
- **2026-11-01 (c)** — No own photos yet; chose public datasets for Days 3–4, own photos before Day 5.
- **2026-11-01 (b)** — Day 0 setup on laptop: swapped MinIO images, added compose `x-kisan-env`, wrote `.env`, migrated, bucket `kisan-animal-images`. 36 passed, 2 Temporal tests fail locally (→ KSN-035). Photos pending.
- **2026-11-01** — Code review of the backend zip. Added KSN-038/039/045–049 (trigger poison pill, stale status, upload size cap, relay leadership + batching, review consistency, upload rules) and 4 gotchas.
- **2026-10-31** — Wrote the one-week learning plan (docs/WEEK1.md). Added KSN-027/028/029.
- **2026-10-18** — Wrote the six docs. Fixed mixed time-zone crash in fraud stage (+ test). Listed known gaps as KSN-030…064.
- **2026-10-09** — Architecture agreed (6 rules). Built backend M0: API, outbox/Kafka/Temporal, 7 stages, scoring, Triton configs, tests, Postgres smoke.

<!-- AI assistants: append a dated line above, update "Where we are", and add any decision you made. Keep entries one line. -->
