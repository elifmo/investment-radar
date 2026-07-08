# Faz 0 — Firebase Authentication Kurulumu

Kod tarafı hazır. **Firebase Console'da bir kez** şunları açman gerekir:

1. [Firebase Console](https://console.firebase.google.com/project/investment-radar-2c19d/authentication/providers)
2. **Authentication → Sign-in method**
3. Etkinleştir:
   - **Google** (Authorized domain: `investment-radar-usa.web.app` zaten ekli olmalı)
   - **Email/Password** (isteğe bağlı; Google yeterli)
4. **Firestore rules deploy:**
   ```bash
   firebase deploy --only firestore:rules
   ```

## Test checklist

- [ ] Giriş yapmadan **My Radar** → "Sign in" mesajı, veri yok
- [ ] Google ile giriş → radar kaydı ekle
- [ ] Çıkış → liste boş / erişim yok
- [ ] Başka Google hesabı → birinci kullanıcının verisi görünmez

## Not

Eski `user_id: 1` kayıtları yeni kurallar altında **kimseye görünmez** (güvenlik için doğru).
Yeni kayıtlar `user_id = Firebase Auth uid` (string) kullanır.
