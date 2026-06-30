-- =============================================================
-- Annotie — Faz 3: Ekip yardimci RPC'leri
-- 0001_init.sql calistirildiktan SONRA bir kez calistirin.
-- =============================================================

-- Bana gonderilen bekleyen davetler + ekip adi.
-- Davet edilen kisi henuz ekip uyesi olmadigindan teams uzerindeki RLS
-- ekip adini gizler; bu SECURITY DEFINER fonksiyon yalnizca ilgili
-- kullaniciya kendi davetlerini (ekip adiyla) guvenli sekilde gosterir.
create or replace function public.my_pending_invites()
returns table (
  invite_id       uuid,
  team_id         uuid,
  team_name       text,
  role            team_role,
  invited_by_name text,
  token           text,
  expires_at      timestamptz
)
language sql security definer stable set search_path = public as $$
  select i.id, i.team_id, t.name, i.role, p.username, i.token, i.expires_at
  from invites i
  join teams t on t.id = i.team_id
  left join profiles p on p.id = i.invited_by
  where i.status = 'pending'
    and i.expires_at > now()
    and i.invited_user_id = auth.uid();
$$;

-- =============================================================
-- Migrasyon sonu
-- =============================================================
