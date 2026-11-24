# Investment Radar — Full Beta Development Plan

**Document status:** Canonical · updated 2026-07-20 (evening)  
**Product name:** Beta (personalized agent layer)  
**Authority:** This file is the implementation source of truth. Older specs (`SCENARIO3_MULTI_AGENT.md`, `CURSOR_IMPLEMENTATION_SPEC.md`) supply schemas/prompts; **on conflict, this file wins**.  
**Maps:** V1 flow → `agent_io_map_v1.html` · Full 11-agent vision → `agent_io_map.html`  
**Live URL:** https://investment-radar-usa.web.app (build stamp on header, e.g. `v0720u`)

---

## 0. Product decisions (do not reopen casually)

| Topic | Decision |
|-------|----------|
| Vision | Full Scenario 3 (personalized brief + actions + learning + later Events/Deep Dive) |
| Delivery | **Same USA dashboard URL** — not a second site / extra link |
| Rollout | **V1 core first** → **Full (V2+) phase by phase** |
| Pipeline | Existing scorer / decision_engine **unchanged** |
| Orchestrator | **Included** — thinking editor (ranked plan + conflicts + memory). Does not recompute TA scores |
| Learning | Decision Logger + Outcome Tracker → feed Orchestrator next night |
| Language | **English only** for all UI and agent user-facing text |
| Ultra-slim merge | Rejected as primary path |
| Ship all 11 agents on day 1 | Rejected |

### How “beta” appears to the user

- Open existing USA Hosting link (`frontend/usa`).
- New blocks labeled **Beta** (Daily Brief, action pills, Tracker).
- Existing tabs remain (Candidates, My Portfolio, Heatmap, ETF, …).
- Kill switches: GitHub `RUN_AGENTS=false` and/or UI hide.

### Language rules

| Surface | Language |
|---------|----------|
| Labels, pills, buttons, empty states | English |
| Brief, summaries, notes, reasons | English |
| Canonical pills | `Exit now` · `Review` · `Hold` · `Enter` · `Wait` · `Watch` |
| Priority | `A` (do today) · `B` (later) · `Watch` (not first ticket) |
| Horizon | `Trade` (~weeks) · `Swing` (multi-week) · `Position` (longer / ETF) |
| Fit badges | `Fits` · `Overlap` · `Doesn't fit` |
| Banner | `Beta · Daily Brief` | 
| Prompts | Must include: *Respond in clear English only. Do not mix languages.* |

Clarity bar: **what to do** · **how long** · **why** · **how much** — no identical Enter € clones; no duplicate sections saying the same thing.

---

## 1. Architecture overview

```
LAYER 0  Code pipeline (unchanged) → daily_candidates, macro_regime, sector_status, …
LAYER 1  Shared agents → macro_signal, sector_rotation, earnings_preview
LAYER 2  My Portfolio agents → exit (+ later avg-down, risk)
LAYER 3  Candidates agents → fit, timing, sizing
LAYER 4  Orchestrator → daily_brief
LAYER 5  Learning → decision_log + outcomes → next Orchestrator
LAYER 6  UI (same URL) → Beta brief, pills, personalized candidates, tracker
LAYER 7  Full add-ons → Events, Price Alert, Deep Dive debate, rich Risk/AvgDown
```

**Nightly order (V1 and Full share the same spine):**

```
USA pipeline
  → Macro → Sector → Earnings
  → Exit → Candidates (Fit → Timing → Sizing)
  → Orchestrator → daily_brief
  → Decision Logger → Outcome Tracker
  → [Full] AvgDown · Risk weekly · (intraday: Price Alert · Events)
```

**Learning loop:** brief actions logged → after window, outcome written → next brief reads last N outcomes.

---

## 2. Release trains

| Train | Name | Goal | Exit criteria to next |
|-------|------|------|------------------------|
| **V1** | Core beta | One morning plan + trust loop | Brief stable daily; pills live; logs writing; first outcomes appearing |
| **Full** | Complete Scenario 3 | All original beta capabilities | AvgDown, Risk, Alerts, Events, Deep Dive on-demand |
| **Polish** | Optional | Split files to match 11-agent map 1:1 | Only if maintainability needs it |

---

# PART A — V1 CORE (build first)

## Phase 0 — Infrastructure

**Goal:** Agents can run after pipeline without breaking scoring.

| # | Task | Deliverable | Done? |
|---|------|-------------|-------|
| 0.1 | Firestore rules | `agents/{document=**}`, `decision_log/{id}` read public, write false | [x] |
| 0.2 | Python deps | `anthropic` in `requirements.txt` | [x] |
| 0.3 | Package skeleton | `src/agents/`, `src/tracking/`, `run_v1.py` stubs | [x] |
| 0.4 | GHA step | After USA daily: `python -m src.agents.run_v1`, `continue-on-error` | [x] |
| 0.5 | Secrets | GitHub: `ANTHROPIC_API_KEY`, `RADAR_USER_ID` | [x] user |
| 0.6 | Deploy rules | `firebase deploy --only firestore:rules` | [x] user |
| 0.7 | Optional gate | Repo var `RUN_AGENTS=false` until Phase 1 useful | [ ] optional |

**Acceptance:** Manual/CI run of `run_v1` writes `agents/_runner_heartbeat` without failing the pipeline job hard.

---

## Phase 1 — Shared agents

**Goal:** Macro / sector / earnings context in English for tags and later Orchestrator.

| # | Component | Output | Model | UI |
|---|-----------|--------|-------|-----|
| 1.1 | Macro Agent | `agents/macro_signal` | Code regime + Haiku summary | Macro badge on brief | [x] |
| 1.2 | Sector Agent | `agents/sector_rotation` | Code status + headlines + Haiku | `Sector watch` tag | [x] |
| 1.3 | Earnings | `agents/earnings_preview/...` | Code + light Haiku | What's next + News tab | [x] |

**Macro logic (code):** map `macro_regime` + SPY vs EMA + VIX → `bullish` / `neutral` / `cautious`. Headlines are context only (do not override regime math).

**Sector logic (code):** use existing `sector_status`; classify strengthening / weakening / neutral; optional ETF headlines for summary.

**Earnings logic:** `days_to_earnings ≤ 14`; risk from days + historical move size.

**Acceptance:** Docs exist in Firestore after nightly; tags readable on My Portfolio / Candidates.

---

## Phase 2 — Exit + personalized Candidates

**Goal:** Actionable holdings + portfolio-aware candidate list.

| # | Component | Output | Notes |
|---|-----------|--------|-------|
| 2.1 | Exit Agent | Per holding: `exit` / `review` / `ok` + English note | Code decides flag; Haiku writes note | [x] |
| 2.2 | My Portfolio UI | Dot + pill + detail action banner | Copy: Exit now / Review / Hold | [x] |
| 2.3 | Portfolio Fit | `agents/candidate_fit/by_ticker/{ticker}` | Sector cap ~33%, overlap | [x] |
| 2.4 | Entry Timing | `agents/entry_timing/by_ticker/{ticker}` | Near support → enter_now; else wait + target | [x] |
| 2.5 | Position Sizing | `agents/position_sizing/by_ticker/{ticker}` | Pure math from budget config | [x] |
| 2.6 | Candidates UI | Guidance: Priority · horizon · € · thesis under pills; hide no_fit | English only | [x] |
| 2.7 | Guidance demotion | Max 1 Priority A enter; same-theme clones → Watch | Orchestrator + client fallback | [x] |

**Candidates runner:** one process, three steps in order (Fit → Timing → Sizing). Prefer code; Haiku only for short `reason` when useful.

**Acceptance:** User can see what to do on holdings and which candidates fit without reading the whole table.

---

## Phase 3 — Orchestrator + learning *(critical)*

**Goal:** One plan + measurable trust. This is the product heart.

| # | Component | Output | Model |
|---|-----------|--------|-------|
| 3.1 | Orchestrator | `agents/daily_brief` | **Sonnet** | [x] |
| 3.2 | Brief UI | Do today cards + market why + Not today / Holdings OK | Beta · Daily Brief | [x] |
| 3.3 | Decision Logger | `decision_log/{id}` | Code | [x] |
| 3.4 | Outcome Tracker | Update log with outcome | Code + yfinance | [x] |
| 3.5 | Tracker UI | Hit rate + table | English | [x] |
| 3.6 | Memory inject | Last N outcomes into Orchestrator | Prompt context | [x] |

### Orchestrator must

- Rank: exit > review > Priority A enter > Priority B wait > Watch  
- Cap identical enters (max 1 Priority A; demote same-sector clones)  
- Assign horizon: Trade / Swing / Position  
- Write clear English plan (`do_today`, `market_why`, `not_today`)  
- Optionally one lesson from past outcomes  

### Orchestrator must not

- Recompute technical scores  
- Invent prices  
- Ignore pipeline / agent inputs  
- Spam six identical “Enter €100” rows  

### Outcome windows (start here; tune later)

| Decision | Window | Prefer |
|----------|--------|--------|
| Exit | 7–14d | vs hold counterfactual |
| Enter now | 14–30d | raw + **alpha vs SPY** |
| Wait | 30d or target hit | opportunity cost |

**Acceptance:** Every trading morning has a brief (or explicit placeholder); every exit/enter/wait in brief is logged; after windows, outcomes fill Tracker.

---

## Phase 4 — V1 harden + beta label

| # | Task | Done? |
|---|------|-------|
| 4.1 | Soft-fail already in GHA; ensure UI placeholder if no brief | [x] |
| 4.2 | Per-agent duration logging (`agents/_run_log`, heartbeat steps) | [x] |
| 4.3 | Beta badge + note: learning needs 14+ days of outcomes | [x] |
| 4.4 | Cost sanity check (~$2.5–4/mo typical single user) | [x] documented |

**V1 agent core done when:** checklist in §6 green for V1 rows.

---

## Phase 4.5 — UX clarity sprint *(shipped 2026-07-20)*

Not in the original V1 agent list — product feedback after first live brief. Same URL.

| # | Task | Done? |
|---|------|-------|
| 4.5.1 | Guidance language: Priority A/B/Watch + Trade/Swing/Position | [x] |
| 4.5.2 | Candidates: thesis under Guidance; no duplicate Watch pills; no Thesis column spam | [x] |
| 4.5.3 | Detail card: one Decision + Thesis + You’re wrong if + Scan decision | [x] |
| 4.5.4 | Daily Brief: Do today only (removed duplicate “Needs attention”) | [x] |
| 4.5.5 | My Portfolio: action-first layout; Decision Tracker collapsed | [x] |
| 4.5.6 | ETF Scan: monthly DCA strip (Buy / Wait limit / Skip) | [x] |
| 4.5.7 | Portfolio “What's next”: earnings plain English + news tone in detail | [x] |
| 4.5.8 | **News tab**: feed with publish time + Positive/Negative/Neutral | [x] |
| 4.5.9 | `deep_dive?levels_only=1`: levels + news without Claude | [x] |
| 4.5.10 | Google auth (GIS + credential) — still verify per-browser if flaky | [~] mostly; confirm live |

**Mocks (design only, not product code):** `ui_mockup_guidance_v2.html`, `ui_mockup_buy_thesis.html`, `ui_mockup_all_views.html`

---

# PART B — FULL VERSION (after V1)

Build only after V1 exit criteria. Same URL, still English, still Orchestrator-centered.

## Phase 5 — Averaging down

| Task | Detail | Done? |
|------|--------|-------|
| 5.1 | Code rules: score > 40, near support, sector not weakening, macro not cautious | [x] |
| 5.2 | Write `agents/avg_down/by_item/{radar_item_id}` | [x] |
| 5.3 | My Portfolio detail: “Average down?” section — checks N/4 + note | [x] |

**Acceptance:** Only shows for holdings with material drawdown (P&L < −10%).

---

## Phase 6 — Risk summary (portfolio-level)

| Task | Detail | Done? |
|------|--------|-------|
| 6.1 | Daily: positions, avg score, warnings, sector concentration → `agents/portfolio_summary` | [x] |
| 6.2 | Weekly: Sonnet summary (Mon or stale >6d) | [x] |
| 6.3 | UI panel on My Portfolio under Daily Brief | [x] |

Note: Does not replace Orchestrator / Do today — adds book-level context.

---

## Phase 7 — Price Alert (code monitor)

| Task | Detail |
|------|--------|
| 7.1 | `src/monitors/price_alert.py` — poll watching positions with `entry_target` |
| 7.2 | Schedule: market hours (separate GHA or Cloud Scheduler), ~15 min |
| 7.3 | Write `alerts/{ticker}_{date}`; notify when within ~1% of target |
| 7.4 | **No LLM** |

**Acceptance:** Alert fires once per ticker per day max.

---

## Phase 8 — Events Agent (intraday)

| Task | Detail | Status |
|------|--------|--------|
| 8.0 | **News tab (lighter precursor)** — portfolio + candidates headlines, tone, publish time | [x] shipped Phase 4.5 |
| 8.1 | RSS / news fetch for radar tickers + held sectors (scheduled) | [ ] |
| 8.2 | Keyword pre-filter (code) — no LLM if no match | [ ] |
| 8.3 | Haiku materiality check vs thesis → `agents/events/{id}` if material | [ ] |
| 8.4 | In-app alert card (+ push later if desired) | [ ] |
| 8.5 | Schedule: ~30 min during US market hours | [ ] |

**Acceptance:** Noise filtered; only thesis-relevant events surface. News tab ≠ full Events Agent.

---

## Phase 9 — Deep Dive debate (on-demand)

| Task | Detail |
|------|--------|
| 9.1 | Extend existing Deep Dive Cloud Function (or sibling) |
| 9.2 | Bull vs Bear short debate using thesis + exit_condition + score context |
| 9.3 | Trigger: user opens Deep Dive / Review — **not** nightly for all tickers |
| 9.4 | Optional: inject recent decision_log for that ticker |

Inspired by TradingAgents debate pattern; **not** a nightly LangGraph firm for 521 names.

**Acceptance:** On-demand only; English; bounded cost per click.

---

## Phase 10 — Full alignment / polish (optional)

| Task | Detail |
|------|--------|
| 10.1 | Align file names 1:1 with `agent_io_map.html` if desired |
| 10.2 | Tune outcome windows by decision type from real Tracker data |
| 10.3 | Orchestrator weight hints from hit rates (learned preferences) |
| 10.4 | Remove Beta badge only when you trust the loop |

---

## 3. Target file map

### V1

```
src/agents/
  __init__.py
  client.py                 # Firebase/Anthropic helpers, ENGLISH_OUTPUT_RULE
  macro_agent.py
  sector_agent.py
  earnings_preview.py
  exit_signal_agent.py
  portfolio_fit.py
  entry_timing.py
  position_sizing.py
  orchestrator_agent.py
  run_v1.py                 # nightly orchestration
src/tracking/
  decision_logger.py
  outcome_tracker.py
frontend/usa/index.html     # Beta brief, pills, fit/timing/€, tracker
firestore.rules             # agents/**, decision_log
.github/workflows/pipeline.yml
```

### Full add

```
src/agents/avg_down_agent.py
src/agents/risk_summary_agent.py
src/agents/events_agent.py
src/monitors/price_alert.py
functions/                  # Deep Dive debate extension
.github/workflows/intraday.yml   # or Cloud Scheduler equivalent
```

---

## 4. Firestore outputs (summary)

| Path | Phase | Purpose |
|------|-------|---------|
| `agents/macro_signal` | 1 | Macro signal + English summary |
| `agents/sector_rotation` | 1 | Sector map + summary |
| `agents/earnings_preview/{ticker}` | 1 | Earnings risk note |
| `agents/candidate_fit/{ticker}` | 2 | Fit |
| `agents/entry_timing/{ticker}` | 2 | Timing + target |
| `agents/position_sizing/{ticker}` | 2 | Suggested € |
| `agents/daily_brief` | 3 | Morning plan |
| `agents/portfolio_summary` | 6 | Risk panel |
| `agents/events/{id}` | 8 | Material events |
| `decision_log/{id}` | 3 | Learning fuel |
| `alerts/{ticker}_{date}` | 7 | Price alerts |

Schemas: see `SCENARIO3_MULTI_AGENT.md` / `CURSOR_IMPLEMENTATION_SPEC.md` (English field values in production).

---

## 5. Cost guide (single user)

| Scope | Typical / month |
|-------|-----------------|
| V1 (Haiku agents + Sonnet Orchestrator) | ~$2.5–4 |
| Tight (minimal candidate LLM) | ~$1.5–2.5 |
| Full + Events + occasional Deep Dive | ~$4–8 |

Main cost driver: Orchestrator (Sonnet) and per-candidate LLM spam — keep sizing/timing as code.

---

## 6. Success criteria

### V1

- [x] Daily `daily_brief` (or clear placeholder) — code + UI
- [x] Holdings show Exit now / Review / Hold — code + UI
- [x] Candidates show guidance · priority · horizon · size · sensible sort — code + UI
- [x] Brief actions land in `decision_log` — code
- [x] Outcomes begin after windows — code (fills over time)
- [~] User can act from brief without digging raw scores — **UX shipped; keep validating live mornings**

### UX clarity (Phase 4.5)

- [x] No identical Enter € wall
- [x] Do today = single action list (no duplicate panels)
- [x] ETF monthly opportunity strip
- [x] News tab with when + tone

### Full

- [x] Avg-down section for underwater names
- [x] Portfolio risk summary (daily/weekly)
- [ ] Price alerts for watching targets
- [ ] Material events agent (scheduled; beyond News tab)
- [ ] On-demand Deep Dive debate
- [ ] Tracker used to tune Orchestrator / rules

**Accuracy promise:** V1 does not claim alpha. It claims clarity + measurement. Accuracy improves via Tracker → memory → rule/weight updates.

---

## 7. Explicit non-goals

- Replacing the deterministic TA pipeline with LLM scoring  
- Nightly TradingAgents-style multi-agent debate on the full universe  
- Turkish (or mixed) user-facing copy  
- Second beta hosting URL in V1/Full  
- Naïve “price up = correct” as the only outcome metric  

---

## 8. Current progress snapshot *(2026-07-20 late)*

### Done

| Area | Status |
|------|--------|
| Phase 0–4 V1 agents + learning loop | **Done** |
| Phase 4.5 UX clarity sprint | **Done** |
| **Phase 5 AvgDown** | **Done** (`avg_down` agent + holding detail UI) |
| **Phase 6 Risk summary** | **Done** (`portfolio_summary` + My Portfolio panel) |
| Hosting | Live `investment-radar-usa.web.app` |

### Remaining (Full)

| Phase | What |
|-------|------|
| **7** | Price alerts (watching + entry target) |
| **8** | Events Agent (thesis-material, scheduled) |
| **9** | Deep Dive bull/bear debate on-demand |
| **10** | Polish / learned weights / remove Beta badge |

### Suggested next

1. Run `python3 -m src.agents.run_v1` so risk + avg_down docs fill Firestore.  
2. **Phase 7 Price Alert** if you want “near target” pings.  
3. Or pause and use Do today + Risk for a week.

---

## 9. Resume prompt (paste into Cursor)

```
Read beta-version/DEVELOPMENT_PLAN.md (updated 2026-07-20 late).
V1 + Phase 4.5 UX + Phase 5 AvgDown + Phase 6 Risk are shipped.
Next Full work: Phase 7 Price Alert only if I ask.
Do not change the scoring pipeline.
```

---

## 10. Related documents

| File | Role |
|------|------|
| **`DEVELOPMENT_PLAN.md` (this file)** | Full phase-by-phase plan — **canonical** |
| `V1_PLAN.md` | Decision lock + Turkish handoff notes |
| `README.md` | Folder entry |
| `agent_io_map_v1.html` | V1 I/O map |
| `agent_io_map.html` | Full 11-agent map |
| `SCENARIO3_MULTI_AGENT.md` | Original full vision narrative |
| `CURSOR_IMPLEMENTATION_SPEC.md` | Cursor prompts / schemas |
| `ui_mockup_guidance_v2.html` | Guidance / brief design target |
| `ui_mockup_buy_thesis.html` | Buy thesis card mock |
| `ui_mockup_all_views.html` | Portfolio / Candidates / ETF / Heatmap mocks |
