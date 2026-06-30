# Cloudflare R2 + Edge Function Kurulumu (Faz 5)

Görsel baytları **Cloudflare R2**'de (S3-uyumlu, egress ücretsiz) saklanır.
İstemci R2 anahtarlarını asla görmez; bir **Supabase Edge Function** kısa ömürlü
presigned URL üretir. ~15 dakika.

> Akış: İstemci görseli sha256 ile hash'ler → Edge Function'dan presigned URL
> ister → görseli doğrudan R2'ye yükler/indirir → metadata `images` tablosuna yazılır.

---

## 1. Cloudflare R2 bucket oluştur

1. <https://dash.cloudflare.com> → kayıt ol / giriş yap (ücretsiz).
2. Sol menü → **R2**. İlk kez ise "Enable R2" / şartları kabul et.
   - ⚠️ Kart isteyebilir; ücretsiz katmanda (10 GB depo) ücret alınmaz.
3. **Create bucket**:
   - **Name:** `annotie`
   - **Location:** Automatic (veya EU)
   - **Create bucket**.

---

## 2. R2 API Token oluştur

1. R2 ana sayfası → sağ üst **Manage R2 API Tokens** (veya **API** → **Manage API Tokens**).
2. **Create API Token**:
   - **Permissions:** **Object Read & Write**
   - **Specify bucket:** sadece `annotie` (en güvenlisi)
   - **Create**.
3. Çıkan değerleri **kaydet** (bir daha gösterilmez):
   - **Access Key ID**
   - **Secret Access Key**
4. **Account ID**'yi de not et: R2 sayfasında veya endpoint'te görünür
   (`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`).

> Bu 4 değer (Account ID, Access Key ID, Secret Access Key, bucket adı)
> **sadece Supabase'e** girilecek; uygulamaya/koda **konmayacak**.

---

## 3. Edge Function secret'larını gir

1. Supabase paneli → **Project Settings** → **Edge Functions** → **Secrets**
   (veya **Edge Functions** → **Manage secrets**).
2. Şu 4 secret'ı ekle:

   | Name | Value |
   |------|-------|
   | `R2_ACCOUNT_ID` | Cloudflare Account ID |
   | `R2_ACCESS_KEY_ID` | R2 Access Key ID |
   | `R2_SECRET_ACCESS_KEY` | R2 Secret Access Key |
   | `R2_BUCKET` | `annotie` |

3. **Save**.

---

## 4. Edge Function'ı deploy et

**Yöntem A — Panelden (kolay, CLI gerektirmez):**

1. Supabase paneli → **Edge Functions** → **Create a new function** (veya **Deploy a new function** → **Via Editor**).
2. **Name:** `storage-presign`
3. Açılan editöre [`supabase/functions/storage-presign/index.ts`](../supabase/functions/storage-presign/index.ts)
   dosyasının **tüm içeriğini** yapıştır.
4. **Deploy**.

**Yöntem B — CLI ile (Supabase CLI kuruluysa):**

```bash
supabase functions deploy storage-presign --project-ref YOUR-PROJECT-REF
```

> `verify_jwt` varsayılan olarak **açık** kalmalı — fonksiyon yalnızca giriş yapmış
> kullanıcıları kabul eder.

---

## 5. Doğrulama

Uygulama tarafı kod hazır olduğunda (sonraki adım), şu test çalıştırılacak:

```bash
py -3.12 scripts/test_storage.py
```

Beklenen: hash → presign(put) → upload → metadata kaydı → presign(get) →
download → yerel cache doğrulaması (`[OK]`).

---

## Sorun giderme

| Belirti | Çözüm |
|--------|-------|
| `R2 secret eksik` (500) | 3. adımdaki 4 secret'ı kontrol et |
| `Yetkisiz` (401) | Giriş yapılmamış / token süresi dolmuş |
| `Yazma yetkiniz yok` (403) | Kullanıcı ekipte viewer; owner/admin/annotator olmalı |
| Upload 403 (R2) | API Token izni "Object Read & Write" ve doğru bucket mı? |
| `Görsele erişim yok` (403, get) | İlgili `images` kaydı yok veya kullanıcı ekip üyesi değil |
