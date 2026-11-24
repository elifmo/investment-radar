# Cursor command guide (historical)

> **November 2026:** Start with **[README.md](../README.md)** and **[CLAUDE_EN.md](CLAUDE_EN.md)**. This file is an old phase-by-phase prompt log, not current UI spec.
> Live dashboard: https://investment-radar-usa.web.app

## BEFORE STARTING

Open Cursor, open the project folder.

In Cursor AI Chat, write this:

> "Read CLAUDE_EN.md. What's the current pipeline architecture and Firestore collections?"

After Cursor reads it, use the phases below for **new features only** — not for rebuilding what already exists.

---

## 📸 Want to See Dashboard Examples?

Open the `dashboard-example.png` and `dashboard-candidates-tab.png` files in the project. These are actual working dashboard implementations.

**Example: MSFT Stock**
- Why today? 50-day MA broken + AGPro + Volume 2.1x
- Risk/Reward 1:1.6 (green)
- Volume 2.10x (green)
- Earnings 8 days away (gray)
- Signals: 12 positive, 0 negative
- AGPro Stop Run 82/100 (excellent)

Tell Cursor:

> "Look at dashboard-example.png and dashboard-candidates-tab.png (these are design reference - layout style).
> Build a dashboard exactly like these screenshots in LAYOUT and DESIGN.
> BUT: ALL TEXT MUST BE IN ENGLISH.
> Dark mode, all metrics visible, detailed signal grid, AGPro section, before you act checklist.
> Every label, button, text = English."

---

## 🌐 Language Standardization

**IMPORTANT:** Dashboard is currently in **FULL English**.

Translation reference:
```
Support               → Destek
Resistance           → Direnç
Volume               → Hacim
Earnings             → Kazanç
Risk/Reward          → Risk/Ödül
Stop Run             → Dur Dönüş
Reversal             → Geri Dönüş
High confidence      → Yüksek güven
Signal               → Sinyal
Trend                → Eğilim
Bull Stop Run        → Boğa Dur Dönüşü
Confirmed Bull Reversal → Boğa Geri Dönüşü Onaylandı
Reclaim              → Talep Geri Alma
Invalidation         → Geçersizleştirme
```

**Future Turkish Option (Phase 4+):**
Tell Cursor:
> "Prepare i18n (internationalization) setup. Create tr.json and en.json files with all UI text. Add language toggle button (top right). Default to English for now, but structure ready for Turkish."

---

# PHASE 1 — PIPELINE RUNS (Week 1-2)

Goal: GitHub Actions pipeline runs regularly, writes to Firebase.

## Step 1.1 — Install Requirements

```
Tell Cursor:
"requirements.txt exists. We ran pip install -r requirements.txt.
Which files are missing, which need testing?"
```

Cursor will check the directory structure.

## Step 1.2 — Test Event Filter

```
Tell Cursor:
"Test src/event_filter.py. Run it on 5 US stocks (MSFT, NVDA, AAPL, TSLA, GOOGL)
and 3 Turkish stocks (FROTO.IS, ASELS.IS, TUPRS.IS).
Which events triggered? Show results."
```

Expected:
- Volume spike detection
- EMA crossover detection
- RSI bounce detection

## Step 1.3 — Run Pipeline (local)

```
Tell Cursor:
"Terminal: cd src && python pipeline.py usa
Show the output. Fix any errors."
```

Then for BIST:

```
Tell Cursor:
"python pipeline.py bist and show the result."
```

## Step 1.4 — Firebase Connection

```
Tell Cursor:
"Does src/pipeline.py write to Firebase?
Test it: go to firebase console, check if data was written.
If not, add the connection."
```

## Step 1.5 — GitHub Actions Setup

```
Tell Cursor:
"Add GitHub Actions workflow. Every day:
- 17:45 TR: python pipeline.py bist
- 23:15 TR: python pipeline.py usa
Write .github/workflows/pipeline.yml using cron syntax."
```

**PHASE 1 Completion Checklist:**
- [ ] Pipeline runs locally
- [ ] BIST and USA run separately
- [ ] Writes to Firebase
- [ ] GitHub Actions scheduled
- [ ] Test for 3 days (check for errors)

---

# PHASE 2 — BASIC DASHBOARD (Week 3-4)

Goal: GitHub Pages has working dashboard, Firebase reads data.

## Step 2.1 — HTML Template

```
Tell Cursor:
"Create frontend/index.html. Include:
- Header: 'Investment Radar — Daily Candidates'
- Tab navigation: Candidates, My Radar, Statistics
- Left panel: candidate table
- Right panel: selected stock detail
- IMPORTANT: ALL TEXT MUST BE IN ENGLISH
- Professional CSS (Tailwind-style)
- Responsive for mobile"
```

## Step 2.2 — Firebase Reading

```
Tell Cursor:
"Add JavaScript to index.html. Connect Firebase SDK.
Read daily_candidates, show in table.
When row clicked, show details on right side.
Show 'Loading...' while fetching."
```

## Step 2.3 — Add to Radar (Frontend)

```
Tell Cursor:
"Implement +ADD TO RADAR button:
1. Click opens modal with: Thesis (textarea) and Exit Condition (textarea)
2. User fills in and clicks OK
3. Data written to Firebase: {user_id: 1, ticker, thesis, exit_condition}
4. Modal closes, table refreshes"
```

## Step 2.4 — GitHub Pages Deploy

```
Tell Cursor:
"Deploy dashboard to GitHub Pages:
1. Create .github/workflows/deploy.yml
2. On push to main, copy frontend/index.html to gh-pages branch
3. Enable GitHub Pages in repo settings
4. Dashboard live at: https://[username].github.io/yatirim-radar"
```

**PHASE 2 Completion Checklist:**
- [ ] GitHub Pages dashboard live
- [ ] Can add/view candidates
- [ ] Firebase connection working
- [ ] Responsive design (mobile OK)
- [ ] All text in English

---

# PHASE 2B — RADAR MANAGEMENT (Parallel)

Goal: User can add/remove stocks from radar via dashboard.

## Step 2B.1 — Firebase Schema

```
Tell Cursor:
"Create radar_items collection in Firebase:
Structure: {user_id, ticker, market, thesis, exit_condition, added_at, is_active}
Add test data: MSFT (user 1), FROTO.IS (user 1)"
```

## Step 2B.2 — Add/Remove Buttons

```
Tell Cursor:
"Add '+Radar' button to each Candidates table row.
Click → modal opens (Thesis and Exit Condition inputs).
OK → write to Firebase radar_items."
```

## Step 2B.3 — Radar Panel

```
Tell Cursor:
"Add third panel: 'My Radar'.
List all radar_items (user_id=1).
Each item: Thesis (tooltip), Exit Condition (tooltip), Remove button.
Read real-time from Firebase."
```

## Step 2B.4 — Decision Logs

```
Tell Cursor:
"Log every decision: 'Add to Radar', 'Skip', 'Remove'.
Save reason text too.
Write to Firebase decisions table."
```

**PHASE 2B Completion Checklist:**
- [ ] + Radar button works
- [ ] Thesis and exit condition saved
- [ ] My Radar panel shows items
- [ ] Remove button works
- [ ] Decision history exists

---

# PHASE 3 — USER FEEDBACK & OPTIMIZATION (Week 5-6)

Goal: Gather data on mail vs dashboard usage effectiveness.

## Step 3.1 — Statistics Page

```
Tell Cursor:
"Add statistics page to dashboard:
- How many candidates from YatirimRadar vs Stock Limit?
- How many added/skipped?
- How many overlap (both sources)?
- Average score?
Pull all data from firebase decisions table."
```

## Step 3.2 — User Feedback Form

```
Tell Cursor:
"Add simple survey to dashboard:
'Which channel was more helpful today?'
Options: Mail, Dashboard, Both, Neither
Save selection (analytics table)."
```

## Step 3.3 — Mail vs Dashboard Comparison

```
Tell Cursor:
"Add chart to statistics page:
X axis: Days (last 7 days)
Y axis: Stock count
Two lines: Mail sources (SLB), Dashboard sources (YR)
Show overlap."
```

**PHASE 3 Completion Checklist:**
- [ ] Statistics page ready
- [ ] Overlap calculated
- [ ] User feedback captured
- [ ] 2 weeks of data
- [ ] Enough data to decide

---

# PHASE 4 — DECISION & OPTIMIZATION (Week 7-8)

Goal: Analyze data and make mail vs dashboard decision.

## Step 4.1 — Analysis

```
Tell Cursor:
"Analyze last 2 weeks of data:
1. Overlap ratio? (both sources / total)
2. Who triggered first? (1H advantage for who?)
3. False signals comparison (worse suggestions from who?)
4. User feedback says what?
Export as CSV."
```

## Step 4.2 — Decision

Make a decision:
- **Mail continues**, Dashboard backup → `SEND_EMAIL = True`
- **Dashboard continues**, Mail off → `SEND_EMAIL = False`
- **Both together** → Keep both

## Step 4.3 — Cleanup

```
Tell Cursor:
"Finalize config. Decision made: [Mail/Dashboard/Both]
Remove unnecessary tests. Production ready.
Update README.md (how users will use this)."
```

**PHASE 4 Completion Checklist:**
- [ ] Data analyzed
- [ ] Decision made
- [ ] Production config set
- [ ] README ready
- [ ] First user onboarded

---

# TROUBLESHOOTING COMMANDS FOR CURSOR

## Pipeline Errors

```
"src/event_filter.py isn't working. Error: [error message]
What's wrong? Fix it."
```

## Firebase Connection Error

```
"Firebase credentials missing. Steps:
1. Create Firebase project (console.firebase.google.com)
2. Get credentials
3. Add to .env file"
```

## Dashboard Data Not Showing

```
"Dashboard shows no candidates. Debug:
1. Open Firefox console (F12)
2. Check Network tab for Firebase request
3. Show me any errors."
```

## GitHub Actions Failed

```
"GitHub Actions log failed. Show me which step broke."
```

---

# QUICK REFERENCE

**Phase 1 question:** Does pipeline run?
→ Test: `python pipeline.py usa`

**Phase 2 question:** Does dashboard show data?
→ Open in browser, check console

**Phase 3 question:** Mail vs Dashboard — which is better?
→ Check statistics page

**Phase 4 question:** Which one to keep?
→ Data-driven decision

---

# IMPORTANT NOTES

1. **Use Cursor AI chat** — descriptions, not terminal commands
2. **Check completion list after each phase** — don't skip steps
3. **Commit to GitHub** — push after each step
4. **One step per day** — rushing causes errors
5. **If error, go back** — to that phase, fix, then forward

---

*Last update: May 2026*
