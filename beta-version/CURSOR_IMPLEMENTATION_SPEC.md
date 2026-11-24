# Investment Radar — Cursor Implementation Spec
**Version:** 2.0  
**Tarih:** Temmuz 2026  
**Amaç:** Bu dosyayı Cursor'a ver. Her fazı sırayla uygulat.

> **Canonical plan:** [`DEVELOPMENT_PLAN.md`](./DEVELOPMENT_PLAN.md) (V1 Phases 0–4 + Full Phases 5–10).  
> **Güncel öncelik:** V1 çekirdek + Orchestrator + Tracker. Bu spec’teki AvgDown / Events / ayrı Risk vb. **Full (Phase 5+)**. Çakışmada DEVELOPMENT_PLAN üstündür.

---

## Ne İnşa Ediyoruz?

Mevcut sistem teknik analiz skorlarını kod ile üretiyor. Bu spec üzerine **11 Claude agent** ekliyor:

- Sabah hazır bir **daily brief** (ne al, ne sat, ne bekle)
- **My Radar** tab'ında aksiyon etiketleri (Exit now → / Hold ✓ / Review →)
- **Candidates** tab'ında kişiselleştirilmiş öneriler (portföyünü biliyor)
- Gün içi **Events Agent** (şirket açıklamaları + sektör haberleri)
- **Karar takip** sistemi (öneriler doğru muydu?)

**Temel kural:** Mevcut kod değişmiyor. Agentlar Firestore'a yazar, frontend okur.

---

## Mimari Özet

```
Gece 23:00 — Mevcut kod pipeline (521 hisse taraması)
Gece 23:30 — Shared Agents (Macro, Sector, Earnings)
Gece 23:45 — Radar Agents (Exit, AvgDown, Risk) + Candidates Agents (Fit, Timing, Sizing)
Gece 00:00 — Orchestrator Agent → agents/daily_brief yazar
Sabah       — Kullanıcı brief'i açar
Gün içi     — Events Agent (30 dk'da bir) + Price Alert (15 dk'da bir)
```

### Firestore koleksiyon haritası

```
agents/
  macro_signal
  sector_rotation
  earnings_preview/{ticker}
  candidate_fit/{ticker}
  entry_timing/{ticker}
  position_sizing/{ticker}
  portfolio_summary
  daily_brief
  events/{event_id}
  decision_log/{decision_id}      ← yeni: karar takibi için

radar_items/{id}                  ← mevcut
trade_entries/{id}/
  daily_notes                     ← yeni: ajan çıktıları
  avg_down_signal                 ← yeni
daily_candidates/{ticker}         ← mevcut
alerts/{ticker}_{date}            ← yeni: fiyat alarmları
```

---

## Faz 1 — Shared Agents (Hafta 1–2)

Önce bunlar. Diğer tüm agentlar bunların çıktısını kullanıyor.

---

### Agent 1: Macro Agent

**Dosya:** `src/agents/macro_agent.py`

**Cursor prompt:**
> "Create `src/agents/macro_agent.py`. It reads from Firestore `macro_regime/current` and fetches SPY, QQQ via yfinance (50d EMA, 200d EMA, current price). It also reads VIX. Additionally, fetch the last 5 headlines from NewsAPI (or yfinance news) for query 'fed interest rates economy' to capture recent macro events — pass these as context to Haiku. Logic: if RISK_ON AND SPY > 50d EMA AND VIX < 20 → signal = 'bullish'. If SPY < 200d EMA OR VIX > 30 → signal = 'cautious'. Otherwise → signal = 'neutral'. Calls Claude Haiku API with all raw data + news headlines and produces a 2-sentence plain-English summary that incorporates any significant recent macro news. Writes result to Firestore `agents/macro_signal`. See schema below."

**Output schema — `agents/macro_signal`:**
```json
{
  "signal": "bullish",
  "summary": "Risk-on ortam. SPY 50 günlük EMA üzerinde, VIX 16 seviyesinde. Yeni pozisyon açmak için uygun.",
  "updated_at": "2026-07-19"
}
```

**Model:** Claude Haiku 4.5  
**Maliyet:** ~$0.002/run

---

### Agent 2: Sector Rotation Agent

**Dosya:** `src/agents/sector_rotation_agent.py`

**Cursor prompt:**
> "Create `src/agents/sector_rotation_agent.py`. It reads `sector_status` from Firestore (already populated by the existing pipeline — sector ETF performance). For each sector, calculates 5-day and 20-day momentum. Classification: ETF trending up + volume increasing → 'strengthening'. Declining + volume → 'weakening'. Otherwise → 'neutral'. Additionally, for each sector fetch the last 3 headlines from yfinance news using the sector ETF ticker (e.g., XLE for energy, SMH for semiconductors) — pass these to Haiku as context so the summary can mention notable sector news (e.g., 'FDA regulation' for healthcare, 'TSMC production' for semikon). Calls Haiku with price data + news headlines to produce a 2-sentence summary per sector. Writes to `agents/sector_rotation`."

**Output schema — `agents/sector_rotation`:**
```json
{
  "sectors": {
    "semiconductors": "weakening",
    "energy": "strengthening",
    "healthcare": "neutral"
  },
  "summary": "Semikon rotasyonu devam ediyor. Enerji sektörü ivme kazanıyor.",
  "updated_at": "2026-07-19"
}
```

**Frontend etkisi:** My Radar'daki hisselere `Sector ⚠` tag'i ekle. Sector zayıfsa sarı nokta.

---

### Agent 3: Earnings Preview Agent

**Dosya:** `src/agents/earnings_preview_agent.py`

**Cursor prompt:**
> "Create `src/agents/earnings_preview_agent.py`. It reads all radar_items and daily_candidates where days_to_earnings ≤ 14. For each such ticker, fetches historical earnings via yfinance and calculates average price move over last 8 earnings. Risk level: days ≤ 7 AND avg_move > 8% → 'high'. Otherwise → 'medium' or 'low'. Calls Haiku to write a 1-sentence note per ticker. Writes to `agents/earnings_preview/{ticker}`."

**Output schema — `agents/earnings_preview/{ticker}`:**
```json
{
  "ticker": "NVDA",
  "days_to_earnings": 6,
  "avg_move_pct": 9.2,
  "risk_level": "high",
  "note": "NVDA son 8 earnings'de ortalama ±9.2% hareket etti. Yüksek volatilite riski.",
  "updated_at": "2026-07-19"
}
```

**Frontend etkisi:** My Radar satırına `Earnings 6d` amber tag ekle.

---

### Ortak runner — `src/agents/run_shared_agents.py`

**Cursor prompt:**
> "Create `src/agents/run_shared_agents.py`. This is called by GitHub Actions nightly after the existing pipeline finishes. It runs macro_agent → sector_rotation_agent → earnings_preview_agent in sequence. Each agent receives a shared Firestore client and Anthropic client. Log each agent's start/end time and any errors to console. The script exits with code 0 on success, 1 on any agent failure."

---

## Faz 2 — My Radar Agents (Hafta 3–4)

---

### Agent 4: Exit Signal Agent

**Dosya:** `src/agents/exit_signal_agent.py`

**Cursor prompt:**
> "Create `src/agents/exit_signal_agent.py`. It reads all radar_items with status='holding'. For each position: (1) reads the exit_condition field from radar_items, (2) reads current price and score from daily_candidates, (3) reads agents/sector_rotation for sector health, (4) reads agents/macro_signal. Logic: if current price ≤ exit_condition → flag = 'exit'. If score declined >20 points over 3 weeks AND sector = 'weakening' → flag = 'review'. Otherwise → flag = 'ok'. Calls Haiku with all context to produce a 2-3 sentence note explaining the flag. Writes to `trade_entries/{id}/daily_notes`."

**Output schema — `trade_entries/{id}/daily_notes`:**
```json
{
  "date": "2026-07-19",
  "flag": "exit",
  "note": "$97.22 desteği kırıldı. Skor 71'den 38'e geriledi. Semikon sektörü zayıflıyor. Çıkış koşulu tetiklendi.",
  "action": "Exit this position",
  "score": 38
}
```

**Frontend etkisi (My Radar satırı):**
- `flag = exit` → kırmızı nokta + `Exit now →` pill
- `flag = review` → sarı nokta + `Review →` pill  
- `flag = ok` → yeşil nokta + `Hold ✓` pill

**Detail panel:** Flag'e göre action banner ilk sırada göster (örnek: "Exit this position" kırmızı banner, altında "Mark as sold" ve "Keep holding" butonları).

---

### Agent 5: Averaging Down Agent

**Dosya:** `src/agents/avg_down_agent.py`

**Cursor prompt:**
> "Create `src/agents/avg_down_agent.py`. For each holding position where P&L < -10%, evaluate whether averaging down makes sense. Average down is suggested ONLY IF ALL of these are true: (1) score > 40 (thesis not collapsed), (2) current price is within 3% of support level from daily_candidates, (3) sector is not 'weakening', (4) macro signal is not 'cautious'. Calls Haiku to produce a recommendation ('avg_down' or 'wait') with a 2-sentence explanation. Writes to `trade_entries/{id}/avg_down_signal`."

**Output schema:**
```json
{
  "date": "2026-07-19",
  "recommendation": "wait",
  "note": "Thesis zayıflıyor ve sektör rotasyonu sürüyor. Şimdi ortalama düşürmek riski artırır.",
  "conditions_met": 1,
  "conditions_required": 4
}
```

---

### Agent 6: Risk Summary Agent

**Dosya:** `src/agents/risk_summary_agent.py`

**Cursor prompt:**
> "Create `src/agents/risk_summary_agent.py`. It reads all radar_items and their latest daily_notes, plus agents/macro_signal and agents/sector_rotation. Calculates: total positions, avg score, sector concentration per sector (%), count of warnings. Calls Haiku for daily portfolio health check (writes to agents/portfolio_summary). Once per week (check day of week), calls Sonnet 5 for a richer weekly summary. Weekly summary covers: what improved, what worsened, what needs attention, portfolio-macro alignment."

**Output schema — `agents/portfolio_summary`:**
```json
{
  "positions": 4,
  "avg_score": 71,
  "warnings": 2,
  "top_sector": "semiconductors",
  "top_sector_pct": 40,
  "concentration_warning": true,
  "weekly_summary": "Portföyde 2 uyarı var. INTC çıkış koşulunu tetikledi. NVDA earnings öncesi risk artıyor...",
  "updated_at": "2026-07-19"
}
```

**Frontend etkisi:** My Radar top'unda Portfolio Summary panel — `positions`, `avg_score`, `warnings`, `top_sector_pct` göster. Concentration %33 üzerindeyse sarı uyarı.

---

### My Radar runner

**Cursor prompt:**
> "Create `src/agents/run_radar_agents.py`. Runs after run_shared_agents.py completes. Calls exit_signal_agent, avg_down_agent, risk_summary_agent in sequence for all holding positions. Each writes to Firestore. Log timing and errors."

---

## Faz 3 — Candidates Agents + Orchestrator (Hafta 5–6)

---

### Agent 7: Portfolio Fit Agent

**Dosya:** `src/agents/portfolio_fit_agent.py`

**Cursor prompt:**
> "Create `src/agents/portfolio_fit_agent.py`. For each ticker in daily_candidates, check portfolio fit. Read all radar_items to calculate current sector concentration. If adding this ticker would push any sector above 33% → fit = 'no_fit', reason explains concentration risk. If ticker is highly correlated with existing position (same sector + same business model) → fit = 'overlap'. Otherwise → fit = 'good_fit'. Calls Haiku only for 'no_fit' cases to explain why. Writes to `agents/candidate_fit/{ticker}`."

**Output schema:**
```json
{
  "ticker": "NVDA",
  "fit": "no_fit",
  "reason": "NVDA eklemek semikon ağırlığını %55'e çıkarır. ASML zaten portföyde var.",
  "updated_at": "2026-07-19"
}
```

---

### Agent 8: Entry Timing Agent

**Dosya:** `src/agents/entry_timing_agent.py`

**Cursor prompt:**
> "Create `src/agents/entry_timing_agent.py`. For each candidate with fit = 'good_fit', evaluate entry timing. Read daily_candidates for: current price, support level, RSI, EMA alignment. Logic: price within 3% of support + strong technicals → timing = 'enter_now'. Price 5-15% above support → timing = 'wait', entry_target = support * 1.02. RSI > 70 → timing = 'wait', reason = 'overbought'. Calls Haiku to write a 1-sentence timing note. Writes to `agents/entry_timing/{ticker}`."

**Output schema:**
```json
{
  "ticker": "MNST",
  "timing": "wait",
  "entry_target": 90.96,
  "note": "MNST %9.6 destek üzerinde. $90.96'ya dönmesini bekle.",
  "updated_at": "2026-07-19"
}
```

---

### Agent 9: Position Sizing Agent

**Dosya:** `src/agents/position_sizing_agent.py`

**Cursor prompt:**
> "Create `src/agents/position_sizing_agent.py`. For each candidate with timing = 'enter_now' or 'wait', calculate suggested position size. Read monthly_budget_eur from config/factors.yaml (add field if missing, default 2000). Logic: score > 75 AND macro = 'bullish' AND fit = 'good_fit' → suggest up to 15% of monthly budget. Score 65-75 → 8-10%. If macro = 'cautious' → halve all sizing. Never suggest > 20% of total portfolio value. No Haiku call needed — pure math. Writes to `agents/position_sizing/{ticker}`."

**Output schema:**
```json
{
  "ticker": "ENPH",
  "suggested_amount_eur": 600,
  "portfolio_weight_pct": 12,
  "reasoning": "Yüksek skor (79), enerji sektörü güçleniyor, portföy çeşitleniyor.",
  "updated_at": "2026-07-19"
}
```

---

### Agent 10: Orchestrator Agent

**Dosya:** `src/agents/orchestrator_agent.py`

**Cursor prompt:**
> "Create `src/agents/orchestrator_agent.py`. This runs LAST — after all other agents have written their outputs. It reads: agents/macro_signal, agents/sector_rotation, all trade_entries with latest daily_notes (for My Radar), all agents/candidate_fit + agents/entry_timing + agents/position_sizing (for Candidates). Uses Claude Sonnet 5 (not Haiku) to synthesize all signals and produce agents/daily_brief. The brief must contain: (1) my_radar_actions sorted by urgency — exit > review > ok, (2) candidates_ranked — enter_now first, then wait, (3) budget_allocation showing how monthly budget is split, (4) a 2-sentence plain-English summary. Schema below."

**Output schema — `agents/daily_brief`:**
```json
{
  "date": "2026-07-19",
  "macro_context": "Bullish — enerji güçleniyor, semikon zayıf",
  "my_radar_actions": [
    {"ticker": "INTC", "priority": 1, "action": "exit", "reason": "$97.22 desteği kırıldı"},
    {"ticker": "NVDA", "priority": 2, "action": "review", "reason": "Earnings 6 gün, boyutu küçült"}
  ],
  "candidates_ranked": [
    {"ticker": "ENPH", "action": "enter_now", "amount_eur": 600, "reason": "Enerji güçleniyor, portföy çeşitleniyor"},
    {"ticker": "MNST", "action": "wait", "target_price": 90.96, "amount_eur": 400, "reason": "%9.6 yukarıda"}
  ],
  "no_action_needed": ["ASML"],
  "budget_allocation": {"enter_now": 600, "reserved": 400, "hold": 1000},
  "summary": "Bugün 1 çıkış zorunlu, 1 inceleme önerilir. ENPH için iyi giriş fırsatı var."
}
```

**Model:** Claude Sonnet 5 — bu agent'ı Haiku ile çalıştırma.  
**Maliyet:** ~$0.06/run

---

### Candidates runner

**Cursor prompt:**
> "Create `src/agents/run_candidates_agents.py`. Runs in parallel with run_radar_agents.py (both can start after run_shared_agents.py finishes). Calls portfolio_fit_agent → entry_timing_agent → position_sizing_agent in sequence per candidate. After all candidates are processed, calls orchestrator_agent. The orchestrator must run LAST."

---

### Frontend — personalized Candidates tab

**Cursor prompt:**
> "Update the Candidates tab to join daily_candidates with agents/candidate_fit, agents/entry_timing, agents/position_sizing for each ticker. Display: (1) fit badge — green 'Fits ✓' or red 'Doesn't fit ⚠' with reason on hover, (2) timing label — 'Enter now' or 'Wait · target $X', (3) suggested amount '€600'. Sort order: good_fit + enter_now first, good_fit + wait second, no_fit at bottom with reason. Hide no_fit candidates by default with a 'Show filtered (3)' toggle."

**Cursor prompt — Brief banner:**
> "Add a Daily Brief banner to the top of My Radar tab. It reads from agents/daily_brief. Show: macro_context badge, ordered my_radar_actions list (priority 1 first, red for exit / amber for review), candidates_ranked list (green for enter_now / amber for wait), budget_allocation bar (€600 allocated / €400 reserved / €1000 hold). Include the 2-sentence summary. If no brief exists yet (before first run), show a 'Brief hazırlanıyor — her gece 23:00'da güncellenir' placeholder."

---

## Faz 4 — Averaging Down UI (Hafta 7)

**Cursor prompt:**
> "Add 'Average down?' section to My Radar detail panel. It reads from trade_entries/{id}/avg_down_signal. Show: recommendation ('Şimdi ortalama düşür' or 'Bekle'), 2-sentence explanation, and conditions_met/conditions_required as '1/4 koşul sağlandı'. Only show this section for holding positions where P&L < -10%."

---

## Faz 5 — Events Agent + Price Alert (Hafta 7–8)

---

### Agent 11: Events Agent

**Dosya:** `src/agents/events_agent.py`

**Cursor prompt:**
> "Create `src/agents/events_agent.py`. This runs every 30 minutes during market hours (09:30-16:00 ET, Monday-Friday). Step 1 — fetch recent news from a free RSS feed (e.g. Yahoo Finance RSS for each ticker in radar_items). Step 2 — keyword pre-filter (no API call): does the item mention any ticker in radar_items OR any sector from agents/sector_rotation where user has a position? If no → skip. Step 3 — if keyword match, call Haiku with: (a) the event headline + body, (b) the user's thesis for the affected ticker from radar_items, (c) instruction to answer: 'Does this materially change the thesis or significantly increase risk? Reply: yes/no + 1-sentence reason.' If yes → write to agents/events/{event_id} and trigger push notification. If no → discard."

**Output schema — `agents/events/{event_id}`:**
```json
{
  "event_id": "evt_20260719_nvda_export",
  "timestamp": "2026-07-19T11:32:00Z",
  "type": "sector_news",
  "headline": "ABD çip ihracat kısıtlamasını genişletti",
  "affected_tickers": ["NVDA", "ASML"],
  "thesis_impact": "high",
  "note": "NVDA'nın Çin geliri tehdit altında. Earnings 6 gün sonra, risk ikiye katlandı.",
  "action_suggested": "thesis_review"
}
```

**Push notification format:**
> "[Ticker] — [Headline kısaltması]. Thesis'ini gözden geçir."

---

### Price Alert

**Dosya:** `src/monitors/price_alert.py`

**Cursor prompt:**
> "Create `src/monitors/price_alert.py`. Runs every 15 minutes during market hours. For each radar_item with status='watching' and entry_target set: fetch current price via yfinance. If current_price ≤ entry_target * 1.01 (within 1% of target) AND no alert was sent today for this ticker: send push notification ('TICKER hedef fiyata geldi — $X'), write to Firestore alerts/{ticker}_{date}. No LLM call."

---

## Faz 6 — Karar Takip Sistemi (Hafta 9)

Bu sistem her agent kararını loglar, 14 gün sonra outcome'u hesaplar ve hit rate gösterir.

### Decision Logger

**Cursor prompt:**
> "Create `src/tracking/decision_logger.py`. Called automatically when any agent writes a flag = 'exit' or timing = 'enter_now' or 'wait'. Writes to Firestore decision_log/{decision_id}: ticker, decision_type (exit/enter/wait/review), recommended_price (current price at time of decision), agent_name, reasoning, date. This is the input for outcome tracking."

**Schema — `agents/decision_log/{decision_id}`:**
```json
{
  "decision_id": "dec_20260714_INTC_exit",
  "ticker": "INTC",
  "decision_type": "exit",
  "agent": "exit_signal_agent",
  "recommended_price": 97.41,
  "reasoning": "$97.22 desteği kırıldı",
  "date": "2026-07-14",
  "outcome_checked": false
}
```

### Outcome Tracker

**Cursor prompt:**
> "Create `src/tracking/outcome_tracker.py`. Runs nightly. For each decision_log entry where outcome_checked = false AND date is 14+ days ago: fetch current price via yfinance. Calculate outcome: for 'exit' decisions — if price is now lower → outcome = 'correct', else 'incorrect'. For 'enter_now' — if price is now higher → 'correct'. Write outcome, price_at_check, and pct_change back to the decision_log document. Mark outcome_checked = true."

### Decision Tracker Dashboard

**Cursor prompt:**
> "Add a Decision Tracker tab (or section in My Radar). It reads all decision_log documents. Show: (1) summary cards — total decisions, correct count, hit rate %, (2) agent scorecard — hit rate per agent as a bar, (3) decision log table — date, ticker, decision, price at time, price now, outcome (✓ correct / ✗ incorrect / ⏳ pending). Sort by date descending. Add a 'Pattern insights' section below that groups incorrect decisions by agent and shows the most common failure mode."

---

## GitHub Actions — güncellenmiş schedule

**Cursor prompt:**
> "Update `.github/workflows/nightly.yml`. After the existing pipeline completes, add these steps in order: (1) `python src/agents/run_shared_agents.py`, (2) run `run_radar_agents.py` and `run_candidates_agents.py` in parallel, (3) wait for both, (4) `python src/agents/orchestrator_agent.py`, (5) `python src/tracking/outcome_tracker.py`. Add error handling — if any agent fails, log the error and continue (don't abort the whole pipeline). The existing pipeline step must not change."

For intraday (Events Agent + Price Alert), add a separate workflow:

> "Create `.github/workflows/intraday.yml`. Schedule: every 15 minutes on weekdays from 09:15 to 16:15 ET (cron: '*/15 13-21 * * 1-5'). Steps: (1) run price_alert.py, (2) run events_agent.py (every 30 min — check minute % 30 == 0 inside the script and exit early otherwise)."

---

## Maliyet Özeti

| Agent | Model | Sıklık | Aylık maliyet |
|-------|-------|--------|--------------|
| Macro Agent | Haiku 4.5 | Gece | ~$0.04 |
| Sector Rotation Agent | Haiku 4.5 | Gece | ~$0.04 |
| Earnings Preview Agent | Haiku 4.5 | Gece | ~$0.06 |
| Exit Signal Agent | Haiku 4.5 | Gece | ~$0.10 |
| Averaging Down Agent | Haiku 4.5 | Gece | ~$0.06 |
| Risk Summary Agent | Haiku (gece) + Sonnet 5 (haftalık) | Gece | ~$0.15 |
| Portfolio Fit Agent | Haiku 4.5 | Gece | ~$0.10 |
| Entry Timing Agent | Haiku 4.5 | Gece | ~$0.10 |
| Position Sizing Agent | — (pure math) | Gece | $0.00 |
| Orchestrator Agent | Sonnet 5 | Gece | ~$1.20 |
| Events Agent | Haiku 4.5 | Gün içi (~30 olay/ay) | ~$0.30 |
| Price Alert | Kod only | 15 dk'da bir | $0.00 |
| **Toplam** | | | **~$2.15/ay** |

---

## UI Değişiklikleri Özeti

### My Radar tab

1. **Portfolio Summary panel** (en üstte) — positions, avg_score, warnings, top_sector_pct, concentration uyarısı
2. **Satır sonu aksiyon pill'i** — `Exit now →` (kırmızı) / `Review →` (sarı) / `Hold ✓` (yeşil) / `Wait · $90.96` (sarı)
3. **Renk noktası** — her satırın solunda kırmızı/sarı/yeşil
4. **Agent tag'leri** — `Earnings 6d`, `Sector ⚠`, `Thesis valid`
5. **Detail panel** — action banner ilk sırada (exit/review kararı), altında agent notu, altında "Average down?" bölümü
6. **Daily Brief banner** — tab'ın en üstünde, gece hazırlanan özet

### Candidates tab

1. Fit badge — `Fits ✓` / `Doesn't fit ⚠`
2. Timing label — `Enter now` / `Wait · target $X`
3. Suggested amount — `€600`
4. Sıralama — good_fit + enter_now önce, no_fit altta gizli

### Yeni: Decision Tracker tab / panel
1. Hit rate kartları
2. Agent scorecard
3. Karar logu tablosu

---

## Değişmeyen Şeyler

- Mevcut kod pipeline (event_filter, scorer, decision_engine) — aynı kalıyor
- BIST pipeline — aynı kalıyor
- Mevcut sekmeler (Candidates, Sector Heatmap, Opportunities, Deep Dive) — kaldırılmıyor
- Firebase Hosting setup — değişmiyor
- My Radar formu temel yapısı — korunuyor
