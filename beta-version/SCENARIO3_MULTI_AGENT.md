# Investment Radar — Scenario 3: Multi-Agent Personalized System

**Active implementation plan:** [`DEVELOPMENT_PLAN.md`](./DEVELOPMENT_PLAN.md) (V1 + Full phases) · decisions: [`V1_PLAN.md`](./V1_PLAN.md) · flow: [`agent_io_map_v1.html`](./agent_io_map_v1.html)  
**Status:** Spec — full vision (target architecture)  
**Version:** 1.2  
**Date:** July 2026  
**Change in v1.1:** Orchestrator Agent added as Layer 4.5. Forecast Agent deferred to future version.  
**Change in v1.2:** Events Agent added (Layer 6 — intraday). Price Alert code monitor added. Morning brief flow documented.  
**Principle:** Candidates are not universal. Every recommendation is filtered through your portfolio, your macro context, and your situation.

---

## The Core Problem This Solves

**Current system asks:** "Which stocks look good technically today?"  
**This system asks:** "Which stocks should YOU consider buying today, given your portfolio and the current macro?"

A stock scoring 78/100 technically is not automatically right for you if:
- You already have 40% concentration in its sector
- Macro is risk-off
- You have a losing position in the same sector that needs attention first

---

## The 5-Question Decision Framework

Every candidate must pass all 5 questions before being shown to you:

1. **Is macro favorable?** — Is the environment right for buying?
2. **Does it fit my portfolio?** — Concentration, correlation, existing exposure?
3. **Is the thesis clear?** — Why this stock specifically?
4. **Is the technical entry right?** — Good timing, or wait?
5. **What is my exit?** — Defined before entry.

Questions 1–2 are answered by agents automatically. Questions 3–5 involve you.

---

## Architecture Overview

```
LAYER 1 — DATA (Firestore, updated nightly)
  daily_candidates · radar_items · macro_regime · sector_status

LAYER 2 — CODE PIPELINE (unchanged)
  event_filter → detailed_scorer → decision_engine → daily_candidates

LAYER 3 — SHARED AGENTS (feed both branches)
  Macro Agent · Sector Rotation Agent · Earnings Preview Agent

LAYER 4A — MY RADAR AGENTS        LAYER 4B — CANDIDATES AGENTS
  Exit Signal Agent                  Portfolio Fit Agent
  Averaging Down Agent               Entry Timing Agent
  Risk Summary Agent                 Position Sizing Agent

LAYER 4.5 — ORCHESTRATOR
  Reads all agent outputs → writes agents/daily_brief

LAYER 5 — USER OUTPUT (morning brief, ready at market open)
  My Radar (action-first rows)       Candidates (personalized, filtered)

LAYER 6 — INTRADAY MONITORING (runs continuously during market hours)
  Events Agent (LLM)                 Price Alert (code only)
  company announcements              target price reached
  sector news                        no LLM, yfinance poll
```

### Timing

| When | What runs |
|------|-----------|
| 23:00–23:30 | Code pipeline (521 stocks) |
| 23:30–23:45 | Layer 3: Shared agents |
| 23:45–00:00 | Layer 4A + 4B: Radar + Candidates agents |
| 00:00 | Layer 4.5: Orchestrator writes daily_brief |
| Morning | Brief is ready — user opens app, sees today's plan |
| Market hours | Layer 6: Events Agent + Price Alert monitors continuously |

---

## Layer 3 — Shared Agents

These agents run once per night and feed both My Radar and Candidates.

---

### Agent 1: Macro Agent

**Purpose:** Evaluates the current macro environment. Is this a good time to be buying?

**Inputs:**
- `macro_regime/current` (already in Firestore)
- Market indices trend (SPY, QQQ — fetched via yfinance)
- VIX level
- Sector ETF performance (already in `sector_status`)

**Logic:**
- RISK_ON + SPY above 50d EMA + VIX < 20 → `bullish`
- Mixed signals → `neutral`
- RISK_OFF or SPY below 200d EMA or VIX > 30 → `cautious`

**Output written to Firestore:** `agents/macro_signal`
```json
{
  "signal": "bullish",
  "summary": "Risk-on environment. SPY above 50d EMA, VIX at 16. Good conditions for new positions.",
  "updated_at": "2026-07-19"
}
```

**Impact on Candidates:** `cautious` signal reduces candidate list — only highest-conviction entries shown.  
**Impact on My Radar:** Risk Summary Agent reads this to contextualize portfolio health.

**Model:** Claude Haiku 4.5  
**Estimated cost:** ~$0.002/run

---

### Agent 2: Sector Rotation Agent

**Purpose:** Identifies which sectors are gaining strength and which are weakening. Used in both directions — to filter new entries and to warn about existing positions.

**Inputs:**
- `sector_status` (already in Firestore — sector ETF performance)
- 5-day and 20-day momentum per sector

**Logic:**
- Sector ETF trending up + volume increasing → `strengthening`
- Sector ETF flat or mixed → `neutral`
- Sector ETF declining + volume increasing → `weakening`

**Output written to Firestore:** `agents/sector_rotation`
```json
{
  "sectors": {
    "semiconductors": "weakening",
    "energy": "strengthening",
    "healthcare": "neutral",
    "technology": "neutral"
  },
  "summary": "Semiconductor rotation out underway. Energy gaining momentum.",
  "updated_at": "2026-07-19"
}
```

**Impact on Candidates:** Stocks in weakening sectors are flagged or excluded.  
**Impact on My Radar:** Positions in weakening sectors get `Sector ⚠` tag and amber dot.

**Model:** Claude Haiku 4.5  
**Estimated cost:** ~$0.002/run

---

### Agent 3: Earnings Preview Agent

**Purpose:** For any stock approaching earnings (≤14 days), provides historical reaction analysis and volatility expectations.

**Inputs:**
- `daily_candidates.days_to_earnings` (already exists)
- `radar_items` — which radar positions have earnings approaching
- Historical earnings data via yfinance

**Logic:**
- Calculates average ±% move on past 8 earnings
- Checks consensus direction (beat/miss trend)
- Flags if earnings are within 7 days as high-risk

**Output written to Firestore:** `agents/earnings_preview/{ticker}`
```json
{
  "ticker": "NVDA",
  "days_to_earnings": 6,
  "avg_move_pct": 9.2,
  "typical_direction": "both",
  "risk_level": "high",
  "note": "NVDA has moved ±9.2% on average over last 8 earnings. High volatility event. Consider reducing size before report.",
  "updated_at": "2026-07-19"
}
```

**Impact on Candidates:** High-risk earnings stocks get `Earnings ⚠` warning on candidate card.  
**Impact on My Radar:** Positions with earnings ≤7d get `Earnings Xd` amber tag.

**Model:** Claude Haiku 4.5  
**Estimated cost:** ~$0.003/run (only runs for tickers with upcoming earnings)

---

## Layer 4A — My Radar Agents

---

### Agent 4: Exit Signal Agent

**Purpose:** Nightly scan of all Holding positions. Checks whether exit conditions are met using technical data + shared agent outputs.

**Inputs:**
- `radar_items` — your positions with exit_condition
- `daily_candidates` — current scores and technical signals
- `agents/sector_rotation` — sector health
- `agents/macro_signal` — macro context

**Logic per position:**
- Has price breached exit_condition? → flag `exit`
- Score declining 3+ weeks + sector weakening → flag `review`
- Score stable + thesis intact → flag `ok`

**Output written to Firestore:** `trade_entries/{id}/daily_notes`
```json
{
  "date": "2026-07-19",
  "flag": "exit",
  "note": "Support at $97.22 breached. EMA alignment broken. Score declined from 71 to 38 over 3 weeks. Semicon sector weakening. Exit condition triggered.",
  "score": 38,
  "action": "Exit this position"
}
```

**User sees:** Red dot + "Exit now →" on row. Detail panel opens with "Exit this position" banner at top.

**Model:** Claude Haiku 4.5  
**Estimated cost:** ~$0.005/run (scans all holding positions)

---

### Agent 5: Averaging Down Agent

**Purpose:** When a Holding position is down significantly, evaluates whether averaging down makes sense right now.

**Inputs:**
- `radar_items` — position with entry price and thesis
- Current price from `daily_candidates`
- `agents/sector_rotation`
- `agents/macro_signal`
- P&L calculated from entry price

**Logic — averaging down is suggested only if ALL are true:**
- Original thesis still intact (score not collapsed below 40)
- Price is at or near a support level (from `daily_candidates.support`)
- Sector not weakening
- Macro is not `cautious`

**Output written to Firestore:** `trade_entries/{id}/avg_down_signal`
```json
{
  "date": "2026-07-19",
  "recommendation": "wait",
  "note": "Thesis weakening and sector rotation underway. Averaging down now would increase risk in an unfavorable environment. Wait for sector stabilization.",
  "conditions_met": 1,
  "conditions_required": 4
}
```

**User sees:** In detail panel — "Average down?" section with yes/no and reasoning.

**Model:** Claude Haiku 4.5  
**Estimated cost:** ~$0.003/run

---

### Agent 6: Risk Summary Agent

**Purpose:** Evaluates the entire portfolio holistically. Produces the Portfolio Summary panel and weekly briefing.

**Inputs:**
- All `radar_items`
- All `trade_entries` with daily_notes
- `agents/macro_signal`
- `agents/sector_rotation`

**Logic:**
- Calculates concentration per sector
- Identifies weakest positions (lowest score + negative flag)
- Assesses alignment between portfolio and macro signal
- Produces plain-language weekly summary

**Output written to Firestore:** `agents/portfolio_summary`
```json
{
  "positions": 4,
  "avg_score": 71,
  "warnings": 2,
  "top_sector": "semiconductors",
  "top_sector_pct": 40,
  "concentration_warning": true,
  "macro_alignment": "partial",
  "weekly_summary": "Portfolio has 2 active warnings. INTC exit condition triggered — action needed. NVDA earnings approaching in 6 days, consider reducing size. ASML holding well. Semiconductor concentration at 40% is above recommended 33% threshold.",
  "updated_at": "2026-07-19"
}
```

**User sees:** Portfolio Summary panel at top of My Radar. Weekly email/notification.

**Model:** Claude Sonnet 5 (weekly briefing only — needs richer reasoning)  
**Estimated cost:** ~$0.02/week

---

## Layer 4B — Candidates Agents

---

### Agent 7: Portfolio Fit Agent

**Purpose:** For each technical candidate, checks whether it fits YOUR current portfolio.

**Inputs:**
- `daily_candidates` — today's technical candidates
- `radar_items` — your existing positions
- `agents/sector_rotation`

**Logic per candidate:**
- Does adding this increase sector concentration above 33%? → `no_fit`
- Is this highly correlated with an existing position? → `overlap`
- Does this diversify the portfolio? → `good_fit`

**Output written to Firestore:** `agents/candidate_fit/{ticker}`
```json
{
  "ticker": "NVDA",
  "fit": "no_fit",
  "reason": "Adding NVDA would bring semiconductor exposure to 55%. You already hold ASML. Concentration risk too high.",
  "updated_at": "2026-07-19"
}
```

**User sees:** NVDA appears in candidates with `Portfolio: doesn't fit` tag — or filtered out entirely.

**Model:** Claude Haiku 4.5  
**Estimated cost:** ~$0.005/run

---

### Agent 8: Entry Timing Agent

**Purpose:** For candidates that pass all filters, evaluates whether NOW is the right time to enter or whether waiting for a better price makes sense.

**Inputs:**
- `daily_candidates` — score, support, current price
- `agents/macro_signal`
- Technical signals (EMA, RSI, distance to support)

**Logic:**
- Price at or within 3% of support + strong technicals → `enter now`
- Price 5–15% above support → `wait for pullback — target $X`
- Strong momentum breakout → `enter now — momentum play`
- Overbought (RSI > 70) → `wait — extended`

**Output written to Firestore:** `agents/entry_timing/{ticker}`
```json
{
  "ticker": "MNST",
  "timing": "wait",
  "entry_target": 90.96,
  "note": "MNST is 9.6% above the 20d support level at $90.96. Better risk/reward to wait for a pullback toward support. Set alert at $92.",
  "updated_at": "2026-07-19"
}
```

**User sees:** Candidate row shows "Wait — target $90.96" instead of "Enter now".

**Model:** Claude Haiku 4.5  
**Estimated cost:** ~$0.005/run

---

### Agent 9: Position Sizing Agent

**Purpose:** Given your monthly budget and current portfolio state, recommends how much to allocate to a new position.

**Inputs:**
- `radar_items` — current positions and their weights
- Monthly budget parameter (€2000 — set in config)
- Candidate conviction score
- `agents/macro_signal`

**Logic:**
- High conviction (score >75) + macro bullish + good fit → up to 15% of monthly budget
- Medium conviction (score 65–75) → 8–10% of monthly budget
- Risk-off macro → reduce all sizing by 50%
- Never suggest >20% of portfolio in single position

**Output written to Firestore:** `agents/position_sizing/{ticker}`
```json
{
  "ticker": "ENPH",
  "suggested_amount_eur": 600,
  "portfolio_weight_pct": 12,
  "reasoning": "High conviction (score 79), energy sector strengthening, macro bullish. Energy adds diversification to your semicon-heavy portfolio.",
  "updated_at": "2026-07-19"
}
```

**User sees:** Candidate card shows "Suggested: €600 · 12% of portfolio".

**Model:** Claude Haiku 4.5  
**Estimated cost:** ~$0.003/run

---

## Layer 4.5 — Orchestrator Agent

**Purpose:** Reads all agent outputs and produces a single, ranked, actionable daily brief. This is the final decision layer before the user sees anything.

Without the Orchestrator, all agents give their own outputs but someone still has to reconcile conflicting signals. The Orchestrator does this automatically.

**Inputs:**
- `agents/macro_signal`
- `agents/sector_rotation`
- `agents/earnings_preview/{ticker}`
- `agents/candidate_fit/{ticker}`
- `agents/entry_timing/{ticker}`
- `agents/position_sizing/{ticker}`
- `trade_entries` with `daily_notes` (from My Radar agents)

**Logic:**

For each Holding position — ranks urgency:
- `exit` flag → Priority 1: "Exit INTC today"
- `review` flag + earnings ≤7d → Priority 2: "Review NVDA before earnings"
- `ok` flag → No action needed

For each Candidate — composite score:
```
composite = technical_score × macro_weight × sector_weight × fit_score × timing_score
```
- High composite + good fit → "Enter now"
- Good composite but timing off → "Wait — target $X"
- Low fit regardless of score → filtered out, not shown

**Output written to Firestore:** `agents/daily_brief`
```json
{
  "date": "2026-07-19",
  "macro_context": "Bullish — risk-on, energy sector strengthening",
  "my_radar_actions": [
    {"ticker": "INTC", "priority": 1, "action": "exit", "reason": "Support breached, thesis broken"},
    {"ticker": "NVDA", "priority": 2, "action": "review", "reason": "Earnings in 6 days, consider reducing"}
  ],
  "candidates_ranked": [
    {"ticker": "ENPH", "action": "enter_now", "amount_eur": 600, "reason": "Energy sector strengthening, portfolio diversifies"},
    {"ticker": "MNST", "action": "wait", "target_price": 90.96, "amount_eur": 400, "reason": "9.6% above entry target, wait for pullback"}
  ],
  "no_action_needed": ["ASML"],
  "summary": "1 exit needed, 1 position to review before earnings. 1 new entry available, 1 waiting for better price."
}
```

**User sees:** "Today's brief" banner at the top of My Radar. Candidates tab ordered by Orchestrator ranking.

**Model:** Claude Sonnet 5 — this is the most important agent, it synthesizes conflicting signals and must reason well.  
**Estimated cost:** ~$0.06/run → ~$1.20/month (runs once per night after all other agents complete)

---

## Layer 6 — Intraday Monitoring

---

### Agent 11: Events Agent

**Purpose:** Single agent that monitors two streams during market hours — company-level announcements and sector-level news. Filters everything through one question: "Does this affect my thesis for any position I hold?"

**Why one agent, not two:** Company announcements and sector news are tightly linked. A chip export ban is a sector event but immediately relevant to NVDA and ASML. Splitting into two agents would create duplication and require a merge step.

**Trigger:** Runs when new events are detected via RSS / news API (every 30 min during market hours). Only calls Claude if an event passes keyword filter for tickers in radar or sectors held.

**Inputs:**
- `radar_items` — tickers held + their thesis
- `agents/sector_rotation` — sectors the user is exposed to
- News/events feed filtered for relevant tickers and sectors

**Logic:**

Step 1 — Keyword pre-filter (code, no LLM):
- Does the event mention a ticker in radar_items?
- Does the event mention a sector the user holds?
- If neither → skip (no API call)

Step 2 — LLM materiality check (Haiku, only if Step 1 passes):
- "Given the user's thesis for [ticker], does this event change the thesis or increase risk?"
- If yes → notify user + write to Firestore
- If no → discard silently

**Events monitored:**
- Earnings releases (surprise vs consensus)
- Analyst upgrades / downgrades
- CEO / CFO change
- Guidance revision
- Regulatory decisions (export controls, drug approval, antitrust)
- Sector-level news (trade policy, interest rate decisions, commodity moves)

**Output written to Firestore:** `agents/events/{event_id}`
```json
{
  "event_id": "evt_2026-07-19_nvda_export",
  "timestamp": "2026-07-19T11:32:00Z",
  "type": "sector_news",
  "headline": "US expands chip export restrictions",
  "affected_tickers": ["NVDA", "ASML"],
  "thesis_impact": "high",
  "note": "Export restriction expansion could limit NVDA and ASML revenue in key markets. Thesis (AI cycle play) may be impaired. Suggest thesis review before end of day.",
  "action_suggested": "thesis_review"
}
```

**User sees:** Push notification + in-app alert card:
> **Events Agent — Sector news**  
> "US expands chip export restrictions — affects NVDA, ASML. Thesis review suggested."

**Model:** Claude Haiku 4.5  
**Estimated cost:** ~$0.01/event × ~30 material events/month = ~$0.30/month

---

### Price Alert — Code Monitor (not an agent)

**Purpose:** Notifies user when a Watching position hits its target entry price.

**How it works:** Simple yfinance poll every 15 minutes during market hours. No LLM involved. When `current_price ≤ entry_target`, push notification fires.

**Output:**
> **Price Alert**  
> "MNST hit $91.20 — target $90.96 within range. Consider entering."

**Cost:** $0 (no API call, code only)

---

## What the User Sees — Before vs After

### Candidates tab

**Before (Scenario 1):**
```
NVDA   78/100   Strong Uptrend   [+ Add to Radar]
MNST   74/100   Bullish Momentum [+ Add to Radar]
ENPH   71/100   Early Breakout   [+ Add to Radar]
```
Same list for everyone. No context.

**After (Scenario 3):**
```
ENPH   79/100   Energy sector ↑   Portfolio: fits ✓   Enter now · €600
MNST   74/100   Thesis valid      Portfolio: fits ✓   Wait · target $90.96 · €400
──────────────────────────────────────────────────────────
NVDA   78/100   ⚠ Portfolio: doesn't fit (semicon already 40%)
```
Filtered and sized for your situation.

### My Radar tab

**Before (Scenario 1):**
```
INTC   Holding   [exit condition]   $97.41   -29.3%
```
No guidance. You need to decide.

**After (Scenario 3):**
```
INTC   Holding   $97.41   -29.3%   [Exit now →]
```
Click → "Exit this position" banner. Reasoning. Buttons: Mark as sold / Keep holding.

---

## Phase Rollout

**Phase 1 — Shared agents only (2 weeks)**
- Macro Agent
- Sector Rotation Agent
- Earnings Preview Agent
- These feed tags into existing UI — no new UI needed

**Phase 2 — My Radar agents (2 weeks)**
- Exit Signal Agent
- Risk Summary Agent
- Portfolio Summary panel + color dots + action pills

**Phase 3 — Candidates agents (3 weeks)**
- Portfolio Fit Agent
- Entry Timing Agent
- Position Sizing Agent
- Candidates tab redesign — personalized view

**Phase 4 — Averaging Down Agent (1 week)**
- Added to My Radar detail panel

**Phase 5 — Events Agent + Price Alert (1 week)**
- Events Agent: RSS/news feed integration + keyword pre-filter + Haiku materiality check
- Price Alert: yfinance poll script, triggers on target price hit
- Push notification integration for both

---

## Cost Estimate

| Agent | Model | Frequency | Monthly cost |
|-------|-------|-----------|-------------|
| Macro Agent | Haiku 4.5 | Nightly | ~$0.04 |
| Sector Rotation Agent | Haiku 4.5 | Nightly | ~$0.04 |
| Earnings Preview Agent | Haiku 4.5 | Nightly (only earnings tickers) | ~$0.06 |
| Exit Signal Agent | Haiku 4.5 | Nightly | ~$0.10 |
| Averaging Down Agent | Haiku 4.5 | Nightly | ~$0.06 |
| Risk Summary Agent | Haiku 4.5 (daily) + Sonnet 5 (weekly) | Daily + weekly | ~$0.15 |
| Portfolio Fit Agent | Haiku 4.5 | Nightly | ~$0.10 |
| Entry Timing Agent | Haiku 4.5 | Nightly | ~$0.10 |
| Position Sizing Agent | Haiku 4.5 | Nightly | ~$0.06 |
| Orchestrator Agent | Sonnet 5 | Nightly | ~$1.20 |
| Events Agent | Haiku 4.5 | Intraday (~30 material events/mo) | ~$0.30 |
| Price Alert | Code only | 15-min poll during market hours | $0.00 |
| **Total** | | | **~$2.21/month** |

---

## Cursor Implementation Prompts

### Shared agents — run order

> "Create `src/agents/run_shared_agents.py`. This script runs nightly after the existing pipeline completes. It calls three agents in sequence: macro_agent, sector_rotation_agent, earnings_preview_agent. Each agent reads from Firestore, calls Claude Haiku API, and writes its output back to Firestore under `agents/{agent_name}`. Pass Firestore client and Anthropic client as dependencies. See SCENARIO3_MULTI_AGENT.md for each agent's input/output schema."

### My Radar agents

> "Create `src/agents/my_radar_agents.py`. After shared agents run, this script reads all radar_items from Firestore and runs Exit Signal Agent and Averaging Down Agent for each Holding position. It reads shared agent outputs from `agents/macro_signal` and `agents/sector_rotation`. It writes results to `trade_entries/{id}/daily_notes` (flag + note + action) and `trade_entries/{id}/avg_down_signal`. See SCENARIO3_MULTI_AGENT.md for schema."

### Orchestrator Agent

> "Create `src/agents/orchestrator_agent.py`. This runs last — after all other agents have written their outputs to Firestore. It reads: `agents/macro_signal`, `agents/sector_rotation`, all `agents/candidate_fit/*`, all `agents/entry_timing/*`, all `agents/position_sizing/*`, all `trade_entries` with latest `daily_notes`. It uses Claude Sonnet 5 to synthesize all signals and write a single `agents/daily_brief` document. The brief contains: ordered My Radar actions (priority 1 = exit, priority 2 = review), ranked candidates (enter now vs wait), macro context summary, and a plain-English 2-sentence summary. See SCENARIO3_MULTI_AGENT.md Layer 4.5 for full schema."

### Candidates agents

> "Create `src/agents/candidates_agents.py`. After shared agents run, this script takes today's `daily_candidates` and for each candidate runs Portfolio Fit Agent, Entry Timing Agent, and Position Sizing Agent. Monthly budget is read from `config/factors.yaml` (add field `monthly_budget_eur: 2000`). Results written to `agents/candidate_fit/{ticker}`, `agents/entry_timing/{ticker}`, `agents/position_sizing/{ticker}`. See SCENARIO3_MULTI_AGENT.md for schema."

### Frontend — personalized candidates

> "Update the Candidates tab to read agent outputs alongside technical scores. For each candidate: join `daily_candidates` with `agents/candidate_fit`, `agents/entry_timing`, `agents/position_sizing`. Show: fit badge (fits ✓ / doesn't fit ⚠), timing label (Enter now / Wait · target $X), suggested amount (€X). Sort: good fit + enter now first, no-fit candidates at bottom with reason. See SCENARIO3_MULTI_AGENT.md section 'What the User Sees'."

### Events Agent

> "Create `src/agents/events_agent.py`. This script runs every 30 minutes during market hours (09:30–16:00 ET). Step 1: Fetch recent events from news RSS feed. Step 2: Code-only keyword filter — does the event mention any ticker in `radar_items` or any sector from `agents/sector_rotation` where user has exposure? If no match, skip entirely (no API call). Step 3: If match, call Claude Haiku with: event headline + user's thesis for the affected ticker + instruction to assess whether the event materially changes the thesis or risk. If Haiku response is 'material', write to `agents/events/{event_id}` and send push notification. See SCENARIO3_MULTI_AGENT.md Agent 11 for schema."

### Price Alert

> "Create `src/monitors/price_alert.py`. Runs every 15 minutes during market hours. For each radar_item with status='watching' and entry_target set: fetch current price via yfinance. If current_price <= entry_target * 1.01 (within 1%), send push notification: 'TICKER hit $X — your target $Y is within range.' Write alert to Firestore `alerts/{ticker}_{date}`. No LLM call."

---

## What This Does NOT Change

- The existing code pipeline (event_filter, scorer, decision_engine) — still runs, still provides the technical score
- BIST pipeline — same architecture applies, same agents can cover BIST tickers
- Firebase Hosting setup — no infrastructure changes
- GitHub Actions schedule — agent scripts added to the nightly run after pipeline completes
- My Radar form — already redesigned in MY_RADAR_UI_DECISIONS.md
