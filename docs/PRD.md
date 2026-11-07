# PRD — Kisan Verified Animal Listings

> **One line:** A farmer can sell a cow, buffalo, goat, sheep or camel online, and a buyer can trust that the animal in the photos is real, is the animal described, and is legal to sell.

| | |
|---|---|
| **Status** | Pilot build (backend done, app not started) |
| **Pilot** | 1 state: Rajasthan (`RJ`) |
| **Scale target** | 10M users · 2M listings / month · 16M photos / month |
| **Owner** | Product: _you_ · Tech: _you_ |
| **Read next** | [ARCHITECTURE](ARCHITECTURE.md) · [RULES](RULES.md) · [DESIGN](DESIGN.md) · [TASKS](TASKS.md) |

---

## 1. The problem

Animal markets move online, but buyers cannot trust a listing:

- 📸 **Fake or borrowed photos.** Sellers post photos of a better animal, or photos copied from another listing.
- 🐄 **Wrong animal.** A buffalo listed as a cow, or a different breed than claimed.
- 🔀 **Mixed animals.** The side photo shows one animal, the face photo shows another.
- 🔁 **Same animal sold twice.** One animal listed by two sellers, or relisted after sale.
- ⚖️ **Legal risk.** Some species have state rules on sale and transport. The platform must not help break them.

Today a buyer only finds out at the market, after travel. The seller loses trust, the buyer loses money and a day.

## 2. Who uses it

| Person | What they want | What gets in their way |
|---|---|---|
| **Seller (farmer / trader)** | List quickly from a basic Android phone, get a "Verified" badge, sell faster | Poor network, unfamiliar with apps, Hindi-first |
| **Buyer** | See real, verified animals and travel only for real deals | Fake listings, no way to check from far away |
| **Reviewer (our team)** | Clear cases fast with evidence on one screen | Too many cases, unclear AI reasons |
| **Ops / Legal** | Know every decision can be explained and that state rules are followed | Rules differ by state and change |

## 3. What we are building

A **verification step** between "seller uploads" and "listing goes live".

```
 Seller takes guided photos ──► AI checks ──► Decision ──► Listing
                                                │
          VERIFIED ✅  goes live with badge ◄────┤
          REUPLOAD 📷  seller retakes named photos
          NEEDS_REVIEW 👀  a human decides (within 4 h)
          BLOCKED ⛔  not allowed to be sold here
```

### What the AI checks (pilot)

| # | Check | Question it answers | Result if it fails |
|---|---|---|---|
| 1 | Photo quality | Is the photo sharp, bright and big enough? | Retake that photo |
| 2 | Animal present | Is there exactly one animal, close enough? | Retake that photo |
| 3 | Species | Is it the species the seller chose? | Human review |
| 4 | Views | Did the seller give every required angle? | Retake missing / wrong photos |
| 5 | Same animal | Do all photos and the video show one animal? | Human review |
| 6 | Duplicate | Is this animal already listed elsewhere? | Human review |
| 7 | Fraud signals | Same photo used twice? Gallery upload? KYC done? | Retake or review |
| 8 | State rules | Is this sale allowed in this state? Docs present? | Block or review |

### Later (not in pilot)

Breed check · ear-tag number reading (OCR) · vet / ownership documents · age-range consistency.

> **Age:** we never say "AI verified the age". At most: "declared age is consistent with what we see and with the documents."

## 4. User stories

### Seller
- **S1** As a seller, I create a listing with species, breed, sex, age and ear-tag number, so buyers know what I am selling.
- **S2** As a seller, the app tells me which photo to take next and shows a sample, so I get it right the first time.
- **S3** As a seller, the camera tells me *before* I upload if a photo is blurry, dark or has no animal.
- **S4** As a seller, uploads continue after my network drops.
- **S5** As a seller, if a photo is rejected I see **which** photo and **why**, in my language, and retake only that one.
- **S6** As a seller, I get a message when my listing is live.

### Buyer
- **B1** As a buyer, I see a "Verified" badge only on listings that passed.
- **B2** As a buyer, I see all angles and a short walk-around video of the same animal.

### Reviewer
- **R1** As a reviewer, I see the oldest waiting cases first.
- **R2** As a reviewer, I see every photo, every flag and the AI score on one screen.
- **R3** As a reviewer, I approve, ask for retakes, or block, with a reason.
- **R4** As a reviewer, my answers ("same animal: yes/no", "species: cow") are saved to train the AI.

### Ops / Legal
- **O1** As ops, I turn a state on only after its rules are legally reviewed.
- **O2** As ops, every decision stores its evidence and model versions, so it can be explained later.

## 5. Success metrics

### Pilot exit gate (must pass before a 2nd state)

| Metric | Target |
|---|---|
| Precision of AI "VERIFIED" (checked by humans) | **≥ 98 %** |
| Reviewer overturns AI decision | **< 2 %** |
| Upload → decision, p95 | **< 2 min** |
| Manual review time | **< 4 h** |
| Seller finishes photo flow on first try | **≥ 70 %** |

### Product health

- Listings verified per day · Time to first sale · Buyer reports of "animal not as shown" (should fall) · Retake rate per view (shows which instructions confuse people).

## 6. Scope

| In pilot ✅ | Not in pilot ❌ |
|---|---|
| 6 species, bovines first | Breed, OCR, documents, age |
| Rajasthan only | Other states |
| Human confirms every AI approval | Fully automatic approval |
| Android app (Hindi + English) | iOS app |
| Seller + reviewer flows | Payments, chat, delivery |

## 7. Risks

| Risk | What we do |
|---|---|
| AI approves a wrong animal | Pilot: a human confirms every approval. Auto-approve only after the exit gate. |
| Rules are wrong for a state | Rules live in a table, `legally_reviewed=false` until a lawyer signs off; unreviewed = review, never auto-approve. |
| Photos of animals look alike | Walk-around video ties views together; muzzle photo for bovines; humans review low-confidence cases. |
| Rural network | On-device checks work offline; resumable uploads. |
| Personal data | Data stays in India; consent and deletion per DPDP Act 2023. See [RULES](RULES.md). |

## 8. Open questions

- [ ] Which national livestock database can we query for ear-tag numbers, and on what terms?
- [ ] Which KYC provider?
- [ ] Do we show the AI score to buyers, or only the badge?
- [ ] What happens to the badge when an animal is sold and relisted by the new owner?
