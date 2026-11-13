# HANDOFF — read this first in a new chat

> Replaced at the end of each session. Long-term facts live in [MEMORY](MEMORY.md); tickets in [TASKS](TASKS.md); the plan in [WEEK1](WEEK1.md).

**Last session:** 2026-11-13 · **Next:** **Day 3 — Real computer vision, no training** (WEEK1.md)

## How to pair with Gagan

- Start with a 10-minute concept brief, then **hints, not answers**. Gagan writes the code and pastes it for review.
- Work **one step at a time**, numbered, each step ending with a ✅ "you should see …".
- Keep replies **short** (he prefers ~30 words, plan first, no long explanations). Give exact commands to copy and paste. Point to file and line, and don't rewrite whole files.
- When he's stuck for over 45 min, give the answer, then he types it himself. If he says "I don't know" twice, explain briefly and move on.
- In reviews, flag bugs, RULES §8 breaks (especially `seller_id` scoping) and weak tests (assert the message / code, not only the status).
- He sometimes tidies unrelated code (Pylance warnings) mid-ticket and breaks things (e.g. `Mapped[dict[str, Any]]`). Remind: one change at a time, cleanups in their own commit.
- He prefers to **commit at the end of the day**; one branch + PR per ticket, merged in order.
- At the end of a day, update MEMORY and TASKS (and HANDOFF) in the project.

## His setup

| | |
|---|---|
| Machine | Ubuntu laptop (aspire), repo `~/meeraxu/kisan-verify`, venv `.venv` (**Python 3.12.15** ✅) |
| Stack | `docker compose` on the laptop: api :8080/docs, Temporal UI :8233, MinIO console :9001, Qdrant :6333, Kafka :9092 (`apache/kafka:3.7.0`, tools in `/opt/kafka/bin/`), Postgres :5432 (`kisan/kisan`) |
| Bucket | `kisan-animal-images` |
| Config | `.env` uses `localhost` (for pytest) and is **not** passed to containers; containers use the `x-kisan-env` anchor (service names) |
| After code edits | `docker compose up -d --build api verify-worker verify-trigger outbox-relay` (only the ones changed) |
| Test seller | `a67d7200-ba8b-4028-ab9c-8abdcae2feee` (RJ) · animal `eb9653bf-97dd-4669-bc95-72bde288807f` — now **VERIFIED / LIVE**, indexed in Qdrant (1 point) |
| Shell vars | `$BASE` (http://localhost:8080), `$SID`, `$AID`; he has an upload loop for 7 views (POST media → PUT → complete) |
| Dataset | `/mnt/data/datasets/SideViewCows2026/kisan_sample/barn/images/128_frame/` — 10 side-view frames of one Holstein cow (also `192`), copied as LEFT…TAG.jpg + `VIDEO.mp4` (ffmpeg from frames). Same side only, no FACE/MUZZLE. Kaggle set for Day 3–4 still to fetch |
| Tests | 49 pass. `tests/test_api.py` helpers `new_seller(client)` → headers, `new_listing(client, h)`; fixture `db` yields a sessionmaker. `tests/test_trigger.py` is new |

## State at handoff

- **Day 2 done.** KSN-035, KSN-038 merged to `main`. KSN-030, KSN-034, KSN-086 built, 49 tests pass, ruff clean — **commit + PRs pending** (he was doing it at the end of the session, stacked branches `ksn-030-…` → `ksn-034-…` → `ksn-086-…`). Check `git log origin/main` first.
- **Checkpoint passed:** stop worker → submit → start → AI decision → review → Completed + indexed. `[1]`, `null`, `"x"` landed in `verify.requested.dlq`; trigger stayed up.
- **Found at the checkpoint:** Qdrant collection never created → fixed (KSN-086). Retrying a 404 10× is slow → KSN-087.
- **Not answered yet:** Day 2 self-check — (1) the relay sends an event twice: what stops a second verification? (he saw it: same workflow ID + `REJECT_DUPLICATE` → `WorkflowAlreadyStartedError`, offset still committed); (2) why can't `workflow.py` call `datetime.now()` or the DB? Ask (2) briefly before Day 3.
- Unconfirmed: he never pasted the in-container check that the worker uses `fake` (`.env` only). The run behaved like `fake`.

## Day 3 plan (from WEEK1.md)

1. **Learn:** detection (boxes, confidence, NMS, letterboxing — `kisan/ml/yolo.py`), CLIP zero-shot, embeddings + cosine (`ml/stages/identity.py`), why crop before embedding (`ml/stages/detect.py`).
2. **KSN-027:** zero-shot `LocalBackend` — YOLO11 COCO (`cow` class 19; COCO has no buffalo/camel/goat → which stage catches it?), CLIP for species + views, DINOv2-small or MegaDescriptor embeddings. It must expose `dim` for `ensure_collection`. CPU laptop → start with YOLO11n + DINOv2-small (Plan B).
3. **KSN-028:** CLI `python -m kisan.tools.try_photos <folder>` printing every stage result.
4. **Checkpoint:** run the CLI on each animal folder; one animal's photos pass identity; swap in a photo of another animal (`128` ↔ `192`) and see it flagged.
   - His frames are all one side → expect `views` to fail (that's fine; the identity check is the point today). Changing the Qdrant `dim` (256 → DINOv2 384 / MegaDescriptor 1536) needs the collection dropped and recreated locally.
