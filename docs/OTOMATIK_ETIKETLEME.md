# Otomatik Etiketleme (Kullanıcı Modelleri)

Giriş yapmış kullanıcı kendi YOLO modelini hesabına kaydeder ve açık klasör /
ekip datasetinde otomatik etiketleme çalıştırır. Sonuçlar önce **önizlemede**
gösterilir; yalnızca "Kabul Et" denirse datasete yazılır.

## Kullanım
1. **Hesap → Modellerim... → Model Yükle**: `.onnx` (önerilen) veya `.pt` seçin,
   ad (zorunlu) ve açıklama (opsiyonel) girin. Görev tipi ve sınıflar dosyadan okunur.
2. Bir klasör veya ekip dataseti açın → **Hesap → Otomatik Etiketle...**
   - Model, güven eşiği, IoU ve kapsam (tümü / etiketsizler / split) seçin.
   - **Sınıf eşleme**: aynı isimli sınıflar otomatik eşlenir; diğerleri için
     dataset sınıfı / "Yeni sınıf" / "Yoksay" seçin.
3. **Önizleme**: çıkarım arka planda sürerken tüm görsellerde gezinebilirsiniz
   (←/→). Gri ince çizgi mevcut etiket, renkli kesikli çizgi model tahminidir.
   Güven eşiği kaydırıcısı canlı filtreler.
4. **Kabul Et...** → birleştirme modu: *mevcutlara ekle* / *sadece etiketsiz
   görseller* / *mevcutları değiştir*. **Reddet** hiçbir şey yazmaz.
   Ekip datasetlerinde kabul edilen etiketler buluta da senkronlanır.

## Model formatları
- **ONNX** (her kurulumda çalışır): `yolo export model=best.pt format=onnx`.
  YOLOv8/11 (klasik çıktı + NMS) ve YOLO26/v10 (end-to-end) çıktıları desteklenir;
  detect / segment / obb / pose / classify.
- **.pt**: yalnızca `ultralytics` kuruluysa çalışır (exe'de yoktur).

## Sunucu kurulumu (bir kez)
1. Supabase SQL Editor'de `supabase/migrations/0007_user_models.sql` ve ardından
   `0008_security_hardening.sql` çalıştırın (yeni presign 0008'deki
   `legacy_blob_grants` tablosunu okur; bkz. [SUPABASE_KURULUM.md](SUPABASE_KURULUM.md)).
2. `storage-presign` Edge Function'ını yeniden deploy edin
   (`supabase functions deploy storage-presign`). "Verify JWT with legacy secret"
   **kapalı** kalmalı. Modeller R2'de `models/<kullanıcı_id>/<sha256>` altında tutulur.
3. Yerel cache: `~/.annotie/models/`.
