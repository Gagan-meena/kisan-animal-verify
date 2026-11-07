# HANDOFF — read this first in a new chat

> Replaced at the end of each session. Long-term facts live in [MEMORY](MEMORY.md); tickets in [TASKS](TASKS.md); the plan in [WEEK1](WEEK1.md).

**Last session:** 2026-11-07 · **Next:** **Day 2 — Events that never get lost** (WEEK1.md)

## How to pair with Gagan

- Start with a 10-minute concept brief, then **hints, not answers**. Gagan writes the code and pastes it for review.
- Work **one step at a time**, numbered, each step ending with a ✅ "you should see …".
- Keep replies **short**. Give exact commands to copy and paste. Point to file and line, and don't rewrite whole files.
- When he's stuck for over 45 min, give the answer, then he types it himself.
- In reviews, flag bugs, RULES §8 breaks (especially `seller_id` scoping) and weak tests (assert the message, not only the status code).
- At the end of a day, update MEMORY and TASKS in the project and send him the files to push.

## His setup

| | |
|---|---|
| Machine | Ubuntu laptop (aspire), repo `~/meeraxu/kisan-verify`, venv `.venv` |
| Python | Project targets **3.12**; the system default is 3.14. Rebuild the venv with `uv venv -p 3.12 .venv` if not done |
| Stack | `docker compose` on the laptop: api :8080/docs, Temporal UI :8233, MinIO console :9001, Qdrant :6333, Kafka :9092, Postgres :5432 (`kisan/kisan`) |
| Bucket | `kisan-animal-images` |
| Config | `.env` uses `localhost` (for pytest); containers use the `x-kisan-env` anchor in `docker-compose.yml` (service names) |
| After code edits | `docker compose up -d --build api` (also rebuild `verify-worker` / `verify-trigger` / `outbox-relay` if changed) |
| Test seller | `a67d7200-ba8b-4028-ab9c-8abdcae2feee` (RJ) · animal `eb9653bf-97dd-4669-bc95-72bde288807f` (DRAFT, 1 FRONT photo) |
| Dataset | `/mnt/data/datasets/SideViewCows2026/kisan_sample/...` (side-view cows) + Kaggle for Days 3–4 |
| Tests | `tests/test_api.py` has helpers `new_seller(client)` → headers, `new_listing(client, h)` → listing JSON; fixture `db` yields a sessionmaker |

## State at handoff

- **Day 1 done:** checkpoint passed; KSN-037 (`GET /v1/listings`) and KSN-031 (409 on `BLOCKED` resubmit) built with tests.
- **Tests:** 40 passed, **2 failed**: `test_review_signal_completes_workflow` and `test_review_sla_escalates_then_waits`. The error is `'dict' object has no attribute 'phase'` in the test's fake `record_decision` (tests/test_workflow.py:46). First check `python --version`: a 3.14 venv is the likely cause. → KSN-035.
- **Git:** the first commit was pending. He was adding `.gitignore` (so `.env` is not committed), removing duplicate root `.md` files (docs live in `docs/`), then pushing to `main`. Branch naming from now on: `ksn-<id>-<short>` or `dayN-ksn-...`.
- **Not answered yet:** the Day 1 self-check questions (`(seller_id, id)` scoping, and why handlers don't send to Kafka directly). Ask him briefly before starting Day 2.

## Day 2 plan (from WEEK1.md)

1. **KSN-035:** get the 2 Temporal tests green (Python version, then activity input types).
2. **Learn:** Kafka topics, partitions, consumer groups and offsets (`trigger.py`); relay and leader lock (`events/relay.py`); workflow vs activity, retries, timers and signals (`workflow.py`, `activities.py`); determinism (RULES §8 rule 5).
3. **KSN-030:** a failed workflow → `NEEDS_REVIEW` with the flag "automatic check failed"; a listing never stays stuck in `VERIFYING`.
4. **KSN-034:** reason codes next to the text in `reupload[]`.
5. **KSN-038 (fits today):** trigger poison pill → DLQ.
6. **Checkpoint:** submit a listing, `docker compose stop verify-worker` mid-run, start it again, and the workflow finishes in the Temporal UI. A broken Kafka message lands in the DLQ topic.
   - Submitting needs all 8 views uploaded (incl. VIDEO), with `KISAN_INFERENCE_BACKEND=fake`.
