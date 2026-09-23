# Supabase Kurulum Rehberi (Faz 1)

Bu rehber, ekip/kullanıcı sisteminin backend'ini (kimlik + metadata) **ücretsiz**
Supabase projesi üzerinde ayağa kaldırır. ~10 dakika sürer.

> Hibrit mimari kararı gereği: **auth + metadata Supabase'de**, görsel baytları
> ileride R2/MinIO'da, canlı düzenleme mevcut FastAPI relay'inde. (bkz.
> [MIMARI_PLAN.md](MIMARI_PLAN.md))

---

## 1. Hesap ve proje oluştur

1. <https://supabase.com> → **Start your project** → GitHub veya e-posta ile kayıt ol (ücretsiz).
2. **New project**:
   - **Name:** `annotie` (veya istediğin ad)
   - **Database Password:** güçlü bir parola belirle ve **kaydet** (yönetim için lazım olur).
   - **Region:** sana en yakın bölge (örn. `Frankfurt (eu-central-1)`).
   - **Pricing Plan:** Free.
3. Proje hazırlanırken (~2 dk) bekle.

---

## 2. Şemayı (migrasyon) çalıştır

1. Sol menü → **SQL Editor** → **New query**.
2. `supabase/migrations/` klasöründeki SQL dosyalarını numara sırasıyla
   (`0001` → `0006`) aç ve her dosyanın **tüm içeriğini** ayrı bir
   sorgu olarak çalıştır. Daha önce kurulum yaptıysan yalnızca henüz
   uygulamadığın migration dosyalarından devam et.
3. Her dosyada **Run** (Ctrl/Cmd+Enter) sonrası "Success. No rows returned"
   görmelisin.
4. Sol menü → **Table Editor**'da şu tabloları görmelisin:
   `profiles, teams, memberships, invites, datasets, dataset_classes, images,
   annotations, annotation_events`.

`0005_annotation_operations.sql`, annotation nesnelerine sürüm/tombstone,
datasetlere collaboration sequence ve atomik operation RPC'si ekler.
`0006_collab_v2_migration.sql` ise legacy `label_content` snapshot'larının
uygulama tarafından güvenli ve tekrar çalıştırılabilir biçimde annotation
satırlarına taşınmasını sağlar. Bir ekip dataseti ilk kez açılırken taşıma
tamamlanır ve `collab_schema_version=2` olur. `label_content` silinmez; her
başarılı nesne işleminden sonra trigger tarafından YOLO uyumluluk snapshot'ı
olarak yeniden üretilir.

> Doğrulama: **Authentication > Policies** altında her tabloda RLS'in **Enabled**
> ve politikaların listelendiğini gör.

---

## 3. Geliştirme için e-posta onayını kapat

Geliştirme sırasında kayıt sonrası anında oturum almak için:

1. Sol menü → **Authentication > Providers > Email**.
2. **Confirm email** seçeneğini **kapat** → **Save**.

> Üretimde bunu tekrar **açmanız** önerilir (e-posta doğrulama güvenlik için).

---

## 4. Bağlantı bilgilerini al

1. Sol menü → **Project Settings > API**.
2. Şunları kopyala:
   - **Project URL** → `https://xxxx.supabase.co`
   - **Project API keys > anon / public** → uzun JWT benzeri anahtar.

> ⚠️ **service_role** anahtarını ASLA istemciye/koda koyma. Sadece **anon** key
> kullanılır; güvenlik RLS ile sağlanır.

---

## 5. Yerel yapılandırma

Proje kökünde `cloud_config.example.json` dosyasını `cloud_config.json` olarak
kopyala ve doldur (bu dosya `.gitignore`'da, commit edilmez):

```json
{
  "url": "https://xxxx.supabase.co",
  "anon_key": "ANON-KEY-BURAYA"
}
```

Alternatif: ortam değişkenleri `SUPABASE_URL` ve `SUPABASE_ANON_KEY`.

---

## 6. Bağımlılıkları kur ve doğrula

```bash
pip install -r requirements.txt          # supabase paketini de kurar
python scripts/test_cloud_auth.py
```

Beklenen çıktı: yapılandırma → kayıt → profil oluşumu → çıkış → giriş →
RLS kontrolü adımlarının tümünde `[OK]`.

`[UYARI] ... Confirm email açık olabilir` görürsen → 3. adımı uygula.

---

## Sorun giderme

| Belirti | Çözüm |
|--------|-------|
| `supabase paketi kurulu degil` | `pip install supabase` |
| `Yapilandirma yok` | `cloud_config.json` oluştur (5. adım) |
| Kayıt sonrası oturum yok | Confirm email kapat (3. adım) |
| `permission denied for table` | Migrasyon tam çalışmadı; 2. adımı tekrarla |
| Profil oluşmuyor | `on_auth_user_created` tetikleyicisi yok; 0001_init.sql'i tekrar çalıştır |
