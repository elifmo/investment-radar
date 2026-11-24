# Investment Radar — Uzun Vadeli Yapılacaklar Planı

> Cursor'a yüklemek ve gözden geçirmek için. Bu bir yol haritasıdır — hepsini
> birden yapma. Her faz bittiğinde elinde çalışan bir şey olsun diye sıralı.
>
> **Temel ilke:** Sistem al/sat demez. Kararı kullanıcının yerine vermez —
> tezini yazdırır, riskini gösterir, exit adayı sunar, kaçışı fark ettirir.

> Bu dosya iç yol haritasıdır; ürün özeti için `README.md`.

**Son güncelleme:** Temmuz 2026 (UI notları Kasım 2026’da README’de)

---

## Zaten canlıda olanlar (bu planın önüne geçti)

| Özellik | Durum | Doküman |
|---------|-------|---------|
| Pipeline + Firestore | ✅ | `CLAUDE_EN.md` |
| Decision engine (BUY/WATCH/SKIP) | ✅ | `src/decision_engine.py` |
| Sector heatmap + ETF scan | ✅ | 23:15 TR cron |
| Oversold Watch (Stoch + RSI) | ✅ | `oversold_watch` koleksiyonu |
| USA evren genişletmesi (523) | ✅ | S&P 500 + Nasdaq-100 + 7 ekstra |
| My Radar + Firebase Auth | ✅ | `firestore.rules` |
| Oversold / Fib radar | ✅ | `fib_ema_radar` |
| Opportunities sekmesi | kodda var, USA’da gizli | `DASHBOARD_DESIGN_EN.md` |
| Deep Dive | ✅ | Cloud Function |

**Mimari referans:** `CLAUDE_EN.md` ve `README_DOCUMENTATION.md`

---

## Bağlam: gerçek sorun ne

Sistem "hisse tarama" derdiyle kuruldu ama asıl sorun teknikti değil:

1. **Konsantrasyon** — portföydeki hisseler aynı türden (spekülatif,
   yüksek-beta). Hepsi aynı anda düşüyor çünkü aynı riske bağlı.
2. **Tezsiz giriş** — olayla/haberle giriliyor ("yatırım aldı diye aldım"),
   tezle değil. Olay geçince satış kararı panik anına kalıyor.
3. **Kaçış eğilimi** — düşen pozisyona bakmak acı verince yeni parlak
   hisselere yöneliş; çeşitlendirme mi kaçış mı belirsiz.

Üçü de karar disiplini sorunu, tarama değil.

## Kritik kısıt: sistem SADECE FİYAT okuyor

yfinance'ten fiyat çekiliyor; web'e çıkıp haber okuyamıyor. Bu yüzden:
- Gerçek sorunları çözen her şey → sadece fiyatla yapılır → ucuz, hazır.
- Haber/gündem özelliği → yeni altyapı ister → pahalı → en sona.

---

## GÜVENLİK SINIRLARI (önce oku — planı bunlar şekillendirir)

İşlem defteri = gerçek para verisi. Herkese açık olamaz. Ama:

- **Login sistemini SIFIRDAN yazma.** Şifre saklama / oturum yönetimini
  elle yazmak güvenlik açığı kaynağıdır. Bunun yerine Firebase'in hazır
  kimlik doğrulama servisini (Firebase Authentication) KULLAN — mail /
  Google girişini oradan aç.
- **Erişim izinlerini / paylaşım ayarlarını dikkatle sen yapılandır.**
  Firestore security rules: "veriyi sadece onu oluşturan giriş yapmış
  kullanıcı okur/yazar." Yanlış kurulursa ya herkese açılır ya seni
  kilitler. Firebase'in kendi arayüzünden, ne yaptığını görerek yap.
- Kaynak: Firebase Auth + Firestore Security Rules resmi dokümanı.

İş bölümü: veri yapısı + hesaplama mantığı planlanabilir; ama Auth kurulumu
ve izin yapılandırması senin elinden, resmi dokümana bakarak yapılmalı.

---

## FAZLAR

```
Faz 0  Firebase Auth + erişim kuralları (login)      GÜVENLİK ÖNCE
Faz 1  tez+exit+exit önerisi, durumlar, işlem defteri, risk mix   FİYAT
Faz 2  bilanço takvimi, rotasyon (göreceli güç)                  FİYAT
─────────────────────────────────────────────────  (haber duvarı)
Faz 3  haber katmanı → gündem/keşfet                             YENİ MALİYET
Faz 4  iki karne: kararların + önerilerin                        (veri Faz 1'den)
```

Faz 2 ↔ 3 arası gerçek ayrım: üstü elindekiyle yapılır, acıtanı çözer;
altı yeni altyapı ister, gürültü riski taşır.

---

### FAZ 0 — Güvenli giriş (login) — İLK İŞ

- [x] Firebase Authentication (Google + email) — frontend kodu
- [x] Firestore security rules: veri sahibe bağlı (`user_id == auth.uid`)
- [ ] Firebase Console'da Google/Email provider'ı aç (bkz. `docs/FAZ0_AUTH_SETUP.md`)
- [ ] Test: çıkış yapınca hiçbir kişisel veri görünmemeli
- [ ] Test: başka kullanıcı senin verini çekemez

> Bu faz bitmeden işlem defteri (gerçek para verisi) EKLENMEZ.

---

### FAZ 1 — Çekirdek (sadece fiyat)

#### 1a · Tez + Exit zorunlu form
- [ ] Hisse eklerken Thesis + Exit ZORUNLU alan (boş geçilemez)
- [ ] Tez "olay" gibiyse uyar: "bu olay geçince tutma sebebin ne?"
- [ ] Durum seçimi: Holding (sahibim) / Watching (izliyorum)

#### 1b · Exit yönlendirmesi (fiyat verisinden aday seviyeler)
- [ ] Destek/direnç seviyesi hesapla (fiyatın döndüğü yerler)
- [ ] ATR bazlı tampon hesapla (normal oynaklık payı)
- [ ] 200-gün hareketli ortalama
- [ ] Formda aday olarak sun; kullanıcı seçer ya da kendi yazar
- [ ] Hatırlatma metni: "Bu seviye kırılırsa sadece grafik mi bozulur,
      yoksa aldığın sebep de mi ortadan kalkar?"

> ÜÇ UYARI (koda yorum olarak da yaz):
> 1. Destek/direnç kesin değil, bölge — kırılabilir.
> 2. Herkes aynı seviyeyi görür → stop-run tuzağı → tampon bırak.
> 3. Teknik seviye tezin yerine geçmez → ikisini birleştir.

#### 1c · İşlem defteri (lot + tarih + ekleme/çıkış)
- [ ] Her hisse = işlem LİSTESİ (durum değil): tarih, lot, fiyat, AL/SAT
- [ ] Ekleme (ek alım) ve partial (kısmi satış) desteği
- [ ] Otomatik hesap: kalan lot, ortalama maliyet, kâr/zarar
- [ ] Veri kullanıcıya bağlı (Faz 0 auth ile ilişkili)

#### 1d · Radar/Portföy = tek liste, üç durum
- [ ] İzliyorum → Sahibim → Çıktım (tek liste, durumlar)
- [ ] İzlenende giriş hedefine mesafe; sahipte exit'e mesafe izlenir
- [ ] Geçişte tez taşınır; "aldım"da exit eklenir; arşiv silinmez

#### 1e · Risk dağılımı çubuğu
- [ ] Her holding'e tür etiketi: spekülatif / istikrarlı / savunmacı
- [ ] Konsantrasyon çubuğu (sadece SAHİP olduklarını sayar)
- [ ] Yeni alım bu dengeyi bozuyor mu / düzeltiyor mu göster

#### 1f · Sinyal + öneri kaydını SESSİZCE başlat
- [ ] Her sinyal/öneriyi tabloya yaz (ekran yok, sadece log)
- [ ] Sistem bir hisse ÖNERDİĞİNDE de kaydet (sen almasan bile) → Faz 4 için
- [ ] Bugün başlatmazsan Faz 4'te elin boş kalır

---

### FAZ 2 — Takvim + rotasyon (hâlâ sadece fiyat)

- [ ] Bilanço/olay takvimi (yfinance zaten sonraki bilanço tarihini verir)
- [ ] Temettü tarihleri
- [ ] "Yaklaşan sınav" etiketi (INTC → 23 Tem gibi)
- [ ] Göreceli güç: her hisse endekse (SPX) göre skorlanır
- [ ] Sektör breadth / rotasyon → "para nereye akıyor"

> Doğal durma noktası. Gerçek ihtiyaçların çoğu burada karşılanır.
> Faz 3'e geçmeden önce Faz 1-2'yi bir süre KULLAN, gerçekten lazım mı gör.

---

### FAZ 3 — Haber katmanı (büyük, pahalı, kırılgan)

Önce altyapı:
- [ ] Haber çekme yolu: finans haber API'si YA DA agent'e web arama
- [ ] KAYNAK BEYAZ LİSTESİ: sadece büyük ajans/resmi/ciddi finans;
      forum/blog/sosyal/reklam DIŞLA (asıl zor kısım bu filtreleme)
- [ ] Depolama + tekrar önleme (aynı haber tekrar tetiklemesin)

Sonra gündem bloğu (ana panelde, boşken görünmez):
- [ ] (a) İlgili akış — düşük eşik, senin hisselerin/sektörlerin
- [ ] (b) Keşfet — yüksek eşik, seyrek, evreninde olmayan sektörler
- [ ] "Bu temayı gösterme" ile susturulabilir
- [ ] Her öğede kaynak + link ZORUNLU
- [ ] Dil: "etkileyebilir / yön garantisi değil"; ASLA "al" deme

> Neden en sonda: güvenilir kaynak OLAYI doğrular, PİYASA TEPKİSİNİ değil.
> Agent kaynağı doğru okusa bile yorumlarken halüsinasyon yapabilir.
> Bu yüzden kaynak hep gösterilir; karar kullanıcıda.
> "4 saatte bir rapor" DEĞİL → gündem değişince tetiklenir (uyarı yorgunluğu).

---

### FAZ 4 — İki ayrı karne (veri Faz 1'den birikir)

Küçük iş ama aylarca veri ister. İki karne AYRI tutulur çünkü ayrı şeyleri
ölçerler:

#### Karne A — SENİN kararların (aldıkların)
- [ ] Tez türüne göre başarı: olay-teziyle mi kalıcı-tezle mi girdiklerin
      daha iyi/kötü sonuçlandı? ← en değerli davranış metriği
- [ ] Exit disiplini: exit'e sadık kaldıkların mı, kaydırdıkların mı?
- [ ] Ortalama kazanç vs ortalama kayıp (oran tek başına yanıltıcı)
- [ ] Konsantrasyon zamanla: spekülatif oran arttı mı azaldı mı?
- [ ] En pahalı hata türü (arşivden): panik satış / exitsiz giriş / vs.

#### Karne B — SİSTEMİN önerileri (aldın-almadın fark etmez)
- [ ] Sistem önerdiği ANDA kaydet; sonra 1/3/5/10 günde ne oldu izle
- [ ] Öneriler ortalama %kaç tuttu, medyan kaç günde çıktı
- [ ] Öneri tipine göre kırılım
- [ ] Amaç: "seçici hafıza" tuzağını önlemek — sistem tutmayan
      önerilerini de sayar, kendi gerçek isabetini görür

> DÜRÜSTLÜK NOTU: Karne B bazen "bu öneriler iyi değil" diyecek. Bu İYİ bir
> şey — o mesajı duyman, güzel rakamlar görmekten değerlidir. Öneri kutusuna
> gereğinden fazla güvenmeni engeller.
>
> Her iki karne de aylarca veri + yeterli örneklem ister. Küçük örneklem
> (20-25) istatistiksel olarak zayıf → "kaba eğilim" oku, "gerçek" değil.

---

## REVIEW / KENDİNE SORULACAKLAR

Bu planı gözden geçirirken kendine sor:

- [ ] Faz 0 (güvenlik) gerçekten ilk mi? İşlem defterini ondan önce
      eklemedim değil mi?
- [ ] Login'i sıfırdan yazmaya kalkışıyor muyum? (Yapma — Firebase Auth kullan)
- [ ] Her fazı bitirmeden bir sonrakine atlıyor muyum?
- [ ] Faz 3'ü (haber), Faz 1-2'yi kullanmadan kurmaya çalışıyor muyum?
      (En pahalı/kırılgan parça — önce çekirdek otursun)
- [ ] Sinyal/öneri kaydını Faz 1'de başlattım mı? (Yoksa Faz 4 boş kalır)
- [ ] Sistem hiçbir yerde "al/sat" diyor mu? (Dememeli)
- [ ] Özellik eklemek, üç gerçek pozisyona karar vermekten kaçış mı oldu?

---

## EN ÖNEMLİ HATIRLATMA

Bu konuşma boyunca sisteme sürekli özellik eklendi — her biri mantıklı.
Ama toplamı büyük bir sistem. Özellik eklemek keyifli çünkü karar vermek zor;
sistem kurmak, karar vermekten kaçışın bir biçimi olabilir.

Çekirdeğin %80'i sadece Faz 1'den (tez+exit+risk+işlem defteri) ibaret olsa,
sorunlarının çoğu çözülür. Gerisi güzel eklenti — olmazsa olmaz değil.

Ve hiçbir katman senin yerine karar vermez. Bugünkü üç hisse senin kararın.
(Not: yatırım tavsiyesi değildir; tüm kararlar ve sorumluluk kullanıcıya aittir.)
