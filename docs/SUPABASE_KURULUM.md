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
   (`0001` → `0008`) aç ve her dosyanın **tüm içeriğini** ayrı bir
   sorgu olarak çalıştır. Daha önce kurulum yaptıysan yalnızca henüz
   uygulamadığın migration dosyalarından devam et.
3. Her dosyada **Run** (Ctrl/Cmd+Enter) sonrası "Success. No rows returned"
   görmelisin.
4. Sol menü → **Table Editor**'da şu tabloları görmelisin:
   `profiles, teams, memberships, invites, datasets, dataset_classes, images,
   annotations, annotation_events, user_models, legacy_blob_grants`.

`0005_annotation_operations.sql`, annotation nesnelerine sürüm/tombstone,
datasetlere collaboration sequence ve atomik operation RPC'si ekler.
`0006_collab_v2_migration.sql` ise legacy `label_content` snapshot'larının
uygulama tarafından güvenli ve tekrar çalıştırılabilir biçimde annotation
satırlarına taşınmasını sağlar. Bir ekip dataseti ilk kez açılırken taşıma
tamamlanır ve `collab_schema_version=2` olur. `label_content` silinmez; her
başarılı nesne işleminden sonra trigger tarafından YOLO uyumluluk snapshot'ı
olarak yeniden üretilir.

`0008_security_hardening.sql` güvenlik sertleştirmesidir ve tekrar
çalıştırılabilir:

- **Roller:** admin yalnızca annotator/viewer atayabilir/davet edebilir; owner
  rolü doğrudan atanamaz, ekip sahibi (`owner_id`) değiştirilemez, owner
  ekipten çıkarılamaz.
- **Davetler:** davet kodları yalnızca owner/admin ve davet edilen kişiye
  görünür. Kullanıcı adıyla gönderilen davet yalnızca o hesapla, e-postayla
  gönderilen davet yalnızca o e-postanın hesabıyla kabul edilebilir.
- **Kontrol kolonları:** `collaboration_sequence`, `collab_schema_version`,
  `annotations_migrated_at` istemciden değiştirilemez (yalnızca RPC'ler yazar);
  migrasyon RPC'si mevcut annotation satırlarını hiçbir durumda silmez.
- **Dosya adları:** `images.filename` tek ve güvenli bir dosya adı olmalı
  (`/ \ : * ? " < > |`, kontrol karakteri, `..` yok). Kısıt `NOT VALID`
  eklendiği için mevcut satırları taramaz; yeni ve güncellenen satırlarda
  zorlanır.
- **Görsel depolama:** `legacy_blob_grants` tablosu, 0008 anındaki görsellerin
  hangi ekibe ait olduğunu bir kez kaydeder. `storage-presign` eski
  `blobs/<hash>` nesnelerini yalnızca bu kayıtla imzalar; yeni yüklemeler
  `teams/<team_id>/blobs/<hash>` altına gider.
- **Relay:** `my_dataset_role` RPC'si, relay'in odaya katılan kullanıcının
  rolünü (viewer düzenleme yayınlayamaz) öğrenmesi içindir.

> **Deploy sırası (0008):** önce bu migrasyon → `storage-presign` yeniden
> deploy ([R2_KURULUM.md](R2_KURULUM.md)) → tüm ekip üyeleri yeni uygulama
> sürümüne geçer → relay güncellenir ([RELAY_DEPLOY.md](RELAY_DEPLOY.md)).
> Yeni presign, görsel indirirken `dataset_id` ister; **eski uygulama
> sürümleri bu adımdan sonra ekip görsellerini indiremez.**

> Doğrulama: **Authentication > Policies** altında her tabloda RLS'in **Enabled**
> ve politikaların listelendiğini gör.

---

## 3. Geliştirme için e-posta onayını kapat

Geliştirme sırasında kayıt sonrası anında oturum almak için:

1. Sol menü → **Authentication > Providers > Email**.
2. **Confirm email** seçeneğini **kapat** → **Save**.

> Üretimde bunu tekrar **açmanız** önerilir (e-posta doğrulama güvenlik için).
> Onay kapalıyken herkes başkasının e-postasıyla kayıt olabilir; bu durumda
> e-postayla gönderilen davetlerin "yalnızca o e-postanın sahibi kabul eder"
> kontrolü (0008) koruma sağlamaz.

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
