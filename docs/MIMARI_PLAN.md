# Annotie — Ekip Yönetimi & Kullanıcı Sistemi Mimari Planı

> Durum: **Tasarım / Mutabakat aşaması.** Bu doküman üzerinde anlaşılmadan kod yazılmayacak.
> Hazırlayan: mimari analiz — 2026-06-28

---

## 1. Mevcut Sistemin Analizi

### 1.1 Bugünkü mimari
- **İstemci:** PySide6 masaüstü uygulaması (YOLO formatı: bbox, obb, polygon, keypoint, classify).
- **Yerel mod:** Kullanıcı diskindeki bir klasörü seçer. Etiketler görsellerin yanında `labels/*.txt` olarak tutulur. Doğruluk kaynağı = kullanıcının diski.
- **İşbirliği:** `server/` altında FastAPI + WebSocket **relay**.
  - Host bir lobi açar → 6 karakterlik kod → diğerleri kodla katılır.
  - `manifest` = sadece görsel `stem` listesi + sınıflar + task_type. **Görsel baytları ve mevcut anotasyonlar paylaşılmaz.**
  - Anotasyon işlemleri (`ann_create/delete/modify/class_change`, `class_*`) eşler arası relay edilir.
  - Sunucu **tamamen bellek-içi**: veritabanı yok, dosya depolama yok, kalıcılık yok. Lobi kapanınca her şey uçar.

### 1.2 Kök problem
Sistemde **ortak bir doğruluk kaynağı yok**:
1. Görseller her makinede yerelde durur; relay yalnızca dosya adı paylaşır → herkeste aynı dosyalar olduğu *varsayılır*. Olmayınca kopyalar ayrışır.
2. Anotasyonlar kalıcı kaydedilmez; sadece lobi açıkken canlı yayınlanır. Çökme/çıkış = senkronize olmamış değişiklikler kaybolur.
3. Kimlik, ekip, yetki kavramı yok.

Yeni sistemin temeli: **merkezi, kalıcı bir doğruluk kaynağı** (metadata için DB + görseller için nesne deposu) + kimlik/ekip/yetki + sağlam senkronizasyon.

---

## 2. Temel Tasarım İlkesi: Metadata ile Blob'u Ayır

En kritik içgörü ve maliyet anahtarı: **anotasyonlar küçük, görseller büyük.** İkisini farklı yönet.

| Veri | Boyut | Nerede |
|------|-------|--------|
| Kullanıcı, ekip, üyelik, davet, dataset metadata, görsel kaydı (ad+hash+anahtar), anotasyonlar | KB seviyesi, yapısal | **İlişkisel DB (Postgres)** |
| Görsel baytları | MB–GB | **Nesne deposu (S3-uyumlu)** |

### 2.1 İçerik-adresli görseller (content-addressed) — maliyetin ve tutarlılığın anahtarı
- Her görsel **içerik hash'i (sha256)** ile kimliklenir. Depo anahtarı = hash. → Otomatik **deduplikasyon** (aynı görsel iki kez yüklenmez).
- Bugünkü `stem` (dosya adı) kimliği sorunlu: iki farklı `img1.jpg` çakışır. Hash bunu çözer.
- Dataset = sıralı `{filename, hash, split}` listesi.
- İstemci dataset açınca **manifest'i (metadata)** çeker — ucuz. Görseller **talep üzerine (lazy)** indirilir ve hash ile yerelde cache'lenir. Değişmeyen görsel bir daha indirilmez. → "Büyük dataset + depolama maliyeti" problemi böyle çözülür: kimse tüm dataseti indirmez, sadece açtığını çeker.

---

## 3. Mimari Alternatifler

### Alternatif A — Supabase merkezli (BaaS): en az çaba
- **Supabase Auth**: kayıt/giriş/JWT/e-posta daveti hazır gelir.
- **Supabase Postgres**: teams, memberships, invites, datasets, image metadata, annotations. **Row Level Security (RLS)** ile "yalnızca ekip üyesi ekip datasetini görür" DB seviyesinde zorlanır.
- **Blob:** Cloudflare R2 veya Supabase Storage.
- **Realtime:** Supabase Realtime (Postgres değişiklik akışı) canlı senkronu sağlayabilir.
- **+** En sensitif kısım (auth/davet) hazır; çok az backend kodu; yönetilen ölçek.
- **−** Vendor lock-in; ücretsiz katman limitleri (DB 500MB, atalette uyku); az kontrol; mevcut FastAPI/WebSocket yatırımı atıl kalır.

### Alternatif B — Kendi sunucunda FastAPI + Postgres + MinIO: en çok kontrol
- Mevcut FastAPI sunucusu genişletilir: Postgres (SQLAlchemy), JWT auth (fastapi-users), ekip/davet endpoint'leri, dataset CRUD, MinIO'ya presigned upload.
- **Blob:** aynı VPS'te MinIO (ya da egress'i sıfırlamak için R2).
- WebSocket relay korunur; işlemler DB'ye yazılır (write-through).
- **+** Mevcut Python/FastAPI yatırımını yeniden kullanır; lock-in yok; tek ucuz VPS'te (~5€/ay Hetzner) çalışır; maliyet öngörülebilir.
- **−** Auth, davet, e-posta, yedekleme, ölçek hepsi sizin sorumluluğunuzda; operasyon yükü.

### Alternatif C — Hibrit **(ÖNERİLEN)**
- **Kimlik + metadata → Supabase**: en zor ve güvenlik-kritik kısımları (auth/teams/invites/RLS) devret.
- **Blob → Cloudflare R2** (veya kendi sunucunda MinIO): görsel depolama maliyetini kontrol et (egress ücretsiz).
- **Canlı düzenleme → mevcut FastAPI WebSocket relay**'i koru, ama **write-through** ile Supabase'e yaz → kalıcı doğruluk kaynağı.
- En iyi denge: auth'ta düşük çaba, depolamada düşük maliyet, mevcut realtime kodunun yeniden kullanımı.

---

## 4. Depolama Servisleri Karşılaştırması (maliyet odaklı)

| Servis | Ücretsiz katman | Egress (indirme) | Not |
|--------|-----------------|------------------|-----|
| **Cloudflare R2** | 10 GB/ay depo | **Ücretsiz** | Görsel-yoğun, çok indirilen senaryoda en iyi. Önerilen blob deposu. |
| **Backblaze B2** | 10 GB | İlk 3×depo ücretsiz (CDN ile) | Ucuz ($6/TB/ay). |
| **Supabase Storage** | 1 GB | Sınırlı | Postgres'e entegre, kolay; küçük free tier. |
| **Self-hosted MinIO** | VPS maliyeti | Sıfır marjinal | Kendi sunucun varsa en iyi; tam kontrol. |
| **AWS S3** | — | Pahalı egress | Maliyet için kaçın. |

**Metadata DB:** Supabase Postgres (free 500MB + Auth + RLS + Realtime) veya kendi VPS'inde Postgres. SQLite yalnızca masaüstü yerel cache için uygun, çok-kullanıcılı sunucu için değil.

---

## 5. Senkronizasyon Mekanizması

1. **Görseller:** içerik-adresli + lazy indirme + hash bazlı yerel cache. Görseller **doğrudan istemci ↔ depo** (presigned URL) aktarılır; **asla uygulama sunucusu üzerinden proxy edilmez** (bant genişliği/bellek patlar).
2. **Anotasyonlar:** küçük, eager senkron. Dataset başına monotonik `seq` ile versiyonlanır (zaten var). Açılışta tüm güncel anotasyonlar çekilir; canlı düzenleme WebSocket ile; tetikli/periyodik DB'ye persist.
3. **Çevrimdışı:** masaüstü uygulaması offline çalışmalı; işlemler kuyruğa alınır, yeniden bağlanınca replay edilir.
4. **Çakışma:** başlangıçta anotasyon `uid` başına last-write-wins (mevcut relay ile uyumlu). Sonra versiyon numarası ile optimistic locking / görsel-bazlı kilit (presence zaten kimin hangi görselde olduğunu gösteriyor).

---

## 6. Önerilen Veritabanı Şeması (taslak)

```
users        (id, email, username, password_hash/auth_provider, created_at)
teams        (id, name, owner_id, created_at)
memberships  (id, team_id, user_id, role[owner|admin|annotator|viewer], created_at)
invites      (id, team_id, email/username, token, status[pending|accepted|expired],
              invited_by, expires_at, created_at)
datasets     (id, team_id, name, task_type, kpt_shape, created_by, created_at)
images       (id, dataset_id, filename, content_hash, storage_key, width, height,
              split[train|val|test], size_bytes, created_at)
annotations  (id, image_id, uid, class_id, type, data_json, version,
              updated_by, updated_at)         # ya da görsel başına tek .txt blob
classes      (id, dataset_id, class_index, name, color)
```

Yetki: ekip rolleri (owner/admin/annotator/viewer) + dataset bazlı erişim. RLS veya servis katmanı kontrolü.

---

## 7. Eksikler / İleride Problem Olabilecek Noktalar

1. **Bugün doğruluk kaynağı yok** → tüm tasarımın temeli (madde 2 ile çözülür).
2. **Görsel kimliği** `stem` ile yapılıyor → hash bazlı kimliğe geçilmeli (çakışma riski).
3. **Anotasyonlar sunucuda kalıcı değil** → write-through persist + offline kuyruk şart.
4. **Sır yönetimi:** masaüstü istemcisine **asla** servis anahtarı gömülmemeli → kullanıcı başına JWT + presigned URL + RLS. (Güvenlik açısından kritik.)
5. **Eşzamanlı düzenleme çakışmaları** → sadece relay yetmez, versiyonlama gerekli.
6. **Çevrimdışı düzenleme** → kuyruk/replay olmadan ekip modu kötü ağda kırılgan.
7. **Büyük görsel upload/download** → daima doğrudan istemci↔depo (presigned).
8. **Depolama büyümesi** → hash dedup, opsiyonel küçük resim (thumbnail), soğuk datasetler için lifecycle/arşiv. Egress sessiz katil → R2/B2.
9. **Yetki granülerliği** → ekip rolleri + dataset bazlı erişim.
10. **Göç (migration)** → mevcut yerel datasetleri "ekibe yükle" yolu.
11. **Yedekleme** → DB + depo yedek stratejisi.
12. **Davet güvenliği** → token'lı, süresi dolan davet linkleri; e-posta doğrulama.

---

## 8. Fazlara Bölünmüş Geliştirme Planı (küçük, yönetilebilir adımlar)

- **Faz 0 — Mutabakat (bu konuşma):** Stack seçimi (A/B/C), şema onayı. *Kod yok.*
- **Faz 1 — Backend temeli:** DB şeması + auth (kayıt/giriş/JWT). UI yok, API ile test.
- **Faz 2 — Masaüstü kimlik:** Opsiyonel giriş ekranı; "Atla / Yerel mod" korunur. Token saklama.
- **Faz 3 — Ekip yönetimi:** Ekip oluştur, ekiplerimi listele, kullanıcı/e-posta ile davet, daveti kabul. Ekip listesi ekranı.
- **Faz 4 — Dataset kaydı:** Ekip dataseti oluştur/listele; metadata DB'de. Açılışta **mod seçici** ekran (Bireysel / Ekip).
- **Faz 5 — Görsel depolama:** Presigned upload/download, içerik-hash adresleme, yerel cache, lazy fetch. Mevcut yerel dataseti ekibe yükleme.
- **Faz 6 — Anotasyon kalıcılığı:** Açılışta anotasyonları çek, düzenlemede write-through, offline kuyruk.
- **Faz 7 — Canlı işbirliği entegrasyonu:** Mevcut WebSocket relay'i kimlik doğrulamalı oturum + kalıcılığa bağla; dataset bazlı presence.
- **Faz 8 — Yetki/rol, cila, yedekleme, deployment.**

---

## 9. Önerilen Düşük Maliyetli Başlangıç Yığını (öneri)

- **Auth + metadata:** Supabase (free tier).
- **Blob:** Cloudflare R2 (10 GB free, egress yok) *veya* kendi VPS'inde MinIO.
- **Canlı düzenleme:** mevcut FastAPI WebSocket relay (write-through ile).
- **Deployment:** tek küçük VPS (Hetzner/Fly.io) + yönetilen Supabase. Aylık maliyet başlangıçta ~0–5€.

## 10. Verilen Kararlar (mutabakat)

- **Stack:** Alternatif **C — Hibrit.** Auth/ekip/davet → Supabase; canlı düzenleme → mevcut FastAPI WebSocket relay (write-through ile kalıcı).
- **Blob depolama:** **S3-uyumlu soyutlama** üzerine yazılır (boto3/aioboto3). Depo arkası swappable.
  - Başlangıç: **Cloudflare R2** (ücretsiz başla, egress yok).
  - Büyüyünce config ile **kendi MinIO** (sabit maliyet, sınırsız disk) veya **Backblaze B2**'ye geçiş — kod değişmeden.

### Büyük dataset maliyet notu (20–30 GB+)
- R2 ücretsiz 10 GB **hesap geneli toplam** (ekip başına değil).
- Depolama her yerde ucuz; pahalı olan egress → R2/B2'de ücretsiz, ayrıca lazy+cache+dedup ile minimize.
- 30 GB ≈ R2 ~$0.45/ay, B2 ~$0.18/ay; kendi MinIO (Hetzner Storage Box 1TB) sabit ~€3.8/ay.
- **Sonuç:** S3 API'ye kod, default R2; ölçek/maliyet gerektiğinde MinIO/B2'ye sıfır-kod geçiş.
