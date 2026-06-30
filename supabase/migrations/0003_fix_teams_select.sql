-- =============================================================
-- Annotie — Faz 3 düzeltme: teams_select politikası
-- 0001/0002'den SONRA bir kez çalıştırın.
--
-- Sorun: teams'e INSERT sonrasi PostgREST (return=representation) eklenen
-- satiri SELECT ile geri dondurur. teams_select yalnizca is_team_member(id)
-- kontrol ediyordu; sahip uyeligi AFTER trigger ile olustugundan geri-donus
-- SELECT'i o anda kullaniciyi uye goremiyor ve RLS hatasi veriyordu.
--
-- Cozum: Sahip kendi ekibini her zaman gorebilsin (owner_id = auth.uid()).
-- =============================================================

drop policy if exists teams_select on public.teams;
create policy teams_select on public.teams
  for select to authenticated
  using (is_team_member(id) or owner_id = auth.uid());

-- Teshis fonksiyonu temizligi (artik gerekli degil)
drop function if exists public.whoami();

-- =============================================================
-- Migrasyon sonu
-- =============================================================
