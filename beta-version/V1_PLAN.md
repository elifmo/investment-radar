# Investment Radar — Beta V1 Plan (karar kilitli)

**Tarih:** 2026-07-20  
**Statü:** Karar kilidi + handoff  
**Canonical geliştirme planı (V1 + Full, faz faz):** [`DEVELOPMENT_PLAN.md`](./DEVELOPMENT_PLAN.md)  
**İlgili:** `SCENARIO3_MULTI_AGENT.md`, `CURSOR_IMPLEMENTATION_SPEC.md`, `agent_io_map.html`  
**Akış haritası:** `agent_io_map_v1.html`

> Uygulama sırası ve Full fazlar (5–10) için **DEVELOPMENT_PLAN.md** okunur. Bu dosya kararları özetler.

---

## Karar özeti

| Soru | Cevap |
|------|--------|
| Vizyon | Orijinal beta (kişiselleştirilmiş brief + aksiyon + full agent seti) |
| Nasıl ship? | **Beta katmanı** — mevcut pipeline/UI kalır; agent’lar Firestore’a yazar |
| V1 mi full mü? | **V1 çekirdek önce** → V2 full |
| Orchestrator | **Var** — düşünen editör (tek plan); TA’yı yeniden icat etmez |
| Öğrenme | Orchestrator + Decision Tracker döngüsü (ayrı “öğrenme projesi” değil) |
| Ultra slim | Reddedildi (çok birleşik) |
| 11 agent gün 1 | Reddedildi (V2’ye bırakılanlar var) |

---

## Problem

Mevcut sistem çok sinyal üretiyor (skor, rejim, sektör, adaylar) ama **tek net aksiyon planı** vermiyor.  
Beta V1: “Bugün ne yapayım?” cevabını `agents/daily_brief` ile verir; isabeti Tracker ile ölçer.

---

## Mimari ilkeler

1. Mevcut kod pipeline **değişmez** (event_filter, scorer, decision_engine).  
2. Agent’lar Firestore’a yazar; frontend okur.  
3. Alt agent’lar sinyal üretir (mümkün olduğunca kod + kısa Haiku not).  
4. **Orchestrator** birleştirir, çelişki çözer, önceliklendirir, geçmişten ders alır.  
5. Kararlar loglanır → outcome → sonraki brief’e hafıza.  
6. LLM skoru yeniden hesaplamaz.

---

## V1 kapsamı (çekirdek)

### Gece sırası

```
Pipeline (mevcut)
  → Macro Agent
  → Sector Agent
  → Earnings
  → Exit Agent
  → Candidates runner (Fit → Timing → Sizing)
  → Orchestrator → agents/daily_brief
  → Decision Logger (brief aksiyonlarını yaz)
  → Outcome Tracker (vadesi gelen kararları işle)
```

### Bileşenler

| # | Bileşen | Rol | Model |
|---|---------|-----|--------|
| 1 | Macro Agent | Rejim (kod: macro_regime + SPY/VIX) + haber context + 2 cümle | Kod + Haiku |
| 2 | Sector Agent | sector_status + sektör haber + özet | Kod + Haiku |
| 3 | Earnings | days_to_earnings ≤14 → risk tag | Kod + az Haiku |
| 4 | Exit Agent | holding → exit / review / ok | Kod karar + Haiku not |
| 5 | Candidates | fit → timing → sizing | Kod; reason Haiku (seyrek) |
| 6 | **Orchestrator** | Tek plan, çelişki, öncelik, reflection | **Sonnet** |
| 7 | Decision Logger + Tracker | log + outcome + UI hit-rate | Kod |

### Orchestrator davranışı

**Yapsın:** ranked actions (exit > review > enter > wait), çelişki notu, 2–4 cümle “bugünün planı”, son N decision_log + outcome’tan kısa ders.  
**Yapmasın:** teknik skoru sıfırdan üretmek, pipeline’ı yok saymak.

### Outcome pencereleri (başlangıç)

| Karar | Pencere | Not |
|-------|---------|-----|
| Exit | 7–14g | Mümkünse hold counterfactual |
| Enter now | 14–30g | Raw + alpha vs SPY tercih |
| Wait | 30g veya hedefe geliş | |

Varsayılan spec’teki 14g ile başlanabilir; tipe göre ayrıştırma V1.1.

### UI (V1)

- My Radar: Daily Brief banner + action pills (Exit now / Review / Hold)  
- Candidates: fit badge + timing + € + sıralama  
- Decision Tracker: özet kartlar + log tablosu (pending / correct / incorrect)  
- Tag’ler: Earnings · Sector ⚠  

### V1 dışı (vizyonda, V2)

- Averaging Down (ayrı agent / zengin UI)  
- Risk Summary (ayrı haftalık Sonnet)  
- Price Alert  
- Events Agent  
- Deep Dive bull/bear debate (on-demand)  
- Agent dosyalarını 11 ayrı “ürün agent”a bölmek (istersen, davranış oturunca)

---

## Beta olarak ship etmek

**Evet — beta katman. Ayrı link / ikinci site yok (V1).**

| Soru | Cevap |
|------|--------|
| Ek URL mi? | **Hayır** — aynı USA dashboard (`investment-radar-usa` / `frontend/usa`) |
| Ne değişir? | Aynı sayfada Beta brief, action pills, Tracker |
| Eski sistem? | Sekmeler kalır; brief yoksa placeholder |
| Kill switch | GHA `RUN_AGENTS` veya UI’da beta gizle |

| Neden beta? | Nasıl |
|-------------|--------|
| Mevcut dashboard kırılmaz | Agent yazıları ayrı `agents/` koleksiyonu |
| Güven kazanılana kadar | Brief “tavsiye”; Tracker görünür |
| Geri sarılabilir | Agent step kapat / Beta paneli gizle |
| Öğrenme zaman ister | İlk 14–30g Tracker boş olabilir — beklenen |

### Dil (zorunlu)

- **UI + agent çıktıları + brief: English only** (dashboard zaten EN).  
- Pill’ler net: `Exit now` / `Review` / `Hold` / `Enter now` / `Wait · target $X`.  
- Gerekçe detay panelinde, yine English. Karışık TR/EN yok.  
- Uygulama planı (EN): `DEVELOPMENT_PLAN.md`.

---

## Uygulama adımları

### Faz 0 — Altyapı (2–4 gün)
1. Firestore rules: `agents/**`, `decision_log` (veya `agents/decision_log`), gerekirse `alerts`  
2. GHA: pipeline sonrası agent job; `ANTHROPIC_API_KEY`  
3. Servis hesabının hedef `user_id` radar_items okuması  
4. Boş runner iskeleti: `src/agents/run_v1.py`

### Faz 1 — Shared (1 hafta)
5. `macro_agent.py` → `agents/macro_signal`  
6. `sector_agent.py` → `agents/sector_rotation`  
7. `earnings_preview.py` → `agents/earnings_preview/{ticker}`  
8. My Radar / Candidates’e Earnings + Sector tag (hafif UI)

### Faz 2 — Exit + Candidates (1–2 hafta)
9. `exit_signal_agent.py` → flag + not  
10. My Radar action pills + detail banner  
11. `run_candidates_agents.py`: fit → timing → sizing  
12. Candidates tab: fit / timing / € / sort / no_fit gizli

### Faz 3 — Orchestrator + öğrenme (1 hafta) ← kritik
13. `orchestrator_agent.py` → `agents/daily_brief` (Sonnet)  
14. Brief banner (My Radar üstü)  
15. `decision_logger.py` — brief aksiyonlarından log  
16. `outcome_tracker.py` — gecelik vade kontrolü  
17. Decision Tracker UI  
18. Orchestrator prompt’una son N log + outcome enjekte

### Faz 4 — Beta sertleştirme (3–5 gün)
19. Agent fail → pipeline’ı düşürme; brief yoksa placeholder  
20. Maliyet/log: her agent süre + token  
21. “Beta” etiketi + kısa kullanıcı notu (öğrenme için 14g+)

### V2 (sonra)
22. AvgDown · Risk · Price Alert · Events · Deep Dive debate  

---

## Maliyet (tek kullanıcı, kabaca)

- Tipik V1: **~$2.5–4 / ay** (Orchestrator Sonnet ana kalem)  
- Sıkı (candidate’da az LLM): **~$1.5–2.5**  
- Şişmiş: **~$5–8**

---

## Başarı kriterleri (V1)

1. Her işlem sabahı `daily_brief` dolu (veya açık hata/placeholder)  
2. Holding’lerde exit/review/hold pill’leri  
3. Candidates kişiselleştirilmiş sıralı  
4. Her exit/enter/wait logda  
5. 14g+ sonra outcome’lar dolmaya başlar  
6. Kullanıcı: brief’e bakmadan karar vermiyor (nitel başarı)

**Accuracy vaadi:** V1’de mucize yok. Hedef ölçülebilirlik; isabet Tracker + reflection ile artar.

---

## Bilinçli trade-off’lar

| Yaptık | Yapmadık |
|--------|----------|
| Orchestrator düşünsün | Her gece 11 agent |
| Tracker V1’de | Events/AvgDown gün 1 |
| Bootstrap kurallar + öğrenme hafızası | Saf kural yok / saf LLM trader |
| Beta paralel katman | Mevcut UI’yı silmek |

---

## Dosya haritası (hedef)

```
src/agents/
  macro_agent.py
  sector_agent.py
  earnings_preview.py
  exit_signal_agent.py
  portfolio_fit.py      # veya candidates/ altında
  entry_timing.py
  position_sizing.py
  orchestrator_agent.py
  run_shared.py
  run_radar.py
  run_candidates.py
  run_v1.py             # gece orkestrasyonu
src/tracking/
  decision_logger.py
  outcome_tracker.py
```

Detaylı Cursor prompt’ları için mevcut `CURSOR_IMPLEMENTATION_SPEC.md` kullanılabilir; kapsam çakışırsa **bu dosya (V1 Plan) önceliklidir**.

---

## Proje devamı / handoff (buradan yakıp devam)

> Bu bölüm, sohbeti bırakıp sonra geri dönünce **tek okuma** ile devam etmek içindir.  
> **Durum (2026-07-20):** Plan kilitli, kod yazılmadı. Sonraki iş = Faz 0.

### Şu an neredeyiz?

| Madde | Durum |
|-------|--------|
| Ürün vizyonu (Scenario 3 full) | Dokümanda hazır |
| V1 plan + Orchestrator + Tracker kararı | Kilitli |
| Beta = **aynı USA link** + Beta UI (ek site yok) | Kilitli |
| Dil: UI + agent **English only** | Kilitli — `DEVELOPMENT_PLAN.md` |
| `src/agents/` iskelet + `run_v1.py` stubs | **Başladı (Faz 0)** |
| Firestore `agents/` + `decision_log` rules | **Eklendi — deploy edilmeli** |
| GHA agent step (USA daily, soft-fail) | **Eklendi** |
| Secrets `ANTHROPIC_API_KEY` / `RADAR_USER_ID` | **Sen ekle** |
| Frontend brief / pills / tracker | **Yok** |

### Geri dönünce Cursor’a / kendine ilk prompt

```
beta-version/V1_PLAN.md dosyasını oku.
Karar kilitli: Beta V1 çekirdek (Macro, Sector, Earnings, Exit,
Candidates Fit→Timing→Sizing, Orchestrator, Decision Tracker).
Pipeline değişmez. Orchestrator düşünen editör (Sonnet).
Öğrenme = Logger + Outcome → sonraki brief hafızası.
V2 = AvgDown, Risk, Events, Price Alert, Deep Dive.

Şimdi Faz 0’dan başla: firestore.rules + GHA secret/slot +
src/agents/run_v1.py iskeleti. Kod yazmadan önce mevcut
firestore.rules ve .github/workflows/pipeline.yml’i oku.
```

### Devam checklist (sırayla işaretle)

- [ ] **Faz 0** Altyapı (rules, GHA, uid, `run_v1.py`)
- [ ] **Faz 1** Macro · Sector · Earnings + tag UI
- [ ] **Faz 2** Exit pills · Candidates kişiselleştirme
- [ ] **Faz 3** Orchestrator brief · Logger · Outcome · Tracker UI · hafıza
- [ ] **Faz 4** Fail-soft · Beta etiketi · maliyet log
- [ ] **V1 done** — 2–4 hafta brief kullan + Tracker dolsun
- [ ] **V2** AvgDown · Risk · Price Alert · Events · Deep Dive

### Doküman indeksi (ne okunur?)

| Dosya | Ne için |
|-------|---------|
| **`V1_PLAN.md`** (bu dosya) | **Üstün kaynak** — ne yapılacak, sıra, kararlar |
| `agent_io_map_v1.html` | V1 girdi/çıktı akışını görsel |
| `agent_io_map.html` | Full 11 agent hedef haritası (V2 vizyon) |
| `SCENARIO3_MULTI_AGENT.md` | Full vizyon detayı / schema |
| `CURSOR_IMPLEMENTATION_SPEC.md` | Cursor prompt’ları (V2 parçalar dahil; çakışmada V1_PLAN kazanır) |
| `agent_io_map_slim.html` | Eski “ultra slim” taslak — **uygulama yolu değil**, referans |
| `my_radar_action_first.html` | Action pill / detail panel UI mockup |
| `decision_tracker_scenarios.html` | Tracker UI fikirleri |
| `output_scenarios.html` | Çıktı senaryoları |

### Mevcut repo bağlamı (hatırlatma)

- Pipeline: `src/pipeline.py` → Firestore (`daily_candidates`, `macro_regime`, `sector_status`, …)
- Portföy: `radar_items` + `trade_entries` (Auth / `user_id`); sync: `scripts/sync_portfolio.py`
- Frontend: `frontend/usa/index.html` (Candidates, My Portfolio/Radar, …)
- Tek LLM prod: Cloud Function Deep Dive (Haiku) — agent katmanından ayrı
- Nightly: `.github/workflows/pipeline.yml` — agent’lar **bu bitince** eklenecek

### Bilinçli olarak yapma (tekrar sapma)

- Ultra slim’e geri dönme (Macro/Sector/Exit’i tek kutuya gömme)
- 11 agent’ı Faz 0’da aynı anda kurma
- Orchestrator’ı kaldırma veya “sadece sort”a indirme (karar: düşünsün)
- Tracker’ı V2’ye atma (güven için V1)
- TradingAgents’ı nightly stack yapma (Deep Dive = V2 on-demand)
- Outcome’u sadece “fiyat yukarı = doğru” ile ölçme → alpha / exit-vs-hold tercih

### V1 bittikten sonra (proje devamı — V2)

1. AvgDown (P&L < -10% detail panel)  
2. Risk weekly summary  
3. Price Alert (kod, market hours)  
4. Events Agent (RSS + keyword + nadir Haiku)  
5. Deep Dive bull/bear (on-demand)  
6. İsteğe: agent’ları full 11 isimli dosyaya böl / `agent_io_map.html` ile hizala  

V2’ye geçme koşulu: brief stabil + en az birkaç düzine `decision_log` + ilk outcome’lar görünür.

### Maliyet / başarı (kısa)

- Beklenen LLM: ~$2.5–4/ay (tek kullanıcı)  
- Başarı: sabah `daily_brief` + pills + log; accuracy mucizesi değil, ölçülebilirlik  
- İlk 14–30g Tracker’da çok `pending` normal  

### Son güncelleme

| Alan | Değer |
|------|--------|
| Tarih | 2026-07-20 |
| Karar | Beta V1 + Orchestrator + Tracker; aynı USA URL; English UI/agents |
| Kod | Faz 0 iskelet başladı (`src/agents/run_v1.py` stubs) |
| Sonraki iş | Secrets + rules deploy → **Phase 1 Macro Agent** |
| Plan (EN) | `DEVELOPMENT_PLAN.md` |
