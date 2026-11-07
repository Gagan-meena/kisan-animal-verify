# WEEK 1 — Build While Learning

> **Goal:** in 7 days, a working demo: a seller lists a real animal from a phone, the AI checks it, a reviewer approves it, and it goes live.
> **Rule:** learn one idea, build with it the same day, prove it with a demo. Tick tickets in [TASKS](TASKS.md), log decisions in [MEMORY](MEMORY.md).

## Assumptions

- You know Python and FastAPI, and have used Qdrant.
- Kafka, Temporal, YOLO/CLIP and Flutter are new to you.
- About 7 hours a day, an Android phone, a laptop with 16 GB RAM.
- The backend from M0 already exists. You learn it by extending it, not by retyping it.

## Daily rhythm (≈ 7 h)

| Time | Step | What |
|---|---|---|
| 60 min | **Learn** | Concept brief + read the repo files listed for the day |
| 4–5 h | **Build** | You write the tickets; paste code to Claude for review |
| 30 min | **Prove it** | Run the checkpoint demo; it must work end to end |
| 15 min | **Remember** | Update docs/MEMORY.md and tick docs/TASKS.md |

## How we pair

1. Start each day by saying “Day N”. You get a 10-minute concept brief and hints, not the answer.
2. You write the code. Paste it for review: bugs, rule breaks (docs/RULES.md §8), missing tests.
3. Stuck for more than 45 minutes on one thing: ask for the answer, read it, then type it yourself.
4. End each day by answering the self-check questions out loud or in MEMORY.md.

## The week at a glance

| Day | Theme | Proof at the end of the day |
|---|---|---|
| 0 | Set up and collect photos | `pytest -q` shows 36 passed, and photos/ has at least 6 animal folders. |
| 1 | Follow one request through the backend | In Swagger: create a seller and a listing, `curl -X PUT` a real photo to the presigned MinIO URL, call complete, and see the `media.uploaded` row in the outbox table. |
| 2 | Events that never get lost | Submit a listing, run `docker compose stop verify-worker` mid-run, start it again, and watch the workflow finish in the Temporal UI. Send a broken message to Kafka and find it in the DLQ topic. |
| 3 | Real computer vision, no training | Run the CLI on all your animals. Photos of one animal pass identity; swap one photo with another animal's and see it flagged. |
| 4 | Measure before you trust | A chart of same-animal vs different-animal similarity, and the chosen thresholds written in MEMORY.md with their numbers. |
| 5 | The seller app | On your phone: create a listing, take 8 photos and the video, submit, and see “Checking” turn into a result. |
| 6 | The reviewer, and real sign-in | Full loop: phone submits → reviewer approves in the browser → phone shows Verified. A request with a forged `X-Seller-Id` and no token gets 401. |
| 7 | Ship the demo | The demo works on your phone over mobile data, away from your home Wi-Fi. |

---

## Day 0 · Set up and collect photos

*2–3 h, before Day 1*

**Goal:** Everything runs on your laptop, and you have real animal photos for Day 3.

**Build**

- [ ] **SETUP-1** Install Docker, Python 3.12, Node 20, Flutter (with Android Studio); turn on USB debugging on your phone
- [ ] **SETUP-2** Unzip the repo, `cp .env.example .env`, `docker compose up -d --build`, `make migrate`, `pytest -q`
- [ ] **SETUP-3** Open http://localhost:8080/docs and http://localhost:8233 (Temporal UI)
- [ ] **DATA-1** Photograph 6+ animals at a nearby dairy: all 8 views + a 5-second walk-around video each
- [ ] **DATA-2** Photograph 2 of those animals again on another day (needed for same-animal tests)
- [ ] **DATA-3** Save as photos/animal_01/FRONT.jpg … VIDEO.mp4; write species in photos/labels.csv

**✅ Checkpoint:** `pytest -q` shows 36 passed, and photos/ has at least 6 animal folders.

> **Plan B:** No dairy nearby: use a public cattle re-identification dataset (for example OpenCows2020 or Cows2021) for Days 3–4 and shoot your own later.


---

## Day 1 · Follow one request through the backend

**Goal:** You can explain every hop from “seller taps Create” to a row in the outbox.

**Learn**

- **FastAPI dependencies** — kisan/services/deps.py — app-version gate, seller, pilot gate
- **Async SQLAlchemy + composite keys** — kisan/db/models.py, kisan/db/session.py
- **Postgres partitions** — db/migrations/001_init.sql — animal_images by month
- **Presigned uploads** — kisan/storage.py, kisan/services/media/routes.py
- **Transactional outbox** — kisan/events/__init__.py

**Build**

- [ ] **KSN-037** `GET /v1/listings`: the seller's own listings, newest first, with status (+ tests)
- [ ] **KSN-031** Refuse resubmit of a `BLOCKED` listing with 409 (+ test)

**✅ Checkpoint:** In Swagger: create a seller and a listing, `curl -X PUT` a real photo to the presigned MinIO URL, call complete, and see the `media.uploaded` row in the outbox table.

**Self-check**

- Why does every query use `(seller_id, id)` instead of just `id`?
- What could go wrong if the request handler sent the Kafka event directly?


---

## Day 2 · Events that never get lost

**Goal:** You can kill any process mid-verification and the listing still finishes.

**Learn**

- **Kafka basics** — topics, partitions, consumer groups, offsets — kisan/services/verification/trigger.py
- **Outbox relay + leader lock** — kisan/events/relay.py
- **Temporal workflows vs activities** — kisan/services/verification/workflow.py
- **Retries, timeouts, signals, timers** — workflow.py + activities.py
- **Determinism rules** — docs/RULES.md §8 rule 5

**Build**

- [ ] **KSN-030** Workflow failure (e.g. models down) → `NEEDS_REVIEW` with flag “automatic check failed”, never stuck in `VERIFYING`
- [ ] **KSN-034** Reason codes (`blurry`, `too_dark`, `wrong_view`…) next to text in `reupload[]`
- [ ] **KSN-035** Run the 2 Temporal workflow tests on your laptop (they skip in Claude's sandbox)

**✅ Checkpoint:** Submit a listing, run `docker compose stop verify-worker` mid-run, start it again, and watch the workflow finish in the Temporal UI. Send a broken message to Kafka and find it in the DLQ topic.

**Self-check**

- The relay sends an event twice. What stops a second verification?
- Why can't `workflow.py` call `datetime.now()` or the database?


---

## Day 3 · Real computer vision, no training

**Goal:** The pipeline runs on your real photos with pretrained models.

**Learn**

- **Object detection** — boxes, confidence, NMS, letterboxing — kisan/ml/yolo.py
- **Zero-shot classification** — CLIP: compare an image with text like “a photo of a buffalo”
- **Embeddings + cosine similarity** — kisan/ml/stages/identity.py
- **Why crop before embedding** — kisan/ml/stages/detect.py

**Build**

- [ ] **KSN-027** Zero-shot `LocalBackend`: YOLO11 (COCO) detector, CLIP for species and views, MegaDescriptor or DINOv2 embeddings
- [ ] **KSN-028** CLI `python -m kisan.tools.try_photos photos/animal_01` that prints every stage result

**✅ Checkpoint:** Run the CLI on all your animals. Photos of one animal pass identity; swap one photo with another animal's and see it flagged.

**Self-check**

- COCO YOLO has no “buffalo” class. Which stage catches a buffalo listed as a cow?
- Why does the left side match video frames better than it matches the right side?

> **Plan B:** Models too slow on CPU: use YOLO11n and DINOv2-small today, swap to bigger models on a GPU later.


---

## Day 4 · Measure before you trust

**Goal:** Every threshold has a number from your own data behind it.

**Learn**

- **Precision, recall, false match rate** — why “98 % precision” is the pilot exit gate (docs/PRD.md §5)
- **Threshold curves** — trade-off between false matches and false rejects
- **Duplicate search** — kisan/vector.py — Qdrant filters and the centroid idea

**Build**

- [ ] **KSN-029** `eval/same_animal.py`: same vs different pairs → similarity histogram + table of match rate at each threshold
- [ ] **KSN-024** Set `same_animal_sim`, `species_conf`, `view_conf` in `ml/thresholds.py` from the eval; record why in MEMORY.md
- [ ] **KSN-032** Mark the Qdrant point `sold` / `removed` when a listing is sold or deleted

**✅ Checkpoint:** A chart of same-animal vs different-animal similarity, and the chosen thresholds written in MEMORY.md with their numbers.

**Self-check**

- If 5 % of different-animal pairs pass, how many wrong matches is that at 2M listings a month?
- Why does the pilot still send every AI approval to a human?


---

## Day 5 · The seller app

**Goal:** A farmer can list an animal from your phone.

**Learn**

- **Flutter widgets and state** — screens as widgets; one state holder per flow
- **Camera + image checks in Dart** — camera package; blur and brightness on a downscaled frame
- **Uploads that survive bad network** — retry with backoff; queue saved to disk
- **Hindi + English** — intl / .arb files; copy table in docs/DESIGN.md §4.6

**Build**

- [ ] **KSN-070** App skeleton, Hindi/English, design tokens; dev login with a test seller
- [ ] **KSN-071** New listing form (docs/DESIGN.md §4.2)
- [ ] **KSN-072** Guided camera, lite: silhouettes, step strip, blur + light checks (on-device YOLO comes later)
- [ ] **KSN-074** Upload queue with retry, lite
- [ ] **KSN-075** Submit, checking and result screens

**✅ Checkpoint:** On your phone: create a listing, take 8 photos and the video, submit, and see “Checking” turn into a result.

**Self-check**

- Why is there no gallery button?
- What does the seller see if the upload URL expired while they were offline?

> **Plan B:** Flutter completely new: build the same flow as a mobile web page today (camera via `<input capture>`), and port to Flutter in week 2.


---

## Day 6 · The reviewer, and real sign-in

**Goal:** A reviewer can approve a listing, and no one can pretend to be someone else.

**Learn**

- **OTP login + JWT** — short access token, refresh token, roles in claims
- **Role-based access** — docs/RULES.md §2–3
- **Small web UI** — React + Vite, or FastAPI templates + HTMX if you want speed

**Build**

- [ ] **KSN-040** Lite: `/auth/otp/request` + `/auth/otp/verify` (dev: code printed in logs), JWT check that sets seller/reviewer instead of trusting headers
- [ ] **KSN-050** Review queue page, oldest first, SLA colours
- [ ] **KSN-051** Case page, lite: photos with similarity, flags, Verify / Retake / Block with reason
- [ ] **KSN-053** Lock a case to one reviewer while it is open

**✅ Checkpoint:** Full loop: phone submits → reviewer approves in the browser → phone shows Verified. A request with a forged `X-Seller-Id` and no token gets 401.

**Self-check**

- Why must sellers never see fraud flags?
- Two reviewers open the same case. What happens now?


---

## Day 7 · Ship the demo

**Goal:** Anyone with the link can watch 5 real animals get verified.

**Learn**

- **One-server deployment** — docker compose on a cloud VM in an India region, HTTPS with Caddy
- **Secrets and logs** — .env on the server, no secrets in git, `docker compose logs`
- **What production adds** — docs/ARCHITECTURE.md §8 — Citus nodes, Triton, KEDA

**Build**

- [ ] **DEPLOY-1** Deploy the stack to one VM (8 vCPU, 32 GB) in an India region with HTTPS
- [ ] **DEPLOY-2** Daily database backup to object storage
- [ ] **KSN-083** Lite: one page or SQL view counting decisions by status per day
- [ ] **DEMO-1** Verify 5 real animals end to end; record a 2-minute demo video
- [ ] **RETRO-1** Retro: update MEMORY.md and TASKS.md, plan week 2

**✅ Checkpoint:** The demo works on your phone over mobile data, away from your home Wi-Fi.

**Self-check**

- Which three things would break first at 100× today's traffic?
- What is the first ticket of week 2, and why that one?

---

## Not this week (on purpose)

| Left out | Why / when |
|---|---|
| Citus multi-node, Triton + TensorRT, KEDA | Single machine is enough for a demo. Weeks 3–4. |
| Training custom models | Needs ~2,000 labelled animals. Zero-shot first. Weeks 2–5. |
| On-device YOLO in the app | Blur and light checks cover the main cases for now. Week 2. |
| Terraform / Kubernetes | Week 4, after the demo proves the flow. |
| KYC provider, Play Integrity, DPDP deletion | Required before public launch, not for a demo. |
| Legal review of state rules | Start the conversation this week; it takes longer than code. |
| Buyer app | Week 3. |
