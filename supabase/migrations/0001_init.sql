-- =============================================================
-- Annotie — Faz 1: Kullanıcı, Ekip, Davet, Dataset şeması + RLS
-- Supabase (Postgres) üzerinde çalıştırılır.
-- Bu migrasyon idempotent değildir; temiz bir projede bir kez çalıştırın.
-- =============================================================

create extension if not exists pgcrypto;

-- -------------------------------------------------------------
-- ENUM tipleri
-- -------------------------------------------------------------
do $$ begin
  create type team_role as enum ('owner','admin','annotator','viewer');
exception when duplicate_object then null; end $$;

do $$ begin
  create type invite_status as enum ('pending','accepted','declined','expired');
exception when duplicate_object then null; end $$;

-- -------------------------------------------------------------
-- TABLOLAR
-- -------------------------------------------------------------

-- profiles: auth.users ile 1:1 (kimlik Supabase Auth'ta tutulur)
create table if not exists public.profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  username     text unique not null,
  display_name text,
  created_at   timestamptz not null default now()
);

-- teams
create table if not exists public.teams (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  owner_id   uuid not null references public.profiles(id),
  created_at timestamptz not null default now()
);

-- memberships: kullanıcı <-> ekip (rol ile)
create table if not exists public.memberships (
  id         uuid primary key default gen_random_uuid(),
  team_id    uuid not null references public.teams(id) on delete cascade,
  user_id    uuid not null references public.profiles(id) on delete cascade,
  role       team_role not null default 'annotator',
  created_at timestamptz not null default now(),
  unique (team_id, user_id)
);

-- invites: token'lı, süresi dolan davetler
create table if not exists public.invites (
  id              uuid primary key default gen_random_uuid(),
  team_id         uuid not null references public.teams(id) on delete cascade,
  email           text,
  invited_user_id uuid references public.profiles(id),
  role            team_role not null default 'annotator',
  token           text unique not null default encode(gen_random_bytes(16),'hex'),
  status          invite_status not null default 'pending',
  invited_by      uuid not null references public.profiles(id),
  expires_at      timestamptz not null default (now() + interval '14 days'),
  created_at      timestamptz not null default now()
);

-- datasets: artık ekibe bağlı (kullanıcı diskine değil)
create table if not exists public.datasets (
  id         uuid primary key default gen_random_uuid(),
  team_id    uuid not null references public.teams(id) on delete cascade,
  name       text not null,
  task_type  text,            -- detect / segment / pose / obb / classify
  kpt_shape  int[],           -- [keypoint_sayisi, deger_sayisi]
  created_by uuid not null references public.profiles(id),
  created_at timestamptz not null default now()
);

-- dataset_classes: sınıf tanımları
create table if not exists public.dataset_classes (
  id          uuid primary key default gen_random_uuid(),
  dataset_id  uuid not null references public.datasets(id) on delete cascade,
  class_index int not null,
  name        text not null,
  color       text,
  unique (dataset_id, class_index)
);

-- images: içerik-hash adresli görsel kayıtları (baytlar nesne deposunda)
create table if not exists public.images (
  id           uuid primary key default gen_random_uuid(),
  dataset_id   uuid not null references public.datasets(id) on delete cascade,
  filename     text not null,
  content_hash text not null,          -- sha256
  storage_key  text not null,          -- S3/R2 anahtarı (hash bazlı)
  width        int,
  height       int,
  split        text,                    -- train / val / test / unassigned
  size_bytes   bigint,
  created_by   uuid references public.profiles(id),
  created_at   timestamptz not null default now(),
  unique (dataset_id, filename)
);

-- annotations: görsel başına satır bazlı anotasyon (relay uid ile uyumlu)
create table if not exists public.annotations (
  id          uuid primary key default gen_random_uuid(),
  image_id    uuid not null references public.images(id) on delete cascade,
  uid         text not null,            -- istemci tarafı kalıcı uid
  class_index int,
  type        text,                     -- bbox / obb / polygon / keypoint / classify
  data        jsonb not null,           -- geometri / değerler
  version     int not null default 1,
  updated_by  uuid references public.profiles(id),
  updated_at  timestamptz not null default now(),
  unique (image_id, uid)
);

-- Sık sorgular için indeksler
create index if not exists idx_memberships_user   on public.memberships(user_id);
create index if not exists idx_memberships_team   on public.memberships(team_id);
create index if not exists idx_datasets_team      on public.datasets(team_id);
create index if not exists idx_images_dataset     on public.images(dataset_id);
create index if not exists idx_images_hash        on public.images(content_hash);
create index if not exists idx_annotations_image  on public.annotations(image_id);
create index if not exists idx_invites_token      on public.invites(token);

-- -------------------------------------------------------------
-- YARDIMCI FONKSİYONLAR (RLS özyinelemesini önlemek için SECURITY DEFINER)
-- -------------------------------------------------------------

create or replace function public.is_team_member(p_team uuid)
returns boolean language sql security definer stable set search_path = public as $$
  select exists(
    select 1 from memberships
    where team_id = p_team and user_id = auth.uid()
  );
$$;

create or replace function public.has_team_role(p_team uuid, p_roles team_role[])
returns boolean language sql security definer stable set search_path = public as $$
  select exists(
    select 1 from memberships
    where team_id = p_team and user_id = auth.uid() and role = any(p_roles)
  );
$$;

create or replace function public.dataset_team(p_dataset uuid)
returns uuid language sql security definer stable set search_path = public as $$
  select team_id from datasets where id = p_dataset;
$$;

create or replace function public.image_team(p_image uuid)
returns uuid language sql security definer stable set search_path = public as $$
  select d.team_id
  from images i join datasets d on d.id = i.dataset_id
  where i.id = p_image;
$$;

-- -------------------------------------------------------------
-- TETİKLEYİCİLER
-- -------------------------------------------------------------

-- Yeni auth kullanıcısı -> otomatik profil oluştur
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  v_username text;
begin
  v_username := coalesce(
    nullif(new.raw_user_meta_data->>'username',''),
    split_part(new.email, '@', 1)
  );
  if exists(select 1 from public.profiles where username = v_username) then
    v_username := v_username || '_' || substr(new.id::text, 1, 8);
  end if;
  insert into public.profiles(id, username, display_name)
  values (
    new.id,
    v_username,
    coalesce(nullif(new.raw_user_meta_data->>'display_name',''), v_username)
  );
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Yeni ekip -> kurucuyu otomatik 'owner' üye yap
create or replace function public.handle_new_team()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.memberships(team_id, user_id, role)
  values (new.id, new.owner_id, 'owner')
  on conflict (team_id, user_id) do nothing;
  return new;
end; $$;

drop trigger if exists on_team_created on public.teams;
create trigger on_team_created
  after insert on public.teams
  for each row execute function public.handle_new_team();

-- Davet kabul (token ile) -> üyelik oluştur
create or replace function public.accept_invite(p_token text)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  v_invite public.invites;
begin
  select * into v_invite
  from public.invites
  where token = p_token and status = 'pending' and expires_at > now();

  if v_invite.id is null then
    raise exception 'Gecersiz veya suresi dolmus davet';
  end if;

  insert into public.memberships(team_id, user_id, role)
  values (v_invite.team_id, auth.uid(), v_invite.role)
  on conflict (team_id, user_id) do nothing;

  update public.invites set status = 'accepted' where id = v_invite.id;
  return v_invite.team_id;
end; $$;

-- -------------------------------------------------------------
-- RLS: tüm tablolarda etkin
-- -------------------------------------------------------------
alter table public.profiles        enable row level security;
alter table public.teams           enable row level security;
alter table public.memberships     enable row level security;
alter table public.invites         enable row level security;
alter table public.datasets        enable row level security;
alter table public.dataset_classes enable row level security;
alter table public.images          enable row level security;
alter table public.annotations     enable row level security;

-- profiles ----------------------------------------------------
create policy profiles_select on public.profiles
  for select to authenticated using (true);          -- davet için kullanıcı arama
create policy profiles_insert on public.profiles
  for insert to authenticated with check (id = auth.uid());
create policy profiles_update on public.profiles
  for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

-- teams -------------------------------------------------------
create policy teams_select on public.teams
  for select to authenticated using (is_team_member(id));
create policy teams_insert on public.teams
  for insert to authenticated with check (owner_id = auth.uid());
create policy teams_update on public.teams
  for update to authenticated using (has_team_role(id, array['owner','admin']::team_role[]));
create policy teams_delete on public.teams
  for delete to authenticated using (has_team_role(id, array['owner']::team_role[]));

-- memberships -------------------------------------------------
create policy memberships_select on public.memberships
  for select to authenticated using (is_team_member(team_id));
create policy memberships_insert on public.memberships
  for insert to authenticated
  with check (has_team_role(team_id, array['owner','admin']::team_role[]));
create policy memberships_update on public.memberships
  for update to authenticated
  using (has_team_role(team_id, array['owner','admin']::team_role[]));
create policy memberships_delete on public.memberships
  for delete to authenticated
  using (has_team_role(team_id, array['owner','admin']::team_role[]) or user_id = auth.uid());

-- invites -----------------------------------------------------
create policy invites_select on public.invites
  for select to authenticated
  using (is_team_member(team_id) or invited_user_id = auth.uid());
create policy invites_insert on public.invites
  for insert to authenticated
  with check (has_team_role(team_id, array['owner','admin']::team_role[]) and invited_by = auth.uid());
create policy invites_update on public.invites
  for update to authenticated
  using (has_team_role(team_id, array['owner','admin']::team_role[]));
create policy invites_delete on public.invites
  for delete to authenticated
  using (has_team_role(team_id, array['owner','admin']::team_role[]));

-- datasets ----------------------------------------------------
create policy datasets_select on public.datasets
  for select to authenticated using (is_team_member(team_id));
create policy datasets_insert on public.datasets
  for insert to authenticated
  with check (has_team_role(team_id, array['owner','admin','annotator']::team_role[]) and created_by = auth.uid());
create policy datasets_update on public.datasets
  for update to authenticated
  using (has_team_role(team_id, array['owner','admin','annotator']::team_role[]));
create policy datasets_delete on public.datasets
  for delete to authenticated
  using (has_team_role(team_id, array['owner','admin']::team_role[]));

-- dataset_classes ---------------------------------------------
create policy classes_select on public.dataset_classes
  for select to authenticated using (is_team_member(dataset_team(dataset_id)));
create policy classes_write on public.dataset_classes
  for all to authenticated
  using (has_team_role(dataset_team(dataset_id), array['owner','admin','annotator']::team_role[]))
  with check (has_team_role(dataset_team(dataset_id), array['owner','admin','annotator']::team_role[]));

-- images ------------------------------------------------------
create policy images_select on public.images
  for select to authenticated using (is_team_member(dataset_team(dataset_id)));
create policy images_write on public.images
  for all to authenticated
  using (has_team_role(dataset_team(dataset_id), array['owner','admin','annotator']::team_role[]))
  with check (has_team_role(dataset_team(dataset_id), array['owner','admin','annotator']::team_role[]));

-- annotations -------------------------------------------------
create policy annotations_select on public.annotations
  for select to authenticated using (is_team_member(image_team(image_id)));
create policy annotations_write on public.annotations
  for all to authenticated
  using (has_team_role(image_team(image_id), array['owner','admin','annotator']::team_role[]))
  with check (has_team_role(image_team(image_id), array['owner','admin','annotator']::team_role[]));

-- =============================================================
-- Migrasyon sonu
-- =============================================================
