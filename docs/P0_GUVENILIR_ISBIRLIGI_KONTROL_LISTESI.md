# Annotie P0 Güvenilir İşbirliği Kontrol Listesi

Son güncelleme: 23 Eylül 2026
Genel ilerleme: **3 / 9 tamamlandı**

## Durum işaretleri

- `[x]` Uygulandı ve ilgili testleri geçti.
- `[ ]` Henüz uygulanmadı.
- `[!]` Uygulandı ancak açık sorun veya eksik doğrulama var.

## P0 teslimatları

- [x] **1. Kalıcı annotation kimliği**
  - Eksik: UID, YOLO satır sırası ve içeriğine bağlıydı; geometri veya sıra değişince nesne kimliği değişiyordu.
  - Yapılan: Dataset içindeki `.annotie/annotation_ids/` alanına UUID ve canonical YOLO satır parmak izi yazan atomik metadata sistemi eklendi.
  - Entegrasyon: Dataset/klasör açma, lazy okuma, normal ve otomatik kayıt, cloud yerel cache, export, silme ve geri alma yolları sisteme bağlandı.
  - Uyumluluk: YOLO `.txt` içeriği değişmedi. Metadata yolu verilmeyen eski API çağrıları eski deterministik davranışı koruyor.
  - Doğrulama: PySide6 ve NumPy bulunan izole ortamda `python -m unittest discover -s tests -v` çalıştı; **18/18 test geçti, skip ve hata yok**. `compileall` ve `git diff --check` başarılı.
  - Açık sorun: Bu aşama yalnızca yerel kalıcı kimliği çözer. Ayrı cloud istemcilerinin ortak kimlik kaynağı 2. ve 3. teslimatlarda kurulacak. Salt okunur dataset metadata yazamaz.
  - Commit: `feat: persist annotation identities`

- [x] **2. Nesne bazlı bulut şeması**
  - Eksik: `label_content` tek parça blob olduğu için iki kullanıcının farklı nesne değişiklikleri ayrı sürümlenemiyor, aynı nesnedeki yarış atomik olarak tespit edilemiyor ve reconnect için kalıcı event sırası bulunmuyordu.
  - Yapılan: `0005_annotation_operations.sql` ile annotation tombstone alanları, pozitif object version kuralları, dataset bazlı monotonik `collaboration_sequence` ve append-only `annotation_events` tablosu eklendi.
  - Atomik RPC: `apply_annotation_operation`, `create/modify/class_change/delete` işlemlerini dataset satır kilidi altında uygular. `base_version` eşleşmezse veri yazmadan `conflict` döner; başarılı işlem object version ve dataset sequence değerini bir artırır.
  - Idempotency: `(dataset_id, client_op_id)` benzersizdir. Aynı istek tekrarı ilk sonucu döndürür; aynı anahtar farklı istek için kullanılırsa `idempotency_key_reused` hatası oluşur.
  - Güvenlik: RPC kullanıcı, ekip rolü ve image/dataset ilişkisini doğrular. Annotation/event doğrudan yazma yetkileri kaldırıldı; event okuması ekip üyeliği RLS politikasına bağlandı.
  - Doğrulama: 7 migration sözleşme testi geçti. Tam test paketi PySide6/NumPy ortamında **25/25** geçti. Migration `pglast` PostgreSQL parser ile **19 statement** olarak hatasız ayrıştırıldı; `git diff --check` başarılı.
  - Migration etkisi: Canlı Supabase'e otomatik uygulanmadı. SQL Editor'da 0001–0005 sırası dokümante edildi. `label_content` korunur ve mevcut istemci bu aşamada çalışmaya devam eder.
  - Açık sorun: Canlı/staging PostgreSQL üzerinde yetkili ve viewer kullanıcılarla runtime smoke testi henüz yapılmadı. Uygulama/relay bu RPC'yi 3. ve 4. teslimatlar tamamlanana kadar kullanmaz.
  - Commit: `feat: add versioned annotation operation schema`

- [x] **3. Mevcut veri setlerinin güvenli taşınması**
  - Eksik: Eski ekip datasetlerinde tek doğruluk kaynağı `images.label_content` idi. Object version yerelde saklanmıyor, annotation satırları okunmuyor ve v1/v2 geçişi yarıda kalırsa dataset durumu belirlenemiyordu.
  - Yapılan: `0006_collab_v2_migration.sql`; datasetlere `collab_schema_version`, görsellere `annotations_migrated_at`, idempotent görsel taşıma RPC'si ve yalnızca tüm görseller tamamlanınca v2 yapan finalize RPC'si ekledi.
  - Taşıma davranışı: Ekip dataseti ilk açılırken legacy YOLO satırları eksiksiz parse edilir. Geçersiz tek satır varsa veri düşürmek yerine taşıma durur. Tamamlanan görseller retry'da tekrar yazılmaz; yarıda kalan dataset kaldığı yerden devam eder.
  - Yeni doğruluk kaynağı: V2 dataset açılışı annotation satırlarını okur. DB satırları yerel YOLO dosyası ve `.annotie` UID/version metadata'sı olarak materialize edilir. Annotation modelleri ve collaboration serializer artık object version taşır.
  - Dual-write: Annotation insert/update/tombstone sonrası PostgreSQL trigger aktif nesnelerden canonical YOLO metnini üretip `label_content` snapshot'ını aynı transaction'da yeniler. Eski snapshot silinmez ancak artık doğruluk kaynağı değildir.
  - Geçiş yazımı: Mevcut kaydetme akışı yerel durum ile bilinen DB satırlarını karşılaştırıp create/modify/class_change/delete operasyonlarına ayırır. Başarılı RPC sürümleri modele ve `.annotie` dosyasına geri yazılır; aynı görselde üst üste kayıtlar sıraya alınır.
  - Doğrulama: 14 yeni migration/dönüşüm/senkron/metadata testi eklendi. Tam test paketi PySide6/NumPy ortamında **39/39** geçti. 0006 migration `pglast` ile **17 statement** olarak hatasız ayrıştırıldı; `compileall` başarılı.
  - Migration etkisi: Güncel istemciden önce 0006 uygulanmalıdır. `detect/segment/pose` eski task type adları desteklenir. Viewer, tamamlanmış v2 datasetleri yazma RPC'si çağırmadan okuyabilir.
  - Açık sorun: Canlı/staging Supabase runtime testi yapılmadı. Relay henüz commit-before-broadcast uygulamadığı ve protocol-v2 kapısı koymadığı için karma eski/yeni istemci engeli 4. teslimatta tamamlanacak. Ağ kesintisinde kalıcı retry 6. teslimatı bekliyor.
  - Commit: `feat: migrate cloud datasets to collaboration v2`

- [ ] **4. Server-authoritative işlem akışı**
  - Plan: Operasyonu önce Supabase RPC'ye yazmak; yalnızca commit sonrası acknowledgement ve broadcast yapmak.

- [ ] **5. Late-join ve reconnect replay**
  - Plan: Dataset sequence cursor, sayfalı eksik event replay ve idempotent uygulama.

- [ ] **6. Kalıcı çevrimdışı outbox**
  - Plan: SQLite outbox, acknowledgement sonrası silme ve conflict sonrası bağımlı operasyonları durdurma.

- [ ] **7. Soft annotation lock**
  - Plan: Süreli lease, lock sahibi göstergesi, yenileme/bırakma ve timeout temizliği.

- [ ] **8. Conflict ve hata kullanıcı deneyimi**
  - Plan: Conflict karar ekranı, retry/bekleyen işlem göstergesi ve görünür cloud yazma hataları.

- [ ] **9. P0 çok istemcili doğrulama ve 1.5.0**
  - Plan: Yarış, reconnect, late join, restart, JWT, duplicate operation ve DB failure senaryoları; migration/rollback dokümanı ve sürüm artışı.

## Her teslimatta uygulanacak kontrol

- [ ] Eksik davranış ve gerçek risk yazıldı.
- [ ] Değişen dosyalar ve veri akışı yazıldı.
- [ ] Seçilen çözümün gerekçesi yazıldı.
- [ ] Unit/regression testleri eklendi ve sonucu kaydedildi.
- [ ] Migration ve geriye uyumluluk etkisi kaydedildi.
- [ ] Kalan risk ve sonraki teslimat kaydedildi.
- [ ] Commit/push durumu kaydedildi.

Bu alt kontrol listesi her yeni teslimat tamamlanırken o teslimatın kaydı içinde doldurulur; genel şablon olduğu için burada boş tutulur.
