-- =============================================================
-- Annotie — 0008: Güvenlik sertleştirmesi (P0-B)
-- 0001–0007'den SONRA çalıştırın. Tekrar çalıştırılabilir.
--
-- Kapatılan açıklar:
--   * Rol yükseltme: admin kendini/başkasını owner yapabiliyor, owner'ı
--     düşürebiliyor, owner_id'yi değiştirebiliyordu.
--   * Davet token'ları tüm üyelere görünüyor; accept_invite davet edilen
--     kişiyi doğrulamıyordu (viewer, admin davetini ikinci hesapla alabiliyordu).
--   * Annotator kontrol kolonlarını (collaboration_sequence,
--     annotations_migrated_at, collab_schema_version) değiştirebiliyordu;
--     migrated_at temizlenince migrasyon RPC'si tüm etiketleri olaysız siliyordu.
--   * images.filename yerel yola eklendiği için klasör dışına dosya yazılabiliyordu.
--   * Global blobs/<hash> anahtarı kiracılar arası okuma/yazmaya izin veriyordu
--     (bkz. storage-presign: artık teams/<team_id>/blobs/<hash>).
--
-- Deploy sırası: bu migrasyon → storage-presign deploy → yeni istemci sürümü
-- → relay (my_dataset_role RPC'sini kullanır).
-- =============================================================

-- -------------------------------------------------------------
-- 1) Rol yardımcıları
-- -------------------------------------------------------------
create or replace function public.my_team_role(p_team uuid)
returns team_role language sql security definer stable set search_path = public as $$
  select role from memberships where team_id = p_team and user_id = auth.uid();
$$;

-- Çağıran bu ekipte p_role rolündeki bir üyeliği/daveti yönetebilir mi?
-- owner → admin/annotator/viewer; admin → annotator/viewer. 'owner' rolü
-- doğrudan DML ile asla atanamaz/değiştirilemez (yalnızca handle_new_team).
create or replace function public.can_manage_role(p_team uuid, p_role team_role)
returns boolean language sql security definer stable set search_path = public as $$
  select coalesce(
    case public.my_team_role(p_team)
      when 'owner' then p_role in ('admin', 'annotator', 'viewer')
      when 'admin' then p_role in ('annotator', 'viewer')
      else false
    end,
    false
  );
$$;

-- Relay join_room yetkisi: kullanıcının dataset ekibindeki rolü (üye değilse null).
create or replace function public.my_dataset_role(p_dataset_id uuid)
returns team_role language sql security definer stable set search_path = public as $$
  select m.role
  from datasets d
  join memberships m on m.team_id = d.team_id
  where d.id = p_dataset_id and m.user_id = auth.uid();
$$;

-- -------------------------------------------------------------
-- 2) memberships: rol değişikliği yalnızca yetki sınırları içinde
-- -------------------------------------------------------------
drop policy if exists memberships_insert on public.memberships;
create policy memberships_insert on public.memberships
  for insert to authenticated
  with check (public.can_manage_role(team_id, role));

-- USING eski satırı (yönetilebilir mi), WITH CHECK yeni rolü denetler.
drop policy if exists memberships_update on public.memberships;
create policy memberships_update on public.memberships
  for update to authenticated
  using (public.can_manage_role(team_id, role))
  with check (public.can_manage_role(team_id, role));

-- Üye kendi üyeliğinden çıkabilir; owner çıkamaz (ekibi silmeli).
drop policy if exists memberships_delete on public.memberships;
create policy memberships_delete on public.memberships
  for delete to authenticated
  using (
    (user_id = auth.uid() and role <> 'owner')
    or public.can_manage_role(team_id, role)
  );

-- team_id/user_id taşınamaz; yalnızca rol güncellenebilir.
revoke update on public.memberships from anon, authenticated;
grant update (role) on public.memberships to authenticated;

-- -------------------------------------------------------------
-- 3) teams: owner_id değiştirilemez (yalnızca ad)
-- -------------------------------------------------------------
revoke update on public.teams from anon, authenticated;
grant update (name) on public.teams to authenticated;

-- -------------------------------------------------------------
-- 4) invites: token yalnızca owner/admin ve davet edilene görünür
-- -------------------------------------------------------------
drop policy if exists invites_select on public.invites;
create policy invites_select on public.invites
  for select to authenticated
  using (
    public.has_team_role(team_id, array['owner', 'admin']::team_role[])
    or invited_user_id = auth.uid()
  );

drop policy if exists invites_insert on public.invites;
create policy invites_insert on public.invites
  for insert to authenticated
  with check (public.can_manage_role(team_id, role) and invited_by = auth.uid());

drop policy if exists invites_update on public.invites;
create policy invites_update on public.invites
  for update to authenticated
  using (public.can_manage_role(team_id, role))
  with check (public.can_manage_role(team_id, role));

drop policy if exists invites_delete on public.invites;
create policy invites_delete on public.invites
  for delete to authenticated
  using (public.can_manage_role(team_id, role));

-- Davet rolü/ekibi/token'ı sonradan değiştirilemez.
revoke update on public.invites from anon, authenticated;
grant update (status, expires_at) on public.invites to authenticated;

-- Davet yalnızca davet edilen hesap (kullanıcı adı daveti) veya davet
-- e-postasının sahibi (e-posta daveti) tarafından kabul edilebilir.
create or replace function public.accept_invite(p_token text)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  v_invite public.invites;
  v_email text;
begin
  if auth.uid() is null then
    raise exception 'Giris gerekli';
  end if;

  select * into v_invite
  from public.invites
  where token = p_token and status = 'pending' and expires_at > now()
  for update;

  if v_invite.id is null then
    raise exception 'Gecersiz veya suresi dolmus davet';
  end if;

  if v_invite.invited_user_id is not null then
    if v_invite.invited_user_id <> auth.uid() then
      raise exception 'Bu davet baska bir hesaba ait';
    end if;
  elsif v_invite.email is not null then
    select u.email into v_email from auth.users u where u.id = auth.uid();
    if v_email is null or lower(v_email) <> lower(v_invite.email) then
      raise exception 'Bu davet baska bir hesaba ait';
    end if;
  end if;

  if v_invite.role = 'owner' then
    raise exception 'Gecersiz davet rolu';
  end if;

  insert into public.memberships(team_id, user_id, role)
  values (v_invite.team_id, auth.uid(), v_invite.role)
  on conflict (team_id, user_id) do nothing;

  update public.invites set status = 'accepted' where id = v_invite.id;
  return v_invite.team_id;
end; $$;

-- -------------------------------------------------------------
-- 5) images / datasets: kontrol kolonlarına yalnızca RPC'ler yazar
-- -------------------------------------------------------------
-- İstemcinin yazdığı kolonlar (upsert ON CONFLICT DO UPDATE tümünü günceller).
-- annotations_migrated_at, id ve created_at bu listede yok.
revoke insert, update on public.images from anon, authenticated;
grant insert (
  dataset_id, filename, content_hash, storage_key, width, height, split,
  size_bytes, created_by, label_content, label_updated_at, label_updated_by
) on public.images to authenticated;
grant update (
  dataset_id, filename, content_hash, storage_key, width, height, split,
  size_bytes, created_by, label_content, label_updated_at, label_updated_by
) on public.images to authenticated;

-- collaboration_sequence ve collab_schema_version yalnızca RPC'lerle değişir.
revoke insert, update on public.datasets from anon, authenticated;
grant insert (team_id, name, task_type, kpt_shape, created_by)
  on public.datasets to authenticated;
grant update (name) on public.datasets to authenticated;

-- Dosya adı diğer üyelerin diskinde yola eklenir: tek, güvenli bir bileşen olmalı.
-- NOT VALID: mevcut satırları taramaz, yeni ve güncellenen satırlarda zorlanır.
do $$ begin
  alter table public.images add constraint images_filename_safe check (
    char_length(filename) between 1 and 255
    and filename !~ '[/\\:*?"<>|[:cntrl:]]'
    and filename not in ('.', '..')
    and filename !~ '[ .]$'
  ) not valid;
exception when duplicate_object then null; end $$;

do $$ begin
  alter table public.images add constraint images_content_hash_sha256 check (
    content_hash ~ '^[0-9a-f]{64}$'
  ) not valid;
exception when duplicate_object then null; end $$;

-- migrate_image_annotations_v2 artık hiçbir satırı silmez: görselin zaten
-- satırları varsa (migrated_at bir şekilde boş olsa bile) yalnızca taşınmış
-- olarak işaretler. Böylece eski snapshot ile v2 geçmişinin üzerine yazılamaz.
create or replace function public.migrate_image_annotations_v2(
  p_dataset_id uuid,
  p_image_id uuid,
  p_annotations jsonb
)
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  v_actor uuid := auth.uid();
  v_team_id uuid;
  v_migrated_at timestamptz;
  v_item jsonb;
  v_uid uuid;
  v_class_index int;
  v_type text;
  v_count int := 0;
begin
  if v_actor is null then
    raise exception using errcode = '28000', message = 'authentication_required';
  end if;
  if jsonb_typeof(p_annotations) is distinct from 'array' then
    raise exception using errcode = '22023', message = 'annotations_array_required';
  end if;

  select d.team_id into v_team_id
  from public.datasets d where d.id = p_dataset_id;
  if v_team_id is null then
    raise exception using errcode = 'P0002', message = 'dataset_not_found';
  end if;
  if not public.has_team_role(
    v_team_id, array['owner', 'admin', 'annotator']::team_role[]
  ) then
    raise exception using errcode = '42501', message = 'annotation_write_forbidden';
  end if;

  select i.annotations_migrated_at into v_migrated_at
  from public.images i
  where i.id = p_image_id and i.dataset_id = p_dataset_id
  for update;
  if not found then
    raise exception using errcode = '22023', message = 'image_dataset_mismatch';
  end if;

  if v_migrated_at is null and exists (
    select 1 from public.annotations a where a.image_id = p_image_id
  ) then
    update public.images set annotations_migrated_at = now()
    where id = p_image_id;
    v_migrated_at := now();
  end if;

  if v_migrated_at is not null then
    select count(*)::int into v_count
    from public.annotations a
    where a.image_id = p_image_id and a.is_deleted = false;
    return v_count;
  end if;

  for v_item in select value from jsonb_array_elements(p_annotations)
  loop
    if jsonb_typeof(v_item) is distinct from 'object'
       or jsonb_typeof(v_item->'class_index') is distinct from 'number'
       or jsonb_typeof(v_item->'data') is distinct from 'object' then
      raise exception using errcode = '22023', message = 'invalid_annotation_payload';
    end if;

    begin
      v_uid := (v_item->>'uid')::uuid;
      v_class_index := (v_item->>'class_index')::int;
    exception when invalid_text_representation then
      raise exception using errcode = '22023', message = 'invalid_annotation_payload';
    end;
    v_type := v_item->>'type';

    if v_class_index < 0
       or v_type is null
       or v_type not in ('bbox', 'polygon', 'obb', 'keypoints', 'classify') then
      raise exception using errcode = '22023', message = 'invalid_annotation_payload';
    end if;

    -- Snapshot uretebilmek icin geometri semasini de bu transaction'da dogrula.
    perform public.annotation_yolo_line(
      v_class_index, v_type, v_item->'data'
    );

    insert into public.annotations (
      image_id, uid, class_index, type, data, version,
      updated_by, updated_at, is_deleted, deleted_at
    ) values (
      p_image_id, v_uid::text, v_class_index, v_type, v_item->'data', 1,
      v_actor, now(), false, null
    );
    v_count := v_count + 1;
  end loop;

  update public.images set annotations_migrated_at = now()
  where id = p_image_id;
  perform public.refresh_image_label_snapshot(p_image_id, v_actor);
  return v_count;
end;
$$;

-- -------------------------------------------------------------
-- 6) Eski global blob'lar için okuma izinleri
-- -------------------------------------------------------------
-- 0008 öncesi görseller R2'de blobs/<hash> altında. storage-presign bu öneki
-- yalnızca burada kayıtlı (ekip, hash) çiftleri için imzalar. Tablo yalnızca
-- ilk oluşturulduğunda doldurulur: sonradan eklenen satırlar başka ekibin
-- hash'ini taşıyabileceğinden asla izin üretmez.
do $$
begin
  if to_regclass('public.legacy_blob_grants') is null then
    create table public.legacy_blob_grants (
      team_id      uuid not null references public.teams(id) on delete cascade,
      content_hash text not null,
      created_at   timestamptz not null default now(),
      primary key (team_id, content_hash)
    );
    insert into public.legacy_blob_grants (team_id, content_hash)
    select distinct d.team_id, i.content_hash
    from public.images i
    join public.datasets d on d.id = i.dataset_id
    on conflict do nothing;
  end if;
end $$;

alter table public.legacy_blob_grants enable row level security;
drop policy if exists legacy_blob_grants_select on public.legacy_blob_grants;
create policy legacy_blob_grants_select on public.legacy_blob_grants
  for select to authenticated using (public.is_team_member(team_id));
revoke insert, update, delete on public.legacy_blob_grants from anon, authenticated;
grant select on public.legacy_blob_grants to authenticated;

-- -------------------------------------------------------------
-- 7) Fonksiyon yetkileri: anon/PUBLIC çağıramaz
-- -------------------------------------------------------------
revoke all on function public.is_team_member(uuid) from public, anon;
revoke all on function public.has_team_role(uuid, team_role[]) from public, anon;
revoke all on function public.dataset_team(uuid) from public, anon;
revoke all on function public.image_team(uuid) from public, anon;
revoke all on function public.my_team_role(uuid) from public, anon;
revoke all on function public.can_manage_role(uuid, team_role) from public, anon;
revoke all on function public.my_dataset_role(uuid) from public, anon;
revoke all on function public.my_pending_invites() from public, anon;
revoke all on function public.accept_invite(text) from public, anon;
revoke all on function public.migrate_image_annotations_v2(uuid, uuid, jsonb)
  from public, anon;

grant execute on function public.is_team_member(uuid) to authenticated, service_role;
grant execute on function public.has_team_role(uuid, team_role[]) to authenticated, service_role;
grant execute on function public.dataset_team(uuid) to authenticated, service_role;
grant execute on function public.image_team(uuid) to authenticated, service_role;
grant execute on function public.my_team_role(uuid) to authenticated, service_role;
grant execute on function public.can_manage_role(uuid, team_role) to authenticated, service_role;
grant execute on function public.my_dataset_role(uuid) to authenticated, service_role;
grant execute on function public.my_pending_invites() to authenticated, service_role;
grant execute on function public.accept_invite(text) to authenticated, service_role;
grant execute on function public.migrate_image_annotations_v2(uuid, uuid, jsonb)
  to authenticated;

-- =============================================================
-- Migration sonu
-- =============================================================
