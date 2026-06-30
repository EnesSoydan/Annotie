-- =============================================================
-- Annotie — Faz 6: Görsel etiket içeriği (YOLO .txt) saklama
-- 0001-0003'ten SONRA bir kez çalıştırın.
--
-- Etiketler, görsel başına ham YOLO .txt metni olarak images tablosunda
-- saklanır. Bu, editör round-trip'ini (read_label_file/write_label_file ile)
-- birebir sadık ve basit tutar; tüm görev tipleri (bbox/polygon/obb/
-- keypoints/classify) tek bir metin alanıyla desteklenir.
-- Erişim/yetki mevcut images RLS politikalarıyla (üyelik + yazma rolü) zorlanır.
-- =============================================================

alter table public.images
  add column if not exists label_content   text not null default '',
  add column if not exists label_updated_at timestamptz,
  add column if not exists label_updated_by uuid references public.profiles(id);

-- =============================================================
-- Migrasyon sonu
-- =============================================================
