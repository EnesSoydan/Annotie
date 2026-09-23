# Annotie P0 Güvenilir İşbirliği Kontrol Listesi

Son güncelleme: 23 Eylül 2026
Genel ilerleme: **1 / 9 tamamlandı**

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

- [ ] **2. Nesne bazlı bulut şeması**
  - Plan: Annotation satırları, object version, tombstone, dataset sequence, idempotent event tablosu ve atomik `apply_annotation_operation` RPC.

- [ ] **3. Mevcut veri setlerinin güvenli taşınması**
  - Plan: `label_content` verisini annotation satırlarına aktarıp `collab_schema_version=2` işaretlemek ve geçiş süresince snapshot'ı çift yazmak.

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
