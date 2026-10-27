-- =============================================================
-- Annotie — 0007: Kullanıcıya (profile) özgü modeller
-- =============================================================
-- Giriş yapmış kullanıcı kendi YOLO modelini (.onnx / .pt) kaydeder.
-- Model dosyası R2'de `models/<owner_id>/<content_hash>` anahtarıyla
-- tutulur; bu tablo yalnızca metadata taşır. Modeller sahibine özeldir:
-- RLS ile yalnızca owner_id = auth.uid() satırları görülebilir/yazılabilir.

create table if not exists public.user_models (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null default auth.uid()
                 references auth.users(id) on delete cascade,
  name         text not null,
  description  text,
  format       text not null check (format in ('onnx', 'pt')),
  task_type    text,
  class_names  jsonb not null default '[]'::jsonb,
  imgsz        int,
  kpt_shape    int[],
  content_hash text not null,
  size_bytes   bigint,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint user_models_owner_name_unique unique (owner_id, name),
  constraint user_models_name_not_blank check (length(btrim(name)) > 0)
);

create index if not exists user_models_owner_idx on public.user_models (owner_id);
create index if not exists user_models_hash_idx on public.user_models (content_hash);

create or replace function public.touch_user_models_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists user_models_touch_updated_at on public.user_models;
create trigger user_models_touch_updated_at
  before update on public.user_models
  for each row execute function public.touch_user_models_updated_at();

alter table public.user_models enable row level security;

drop policy if exists user_models_select on public.user_models;
drop policy if exists user_models_insert on public.user_models;
drop policy if exists user_models_update on public.user_models;
drop policy if exists user_models_delete on public.user_models;

create policy user_models_select on public.user_models
  for select to authenticated using (owner_id = auth.uid());
create policy user_models_insert on public.user_models
  for insert to authenticated with check (owner_id = auth.uid());
create policy user_models_update on public.user_models
  for update to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy user_models_delete on public.user_models
  for delete to authenticated using (owner_id = auth.uid());
