# RULES — Security, Access & Coding Rules

> **Read this before:** adding an endpoint, a query, a log line, or anything that touches photos or personal data.
> Legend: ✅ built · ⚠️ gap (has a ticket in [TASKS](TASKS.md)) · 🔒 must never change without review

---

## 1. How people sign in

| Who | Method | Where it is checked |
|---|---|---|
| Seller / buyer | **Phone number + OTP** (SMS, WhatsApp fallback) → short-lived JWT (15 min) + refresh token (30 days, bound to device) | API gateway |
| Reviewer / ops | Company SSO (Google Workspace / Okta) + 2FA, office/VPN IP allow-list | API gateway |
| Services | Kubernetes service accounts + IAM roles; no shared passwords | Cluster / cloud IAM |

The gateway validates the JWT and forwards **trusted** headers. Services trust these headers only because they are not reachable from outside the gateway. 🔒

| Header | Set by | Meaning |
|---|---|---|
| `X-Seller-Id` | gateway, from JWT `sub` | the signed-in seller |
| `X-Reviewer-Id` | gateway, only for staff SSO tokens with role `reviewer` | the reviewer |
| `X-App-Version` | app | must be ≥ `KISAN_MIN_APP_VERSION` or **426** |

⚠️ **Today** the services read these headers but the gateway JWT check is not built (KSN-040). Do not expose the services publicly until it is.

## 2. Roles and what each can do

| Action | Seller | Buyer | Reviewer | Ops admin | System |
|---|:-:|:-:|:-:|:-:|:-:|
| Create listing (pilot state only) | ✅ own | – | – | – | – |
| Upload / retake photos | ✅ own, not while `VERIFYING` | – | – | – | – |
| Submit for verification | ✅ own | – | – | – | – |
| See own verification status + retake reasons | ✅ | – | – | – | – |
| See internal flags, scores, evidence | ❌ | ❌ | ✅ | ✅ | – |
| See live listings + photos | ✅ | ✅ | ✅ | ✅ | – |
| See non-live listings of others | ❌ | ❌ | ✅ | ✅ | – |
| Decide a review case | ❌ | ❌ | ✅ | ✅ | – |
| Change `state_rules` / enable a state | ❌ | ❌ | ❌ | ✅ + legal sign-off | – |
| Change thresholds / model versions | ❌ | ❌ | ❌ | ✅ via release | – |
| Write verification results | – | – | – | – | ✅ worker only |

**Why sellers never see fraud flags:** a seller told "same animal found in listing X" learns how to beat the check. Sellers get plain messages; reviewers get the evidence. 🔒

## 3. Row-level rules (whose data you can touch)

1. **Every seller query filters by `seller_id` from the token.** Never from the URL or body. 🔒
   ```python
   animal = await session.get(Animal, (seller.id, animal_id))   # ✅ composite key includes seller
   animal = await session.get(Animal, animal_id)                 # ❌ never
   ```
2. A missing row and another seller's row both return **404**, so IDs cannot be probed. ✅
3. Reviewer routes take `seller_id` in the path because reviewers work across sellers. Only reviewer tokens reach them. ⚠️ (role enforced at gateway — KSN-040)
4. Buyers read only `listings.status = 'LIVE'` through a separate read model. ⚠️ (KSN-060)
5. **Defence in depth (planned):** Postgres row-level security on tenant tables using `current_setting('kisan.seller_id')`, set per transaction. ⚠️ (KSN-043)

## 4. Photos and files

| Rule | Status |
|---|---|
| Upload only via presigned PUT, 15-minute expiry, exact `Content-Type` | ✅ |
| Types: `image/webp`, `image/jpeg`; video `video/mp4` only | ✅ |
| `capture_meta.source` must be `in_app_camera`; gallery refused (**422**) | ✅ |
| Max 48 upload slots per animal (**429** after) | ✅ |
| Bucket is private; buyers get signed GET URLs via CDN | ⚠️ KSN-061 |
| Server verifies the app's capture signature (`capture_meta.sig`) | ⚠️ presence only — KSN-041 |
| Strip GPS/EXIF from photos shown to buyers | ⚠️ KSN-062 |
| Decode in workers only; a file that fails to decode becomes a retake, never a crash | ✅ |

## 5. Personal data (DPDP Act 2023)

| Rule | How |
|---|---|
| Data stays in India | All storage and backups in `ap-south-1` (Mumbai), DR in Hyderabad. 🔒 |
| Collect the minimum | This service stores IDs, state and KYC status only — no names, phone numbers or Aadhaar. 🔒 |
| Consent | Collected by the app at sign-up, per purpose (listing, verification, training). ⚠️ KSN-063 |
| Deletion on request | Delete S3 prefix `sellers/{id}/`, DB rows by `seller_id`, Qdrant points by `seller_id`. ⚠️ KSN-064 |
| Training data | Only from sellers who consented to "help improve verification". ⚠️ KSN-063 |
| Encryption | TLS 1.3 in transit; KMS at rest (RDS, S3, MSK, Qdrant volumes). |
| Audit | Every decision row keeps `evidence`, `reasons`, `model_versions`, reviewer ID. ✅ |
| Logs | No phone numbers, tokens or presigned URLs in logs. Log IDs only. 🔒 |

> Not legal advice. Have counsel confirm consent text, retention periods and state animal-sale rules before launch.

## 6. Error handling — what the user sees

### API errors (built ✅)

| Code | When | Message (seller-facing) |
|---|---|---|
| **401** | Unknown seller ID | "Unknown seller." |
| **403** | Seller's state not enabled | "Verified listings are not available in your state yet. We will notify you when they are." |
| **404** | Animal / upload not found **or not yours** | "Animal not found." |
| **409** | Upload not in S3 yet | "File has not finished uploading." |
| **409** | Submit with missing views | `{"message": "Some photos are missing.", "missing": [...]}` |
| **409** | Upload or submit while verifying / live | "This listing is being verified; wait for the result." |
| **409** | Submit a `BLOCKED` listing | plain message; checked before missing photos (KSN-031) |
| **422** | Gallery photo, wrong file type, bad field | "Please take the photo with the in-app camera." |
| **426** | Old app | "Please update the Kisan app to continue." |
| **429** | Too many uploads for one animal | "Too many uploads for this animal." |

Retakes come back in `reupload[]` with a **reason code** (`blurry`, `too_dark` …); the app shows its own translated text (DESIGN §4.6). ✅ KSN-034

### Pipeline failures

| Failure | What happens | Status |
|---|---|---|
| Kafka down | Events wait in `outbox`; relay retries | ✅ |
| Bad Kafka message (any parse error: bad JSON, not an object, missing keys) | Sent to `verify.requested.dlq`, partition keeps moving | ✅ KSN-038 |
| Temporal down | Trigger crashes, restarts from last committed offset | ✅ |
| Worker crash mid-run | Temporal retries the activity on another worker | ✅ |
| Triton / Qdrant / any analyze, fraud or score activity fails after its retries | `NEEDS_REVIEW` with flag "automatic check failed"; never stuck in `VERIFYING` | ✅ KSN-030 (alert ⚠️ KSN-052; fail fast on config errors ⚠️ KSN-087) |
| Qdrant collection missing | Worker creates it on start | ✅ KSN-086 |
| Corrupt photo | Treated as a failed-quality photo → retake | ✅ |
| Reviewer slow > 4 h | Flag `review SLA breached`, keep waiting | ✅ (alerting ⚠️ KSN-052) |

## 7. Edge cases

| Case | Behaviour | Status |
|---|---|---|
| Seller retakes a photo | Latest upload per view is used | ✅ |
| Seller taps Submit twice | 2nd call **409** | ✅ |
| Same Kafka event delivered twice | Same workflow ID → 2nd start ignored | ✅ |
| Left and right photos swapped | Silently corrected | ✅ |
| Same photo uploaded as two views | Retake the 2nd one | ✅ |
| Video has no animal in any frame | VIDEO counts as missing → retake | ✅ |
| Photos taken > 24 h apart | Flag for review | ✅ |
| Some photos have a time zone in `captured_at`, some don't | Naive times treated as UTC | ✅ |
| Seller KYC not done | Flag for review | ✅ |
| Same animal listed by another seller | Flag for review (sim ≥ 0.92) | ✅ |
| Two reviewers decide the same case | First signal wins in the workflow; both review rows are stored | ⚠️ KSN-053: lock case on open |
| `BLOCKED` listing resubmitted | **409**, final | ✅ KSN-031 |
| Reviewer verifies a listing whose AI check failed | Goes live, but no centroid → not in duplicate search | ⚠️ KSN-088 |
| Old verification row without `code` in `reupload` | API returns `code: "other"` | ✅ |
| Animal sold → still `active` in Qdrant | New owner's listing gets a duplicate flag | ⚠️ KSN-032: set status on sale |
| Presigned URL expired | App requests a new upload slot | ✅ (unused rows cleaned up ⚠️ KSN-033) |
| Seller moves state | Listing keeps the state it was created in | ✅ by design |
| No `state_rules` row for species | Flag for review, never auto-approve | ✅ |

## 8. Rules for anyone (or any AI) writing code here

1. **Read [MEMORY](MEMORY.md) first.** It has decisions you must not undo.
2. **Scope by seller.** Every tenant query uses `(seller_id, id)`. 🔒
3. **Never trust the phone.** Every on-device check is repeated on the server.
4. **Events go through the outbox.** Call `events.add_event()` inside the same transaction. Never call Kafka from a request handler. 🔒
5. **Workflow code is deterministic.** No I/O, clocks, randomness or new imports in `workflow.py`; put it in an activity. Run `pytest tests/test_workflow.py::test_workflow_passes_sandbox_validation`.
6. **Activities are idempotent.** Assume every activity runs twice. **Type-hint every activity parameter** — Temporal decodes inputs by the hint (no hint → `dict`).
7. **All tunable numbers live in `ml/thresholds.py` or `ml/scoring.py`.** No magic numbers in stages.
8. **New stage = `StageResult`.** Give it a `name`, `score` (or `None`), `flags` for humans, `reupload` for sellers (each with a `ReuploadCode`). Add it to `WEIGHTS` only if it should count.
9. **Seller messages are plain, short and say what to do.** "Photo is blurry; hold the phone steady." Not "blur_var < 100".
10. **Tests for every change.** `pytest -q` and `ruff check kisan tests` must pass.
