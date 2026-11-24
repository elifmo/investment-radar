# Dashboard Design Specification

**Last updated:** July 2026 (live USA chrome updated November 2026)  
**Live URLs:** https://investment-radar-usa.web.app · https://investment-radar-bist.web.app  
**Hosting:** Firebase Hosting (not GitHub Pages)  
**Data:** Firestore (Firebase JS SDK, read-only for pipeline data)

> **Live USA tabs (Nov 2026):** Momentum · Oversold · Sector Heatmap · ETF Scan · Deep Dive.  
> Sections below still describe the full original 7-tab spec (Candidates, Opportunities, My Radar, Statistics). Treat this file as design history; the live site is the source of truth.

---

## Overview

Single-page application that displays pipeline output for a **~523-ticker USA universe** (S&P 500 + Nasdaq-100 extras + watchlist) and **~93 BIST tickers**:

1. **Momentum** (was Candidates) — funnel top names (event filter + scorer + decision engine)
2. **Sector Heatmap** — S&P 500 + theme drill-down
3. **ETF Scan** — EUR-listed ETFs (VHYL, DFEN, NUKL, etc.)
4. **Oversold** — Fib EMA radar + today’s oversold chips (Opportunities tab still in code, hidden)
5. **My Radar** — Personal watchlist (Firebase Auth; currently hidden on USA)
6. **Statistics** — Placeholder
7. **Deep Dive** — Per-ticker AI analysis (Cloud Function)

Language: **English** (USA dashboard)  
Responsiveness: Mobile-friendly (custom CSS, dark theme)

---

## Tab Summary (USA dashboard)

| Tab | Left / main | Right / detail |
|-----|-------------|----------------|
| Candidates | Table: ticker, sector, close, score, streak, why | Detail: RS, grade, RSI, **Stoch %K/%D**, support, decision banner |
| Sector Heatmap | Treemap + theme drill | Stock list for selected sector/theme |
| ETF Scan | ETF table with signal pills | Support/resistance, strategy text |
| Opportunities | 4 sections in card grid | Click card → same detail panel as Candidates |
| My Radar | User's radar items | Thesis + exit condition |
| Deep Dive | Ticker input + market filter | AI-generated analysis |

### Oversold strip (Candidates tab)

Above the candidates table, a chip row shows top 15 oversold tickers from `oversold_watch` (scanned across all **521** pipeline stocks):

- Green border = **deep** (Stoch < 20 + RSI < 35)
- Shows: `TICKER  S{stoch}  R{rsi}`
- Click → opens detail panel (even if not in top 10)

### Opportunities → Oversold Watch

Full cards with price, support, Stoch, RSI, quality grade.  
Separate from momentum candidates — no bounce required.

---

## Layout Structure (Candidates tab)

```
┌─────────────────────────────────────────────────────┐
│ INVESTMENT RADAR — Daily Candidates & My Radar      │
├─────────────────────────────────────────────────────┤
│ [TAB] Candidates  [TAB] My Radar  [TAB] Statistics  │
├─────────────────────────────────────────────────────┤
│                                                     │
│ LEFT PANEL (Main Table)                             │
│ ┌──────────────────┐                                │
│ │ Market: [USA ▼]  │                                │
│ ├──────────────────┤                                │
│ │ Ticker │ Score   │                                │
│ │ MSFT   │ 78.5 ✓  │ ← Click to detail             │
│ │ NVDA   │ 72.1 ◆  │                                │
│ │ AAPL   │ 65.0    │                                │
│ │ ...              │                                │
│ └──────────────────┘                                │
│                                                     │
│ RIGHT PANEL (Detail Card)                           │
│ ┌──────────────────────────────────┐                │
│ │ MSFT | Score: 78.5 | Confidence  │                │
│ │ Market: USA | State: Strong Up   │                │
│ ├──────────────────────────────────┤                │
│ │ WHY TODAY (yellow box)           │                │
│ │ 📊 Volume 2.1x average           │                │
│ ├──────────────────────────────────┤                │
│ │ KEY METRICS                      │                │
│ │ R/R: 1.6 | Vol: 2.1x | Earn: 30d│                │
│ ├──────────────────────────────────┤                │
│ │ SHORT-TERM SIGNALS (1H)          │                │
│ │ ✓ EMA Aligned  ✓ RSI 45  ✓ Vol   │                │
│ │                                  │                │
│ │ LONG-TERM SIGNALS (Daily)        │                │
│ │ ✓ Above EMA20  ✓ Support Hold    │                │
│ ├──────────────────────────────────┤                │
│ │ [+ ADD TO RADAR] [→ SKIP]        │                │
│ └──────────────────────────────────┘                │
└─────────────────────────────────────────────────────┘
```

---

## 📸 Real Dashboard Examples

Below are actual working dashboard implementations with all features active:

## Tab 1: Candidates (Daily Candidates)

**File:** `dashboard-candidates-tab.png` ← COMPLETE

**Left Panel — Candidate List:**
- USA section
  - MSFT (Technology, score 81) — selected
  - UNH (Healthcare, score 76) — "+ Add to Radar" button
  - NVDA (Semiconductors, score 71) — "In Radar" label
- BIST section
  - OYAKC (Finance, score 38) — "+ Add to Radar" button
  - FROTO (Automotive, score 79) — "+ Add to Radar" button

**Features:**
- Market grouping (USA, BIST)
- Score color-coded (green 70+, yellow 65-70, red <65)
- Sector information
- Status label (button or "In Radar")
- Active row highlight

**Right Panel — MSFT Detail (Complete):**

**Header Section:**
- Ticker: MSFT
- Score: 81/100
- Labels: "Strong uptrend" + "High confidence"

**Why today? (White box):**
- "50-day average broken for first time today"
- "Volume 2.1x of 5-day average"
- "AGPro 4H bull reversal triggered this morning"

**Four Metrics (Separate boxes):**
1. Risk/Reward: 1:1.6 (Risk 2.4% · Reward 4.0%)
2. Volume: 2.10x average (Strong buy confirmation)
3. Earnings Date: 8 days away (Keep under watch)

**Signal Summary:**
- "12 positive · 0 negative · 12 total signals"
- Description: "Strong momentum, valuation attractive vs sector. Earnings 8 days out but trend strongly supported."

**Signal Grid (SHORT-TERM — 1H):**
1. EMA5 > EMA20 ✓ Momentum strong
2. Volume 1H ✓ 2.1x average
3. Resistance Break 1H ✓ Broken
4. EMA20 > EMA50 ✓ Uptrend
5. Bollinger 1H ✓ Expanding
6. Support 1H ✓ (price level shown)

**Signal Grid (LONG-TERM — Daily):**
1. EMA50 > EMA200 ✓ Strong trend
2. RSI Daily ✓ 62 — healthy
3. ATR Daily ✓ Expanding
4. Bollinger Daily ✓ Expanding
5. Resistance Daily ✓ Broken holding
6. Volume Daily ✓ Buy confirmed

**Support/Resistance Levels:**
- Support (green): 417.50
- Resistance (red): 445.00

**AGPro — Stop Run Reversal (White box):**
- Label: "REVERSAL ACTIVE" (green)
- 4H Section:
  - Stop Run: Bull Stop Run
  - Confirmation: Confirmed Bull Reversal (green)
  - Reclaim: Strong (green)
- Daily Section:
  - Stop Run: Bull Stop Run
  - Confirmation: Confirmed Bull Reversal (green)
  - Reclaim: Strong (green)
- Invalidation: 411.20
- Target: 438.50
- **Reversal Score: 82/100** (excellent)

**Before you act (Checklist):**
- ☑ Trend + AGPro both confirmed
- ☑ Risk/Reward 1:1.6 — acceptable
- ☑ ⚠️ Earnings 8 days away — watch position size
- ☑ Stop below 417.50

---

### Tab 2: Mevcut Radarım (My Radar)

**File:** `dashboard-example.png`

**ASML Example:**
- Neden bugün? (White box, top) — "Sabah breakout onaylandı · AGPro 4H + Daily ikisi birden aktif · Volume 2.4x ortalama"
- Risk/Reward: 1:2.7 (green — good)
- Hacim: 2.40x ortalama (green)
- Earnings: Yakın earnings yok (gray)
- Sinyal grid: 12 positive · 0 negative · 12 total signals
- Short-term (1H): 4 sinyal (EMA alignment, Volume, Breakout, Support)
- Long-term (Daily): 4 sinyal (EMA trend, RSI, ATR, Bollinger)
- Support (green): 210.50 · Resistance (red): 228.50
- **AGPro Stop Run Reversal** section (advanced):
  - 4H: Bull Stop Run confirmed, Strong reclaim, Invalidation 208.00, Target 228.50
  - Daily: Bull Stop Run confirmed, Strong reclaim
  - Reversal Score: 88/100
- **Before you act:** AGPro 4H + Daily güçlü setup · R/R 1:2.7 iyi · Stop konumlanmış

**Key observation:** When both R/R is good AND volume is high AND earnings are clear, confidence is highest. When any of these are red/negative (like OYAKC with R/R 1:0.7), the "Before you act" warns NOT to enter.

---

## Tab 1: Candidates (Default)

### Left Panel — Candidate Table

**Columns:**
- Ticker (left-aligned, blue, clickable)
- Score (0-100, color-coded: green 70+, yellow 65-70, red <65)
- State badge (Strong Uptrend, Bullish Momentum, Early Breakout, etc.)
- Confidence (High/Medium/Low, icon)
- Market badge (USA / BIST, different colors)

**Filters:**
- Market dropdown: USA / BIST / Both
- Sort by: Score DESC (default) / State / Market
- Min Score slider (0-100, default 60)

**Actions:**
- Click row → Right panel opens
- Hover → Row highlight
- Double-click → Quick add to radar

### Right Panel — Detailed View

**Header Section:**
```
MSFT                                             ×
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Score: 78.5  |  State: Strong Uptrend  |  High Confidence  |  USA
```

**Why Today (Yellow Alert Box):**
```
⚠️ THIS STOCK TRIGGERED TODAY
📊 Volume spike: 2.1x average
   (typical: 1.2M shares, today: 2.5M)
```

**Key Metrics Row:**
```
Risk/Reward: 1.6  |  Volume: 2.1x avg  |  Earnings: 30 days
```
(R/R < 1.5 shows red background)

**Signal Grid (4 columns):**
```
SHORT-TERM (1H)          │  LONG-TERM (Daily)
─────────────────────────┼──────────────────────
✓ EMA5>EMA20 (bullish)  │  ✓ Above EMA20
✓ RSI 45 (neutral)      │  ✓ Resistance far
✓ Volume spike          │  ✓ Support holds
✗ Bollinger lower band  │  ✗ ATR declining
```

**Key Levels:**
```
Support (green): 425.30  |  Resistance (red): 452.80
```

**Action Buttons (Bottom):**
```
[+ ADD TO RADAR]  [→ SKIP FOR NOW]
```

Optional: Modal on "+ ADD" for Thesis input

---

## Tab 2: My Radar (Tracked Stocks)

**Left Panel — Radar Item List:**
```
Ticker | Added | State | Last Signal | Actions
─────────────────────────────────────────────
MSFT   | 3d    | ⚠️ Yellow | EMA dip | [×]
NVDA   | 7d    | ⚠️ Yellow | Volume ▲ | [×]
ASML   | 12d   | ✓ Green | Support holds | [×]
AAPL   | 25d   | ✗ Red | Breakdown risk | [×]
```

Color meanings:
- Green dot: All signals positive
- Yellow dot: Mixed signals
- Red dot: Caution/exit signals

**Right Panel — Radar Item Detail:**
```
MSFT (NASDAQ)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 My Thesis:
"Strong earnings expected, above 50-day MA, 
volume increasing, breakout setup"

🚨 Exit Condition:
"Break below support 420 or if volume collapses"

📊 Current Status:
Price: $425.30 | Signals: 3 positive, 1 negative
Last Update: Today 14:35

[EDIT]  [REMOVE FROM RADAR]
```

---

## Tab 3: Statistics (Phase 2+)

**Header:**
"Mail vs Dashboard — Last 14 Days"

**Grid Layout:**
```
Candidates Found:        | Total Candidates: 42
├─ Mail only: 8 (19%)    |
├─ Dashboard only: 18 (43%) | Overlap: 16 (38%)
└─ Both: 16 (38%)        |

Decision Distribution:
├─ Added to Radar: 12
├─ Skipped: 28
└─ Removed: 2

Feedback (if available):
├─ Mail more useful: 3 votes
├─ Dashboard more useful: 4 votes
└─ Both useful: 2 votes
```

**Chart:**
X-axis: Days (past 14)
Y-axis: Stock count
Two lines: Mail sources vs Dashboard sources

---

## 🌐 Language Support (Phase 3+)

**Current State:** Dashboard is in Turkish (fully localized)

**Future English Option:**

Tell Cursor:

> "Prepare i18n (internationalization) setup:
>
> - Add language variable to frontend (tr/en)
> - Move all UI text strings to language files
> - Create src/locales/tr.json and src/locales/en.json
> - Add language toggle button (top right corner)
> - Save language preference in localStorage
>
> For now Turkish is default, but structure should be i18n-ready."

### 1. Header
```
[× close]
MSFT | Score 78.5 | Strong Uptrend | High Confidence | USA
```

### 2. Why Today (Yellow Alert)
```
⚠️ Volume 2.1x average (typical 1.2M, today 2.5M)
```
(Only show the primary trigger reason)

### 3. Metrics Row
```
R/R: 1.6  |  Volume: 2.1x avg  |  Earnings: 30d away
```
Red background if R/R < 1.5

### 4. Signals Grid (4x2)
ST column (1H) and LT column (Daily)
Each signal: icon (✓/✗) + label + value

### 5. Key Levels
```
Support (green): 425.30
Resistance (red): 452.80
```

### 6. Action Buttons
```
[+ ADD TO RADAR]  [→ SKIP]
```

---

## Color Scheme (Tailwind)

| Element | Color | Tailwind |
|---|---|---|
| Score 70+ | Green | `bg-green-100` / `text-green-700` |
| Score 65-70 | Yellow | `bg-yellow-100` / `text-yellow-700` |
| Score <65 | Red | `bg-red-100` / `text-red-700` |
| Support level | Green | `text-green-600` |
| Resistance level | Red | `text-red-600` |
| Positive signal | Green | `text-green-500` |
| Negative signal | Red | `text-red-500` |
| Why Today box | Yellow | `bg-yellow-50` / `border-l-4 border-yellow-400` |
| Header | Slate | `bg-slate-800` / `text-white` |

---

## Responsive Breakpoints

| Screen | Layout |
|---|---|
| Mobile (<640px) | Stack vertically (table below detail) |
| Tablet (640-1024px) | Side-by-side, table narrower |
| Desktop (>1024px) | Full side-by-side, proportional |

---

## Data Loading States

**Initial Load:**
```
Loading candidates...
```

**No Data:**
```
No candidates found today.
Check back at 17:45 TR (BIST) or 23:15 TR (USA).
```

**Error:**
```
Failed to load data. Please refresh the page.
```

---

## Interaction Patterns

1. **Click candidate row** → Detail opens on right
2. **Click "+ Add to Radar"** → Modal: enter Thesis and Exit Condition
3. **Click "Skip"** → Log decision, move to next candidate
4. **Click radar item** → Detail opens on right
5. **Click "×" on radar** → Confirm dialog, then remove
6. **Filter/sort** → Table updates instantly

---

## Phase Rollout

**Phase 1:** Tab 1 (Candidates only, no Add/Skip)
**Phase 2:** Tab 1 + 2 (Add to Radar working) + Stock Limit side panel
**Phase 3:** All tabs + Statistics populated with real data

