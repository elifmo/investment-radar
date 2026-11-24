# Faz 0 — Firebase Authentication Kurulumu

Operatör notu (bu Firebase projesi). Fork’luyorsan kendi proje ID ve OAuth client’ını kullan.

Kod tarafı hazır. **Firebase / Google Cloud Console'da** şunlar olmalı:

## 1) Firebase Authentication

1. [Firebase Console → Authentication](https://console.firebase.google.com/project/investment-radar-2c19d/authentication/providers)
2. **Sign-in method** → etkinleştir:
   - **Google**
   - **Email/Password** (opsiyonel; şu an kapalıysa email ile giriş `OPERATION_NOT_ALLOWED` verir)
3. **Settings → Authorized domains** içinde olmalı:
   - `investment-radar-usa.web.app`
   - `localhost`
   - `investment-radar-2c19d.firebaseapp.com`

## 2) Google OAuth JavaScript origin (ZORUNLU — Google girişinin asıl kırılma noktası)

Modern tarayıcılar third-party cookie engellediği için app artık **Google Identity Services** kullanıyor.
Bunun çalışması için OAuth Web Client’ta site origin’i tanımlı olmalı.

1. Google Cloud Console → APIs & Services → Credentials → **OAuth 2.0 Client ID** (Web client for this Firebase project)
2. **Authorized JavaScript origins** → **ADD URI**:
   ```
   https://investment-radar-usa.web.app
   ```
3. (İsteğe bağlı, eski popup/redirect için) **Authorized redirect URIs** → **ADD URI**:
   ```
   https://investment-radar-usa.web.app/__/auth/handler
   https://investment-radar-2c19d.firebaseapp.com/__/auth/handler
   ```
4. **Save** → 1–2 dk bekle → dashboard’ı hard refresh et

### Teşhis notu (2026-07-20)

Canlıda Google Identity şu hatayı verdi:

`[GSI_LOGGER]: The given origin is not allowed for the given client ID.`

Yani Firebase Auth / Google provider açık; eksik olan **OAuth client JS origin**.

## Test checklist

- [ ] Giriş yapmadan **My Portfolio** → "Sign in" mesajı
- [ ] Google ile giriş → radar kaydı ekle
- [ ] Çıkış → liste boş / erişim yok
- [ ] Başka Google hesabı → birinci kullanıcının verisi görünmez

## Not

Eski `user_id: 1` kayıtları yeni kurallar altında **kimseye görünmez**.
Yeni kayıtlar `user_id = Firebase Auth uid` (string) kullanır.
Hesap örneği: `cemelifozkan@gmail.com` → uid `CLZuU9TPRGaKwrmUcwd8MgafmNv2`.
