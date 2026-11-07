# DESIGN — Seller App & Review Console

> **Read this before:** building any screen. Every screen lists the API it calls, its states, and its exact words.
> Two front-ends: **Seller app** (Flutter, Android first) and **Review console** (React web, desktop).

---

## 1. Who we design for

| | Seller | Reviewer |
|---|---|---|
| Device | Android 8+, 2–3 GB RAM, 360 dp wide, cracked screen, bright sun | Laptop, 1440 px, keyboard |
| Network | 2G / patchy 4G, often offline in the field | Office broadband |
| Language | Hindi first, English second | English |
| Reading | May read slowly; icons + short words help | Fast; wants density |
| Goal | "Get my animal listed and sold" | "Clear this case correctly in under 60 s" |

**Three promises to the seller**

1. 📷 **You will know a photo is bad before you upload it.**
2. 📶 **Nothing you upload is lost when the network drops.**
3. 🗣️ **If we need a retake, we name the photo and say why, in your language.**

## 2. Design tokens

| Token | Value | Use |
|---|---|---|
| `color.primary` | `#2F6B3A` field green | buttons, active step |
| `color.primary-soft` | `#E1ECDF` | selected tiles |
| `color.ok` | `#2F7A45` | Verified, check passed |
| `color.warn` | `#A26A00` | In review, needs attention |
| `color.bad` | `#B23A2E` | Retake, blocked |
| `color.bg` / `surface` / `fg` | `#F5F6F1` / `#FFFFFF` / `#1D241C` | page / card / text |
| `font.body` | Noto Sans + **Noto Sans Devanagari** | all text (Hindi must not fall back) |
| `font.size` | 16 / 18 / 22 / 28 sp | body / button / title / screen heading |
| `touch.min` | **56 dp** (larger than the 48 dp norm: gloves, wet hands) | every tap target |
| `radius` | 12 dp cards, 28 dp buttons | |

Rules: never color alone — every status has **icon + color + word**. Support text scale 1.3× without clipping. Dark mode: later.

## 3. Seller app — flow

```
 Login (OTP) ─► My listings ─► New listing ─► Photo steps (8) ─► Upload ─► Submit
                    ▲                                                        │
                    │      ┌──────────── Checking (≤ 2 min) ◄────────────────┘
                    │      ▼
                    ├── ✅ Verified ── share listing
                    ├── 📷 Retake ──── only the named photos ──► Submit again
                    ├── 👀 In review ─ "within 4 hours" + push when done
                    └── ⛔ Blocked ─── reason
```

## 4. Seller app — screens

### 4.1 My listings
- List of cards: animal photo (FRONT), species + breed, price, **status chip**.
- Status chips map from `listings.status`:

| Status | Chip | Hindi |
|---|---|---|
| `DRAFT` | ⚪ Draft | अधूरी |
| `VERIFYING` | 🟡 Checking | जाँच जारी |
| `NEEDS_REUPLOAD` | 🔴 Retake photos | फ़ोटो दोबारा लें |
| `LIVE` | 🟢 Verified · Live | सत्यापित |
| `BLOCKED` | ⛔ Not allowed | अनुमति नहीं |
| `SOLD` | ⚫ Sold | बिक गया |

- Big **+ Sell an animal** button, bottom, full width.
- Empty state: drawing of a cow + "List your first animal in 5 minutes".

### 4.2 New listing — `POST /v1/listings`
One question per screen, big tiles, progress dots.

| Step | Control | Validation |
|---|---|---|
| Species | 6 picture tiles: cow, buffalo, goat, sheep, camel, horse | required |
| Breed | searchable list + "Don't know" | optional, ≤ 48 chars |
| Sex | 2 tiles | required |
| Age | years + months wheels | 0–40 years |
| Ear tag | 12-digit number pad, grouped `1234 5678 9012` | exactly 12 digits, optional for goat/sheep |
| Price | ₹ number pad, shows "₹65,000" | 1 – 1,00,00,000 |
| Title | prefilled "Gir cow, 4 years" | 3–120 chars |

Response gives `required_views` → builds the photo checklist. **403** → full-screen "Not in your state yet" with "Notify me".

### 4.3 Photo steps — the most important screen

```
 ┌───────────────────────────────┐
 │ ● ● ● ○ ○ ○ ○ ○   Step 4 of 8 │  ← progress, tap to jump back
 │  बाईं ओर की फ़ोटो             │
 │  Left side photo              │
 │ ┌───────────────────────────┐ │
 │ │                           │ │
 │ │   [ live camera ]         │ │  ← faint silhouette of the species,
 │ │      cow outline          │ │    left-facing, as a framing guide
 │ │                           │ │
 │ └───────────────────────────┘ │
 │  ✅ Animal   ✅ Sharp          │  ← live checks, update ~5×/s
 │  ⏳ Light    ✅ Left side      │
 │                               │
 │        ( ◉  shutter )         │  ← disabled until all 4 green
 │  See example ›                │
 └───────────────────────────────┘
```

**Order of steps** (cow/buffalo; others skip what `required_views` omits):
FRONT → LEFT → RIGHT → REAR → FACE → MUZZLE → TAG → VIDEO

| View | Instruction (EN) | Hindi | Silhouette |
|---|---|---|---|
| FRONT | Stand in front, whole animal in frame | सामने से पूरा पशु | front |
| LEFT | Stand on the animal's left side | पशु की बाईं ओर से | side, head left |
| RIGHT | Stand on the animal's right side | पशु की दाईं ओर से | side, head right |
| REAR | Stand behind the animal | पीछे से | rear |
| FACE | Close-up of the face | चेहरे की नज़दीकी फ़ोटो | head |
| MUZZLE | Close-up of the nose | नाक की नज़दीकी फ़ोटो | muzzle box |
| TAG | Close-up of the ear tag number | कान के टैग का नंबर | tag box |
| VIDEO | Walk slowly around the animal, 5 seconds | पशु के चारों ओर धीरे चलें, 5 सेकंड | circle arrow |

**Live checks (on-device, rule ①)** — same thresholds as server `ml/thresholds.py`:

| Chip | Passes when | Hint when failing |
|---|---|---|
| Animal | YOLO11n sees 1 animal, box ≥ 10 % of frame (full-body views) | "Move closer" / "Only one animal" |
| Sharp | Laplacian variance ≥ 100 at 1024 px | "Hold the phone steady" |
| Light | mean brightness 40–220 | "Too dark — move to daylight" / "Sun behind the animal" |
| View | view model agrees ≥ 0.70 | "This looks like the face — go to the left side" |

After the shutter: show the photo full screen with **Use photo** / **Retake**. Save as WebP, long side 1600 px, quality 80.

**Capture metadata** sent with each upload (`capture_meta`):
```json
{ "source": "in_app_camera", "captured_at": "2026-10-09T08:00:00+05:30",
  "app_version": "1.2.0", "device_id": "<install id>",
  "on_device_check": {"animal": true, "sharp": 143.2, "light": 121, "view": "LEFT", "model": "y11n-3"},
  "sig": "<device-key signature of the above>" }
```
There is **no gallery button**. The server refuses gallery uploads (422).

### 4.4 Upload queue
- Starts as soon as a photo is accepted, in the background.
- Per item: `POST …/media` → PUT to `upload_url` (resumable, retries with backoff) → `POST …/complete`.
- Row per photo: thumbnail, view name, progress ring, ✅ / ⏳ / ⚠️.
- Offline banner: "No network. Photos are saved and will upload automatically."
- If `upload_url` expired (15 min): request a new slot silently.

### 4.5 Submit — `POST /v1/animals/{id}/submit`
- Button enabled when every required view shows ✅.
- **409 missing** → jump to the first missing step.
- Then "Checking your photos" screen: animated check marks for Quality → Animal → Views → Same animal. Poll `GET …/verification` every 10 s (push replaces polling later).

### 4.6 Results — `GET /v1/animals/{id}/verification`

| `status` | Screen |
|---|---|
| `PENDING` | Checking screen (above) |
| `VERIFIED` | Big green badge, confetti once, "Your animal is verified and the listing is live." + **Share on WhatsApp** |
| `REUPLOAD` | Red header "2 photos need to be taken again" + list from `reupload[]`: thumbnail, view, reason, **Retake** → opens that step only |
| `NEEDS_REVIEW` | Amber: "Our team is checking your listing. You will get a message when it is done." Shows "usually within 4 hours" |
| `BLOCKED` | Grey ⛔, `message` (contains the reason), link to help |

> ⚠️ Today the server returns English `reason` text. The app must map reasons through **reason codes** once KSN-034 ships. Until then show the server text under a translated generic line.

**Seller copy (EN → HI)**

| Key | English | Hindi |
|---|---|---|
| `blurry` | Photo is blurry. Hold the phone steady. | फ़ोटो धुंधली है। फ़ोन स्थिर रखें। |
| `too_dark` | Too dark. Move to daylight. | बहुत अंधेरा है। रोशनी में जाएँ। |
| `too_far` | Animal is too far. Move closer. | पशु बहुत दूर है। पास जाएँ। |
| `many_animals` | Only one animal in the photo. | फ़ोटो में केवल एक पशु रखें। |
| `no_animal` | No animal found in this photo. | इस फ़ोटो में पशु नहीं दिखा। |
| `wrong_view` | This looks like the {seen} photo. Take the {view} photo. | यह {seen} की फ़ोटो लगती है। {view} की फ़ोटो लें। |
| `missing` | {view} photo is missing. | {view} की फ़ोटो नहीं है। |
| `same_photo` | Same photo as another view. Take a new one. | यह दूसरी फ़ोटो जैसी ही है। नई फ़ोटो लें। |
| `verified` | Your animal is verified. | आपका पशु सत्यापित हो गया है। |
| `in_review` | Our team is checking your listing. | हमारी टीम आपकी लिस्टिंग देख रही है। |

### 4.7 Buyer listing card (for later, KSN-060)
FRONT photo · ✅ **Verified** chip (only when `LIVE`) · species, breed, age, price, district · swipe gallery in view order · walk-around video · "Report this listing".

## 5. Review console

### 5.1 Queue — `GET /v1/review/queue`

| Column | Notes |
|---|---|
| Waiting | `waiting_since` as "2 h 10 m"; **amber > 3 h, red > 4 h** |
| Score | number + bar |
| Flags | first flag + "+2 more" |
| Species / state | |

Oldest first. `J/K` move, `Enter` opens.

### 5.2 Case — `GET /v1/review/{seller_id}/{animal_id}`

```
 ┌ Flags ──────────────────────────────────────────────────────────────┐
 │ ⚠ RIGHT photo may show a different animal   ⚠ seller KYC not done   │
 ├ Photos (from evidence.stages) ──────────────────┬ Checks ───────────┤
 │ FRONT 0.82  LEFT 0.79  [RIGHT 0.41]  REAR 0.77  │ Species cow 97 %  │
 │ FACE 0.84   MUZZLE     TAG          VIDEO ▶     │ Views 8/8         │
 │ outlier = red outline, sim = best match         │ Score 78.4        │
 ├ Duplicate hit ─────────────────────────────────┤ Rules RJ ⚠ review │
 │ this animal ◄──── side by side ────► listing l2 │ Models y11m-7 …   │
 ├─────────────────────────────────────────────────┴───────────────────┤
 │ Same animal? (•) yes ( ) no   Species right? (•) yes ( ) no         │
 │ [V] Verify    [R] Ask retake (reason)    [B] Block (reason)         │
 └─────────────────────────────────────────────────────────────────────┘
```

- `POST /v1/review/{seller_id}/{animal_id}` with `decision`, `reason`, `labels`.
- Reason **required** for R and B; it is shown to the seller.
- Labels are training data: always ask "Same animal?" and "Species right?".
- After submit: next case opens automatically.

## 6. Accessibility & performance checklist

- [ ] Every tap target ≥ 56 dp; every icon has a TalkBack label
- [ ] Hindi renders in Noto Sans Devanagari, never boxes
- [ ] Works at 360 dp and text scale 1.3×
- [ ] App start < 3 s on a 2 GB phone; camera check < 150 ms per frame
- [ ] On-device model ≤ 5 MB
- [ ] All photos survive app kill + reboot until uploaded
- [ ] Review console fully usable by keyboard
