-- =============================================================
-- Annotie P0/2: Nesne bazli annotation islemleri
-- 0001-0004'ten SONRA calistirin.
--
-- Bu migration:
--   * annotation tombstone ve surum alanlarini tamamlar,
--   * dataset basina monotonik collaboration sequence ekler,
--   * idempotent append-only event tablosu olusturur,
--   * create/modify/class_change/delete islemlerini atomik RPC'ye tasir.
--
-- label_content bu asamada kaldirilmaz. Veri tasima ve dual-write 0006'da
-- ele alinacaktir.
-- =============================================================

alter table public.datasets
  add column if not exists collaboration_sequence bigint not null default 0;

alter table public.annotations
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists is_deleted boolean not null default false,
  add column if not exists deleted_at timestamptz;

do $$ begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'datasets_collaboration_sequence_nonnegative'
      and conrelid = 'public.datasets'::regclass
  ) then
    alter table public.datasets
      add constraint datasets_collaboration_sequence_nonnegative
      check (collaboration_sequence >= 0);
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'annotations_version_positive'
      and conrelid = 'public.annotations'::regclass
  ) then
    alter table public.annotations
      add constraint annotations_version_positive check (version > 0);
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'annotations_tombstone_consistent'
      and conrelid = 'public.annotations'::regclass
  ) then
    alter table public.annotations
      add constraint annotations_tombstone_consistent check (
        (is_deleted = false and deleted_at is null)
        or (is_deleted = true and deleted_at is not null)
      );
  end if;
end $$;

create index if not exists idx_annotations_image_active
  on public.annotations(image_id)
  where is_deleted = false;

create table if not exists public.annotation_events (
  id                 uuid primary key default gen_random_uuid(),
  dataset_id         uuid not null references public.datasets(id) on delete cascade,
  sequence           bigint not null,
  client_op_id       uuid not null,
  image_id           uuid not null references public.images(id) on delete cascade,
  annotation_uid     text not null,
  operation          text not null,
  base_version       int not null,
  object_version     int not null,
  request_payload    jsonb,
  annotation_payload jsonb not null,
  actor_id           uuid not null references public.profiles(id),
  created_at         timestamptz not null default now(),
  constraint annotation_events_sequence_positive check (sequence > 0),
  constraint annotation_events_base_version_nonnegative check (base_version >= 0),
  constraint annotation_events_object_version_positive check (object_version > 0),
  constraint annotation_events_operation_valid
    check (operation in ('create', 'modify', 'class_change', 'delete')),
  unique (dataset_id, sequence),
  unique (dataset_id, client_op_id)
);

alter table public.annotation_events
  add column if not exists request_payload jsonb;

create index if not exists idx_annotation_events_dataset_sequence
  on public.annotation_events(dataset_id, sequence);
create index if not exists idx_annotation_events_image_sequence
  on public.annotation_events(image_id, sequence);
create index if not exists idx_annotation_events_annotation
  on public.annotation_events(image_id, annotation_uid, object_version);

alter table public.annotation_events enable row level security;

drop policy if exists annotation_events_select on public.annotation_events;
create policy annotation_events_select on public.annotation_events
  for select to authenticated
  using (is_team_member(dataset_team(dataset_id)));

-- Annotation mutasyonlari artik yalnizca asagidaki RPC'den gecmelidir.
drop policy if exists annotations_write on public.annotations;
revoke insert, update, delete on table public.annotations from anon, authenticated;
revoke insert, update, delete on table public.annotation_events from anon, authenticated;
grant select on table public.annotation_events to authenticated;

create or replace function public.apply_annotation_operation(
  p_dataset_id uuid,
  p_image_id uuid,
  p_client_op_id uuid,
  p_annotation_uid uuid,
  p_operation text,
  p_base_version int,
  p_annotation jsonb
)
returns table (
  result_status text,
  result_sequence bigint,
  result_object_version int,
  result_annotation jsonb,
  result_was_duplicate boolean
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_actor uuid := auth.uid();
  v_team_id uuid;
  v_locked_sequence bigint;
  v_annotation public.annotations%rowtype;
  v_event public.annotation_events%rowtype;
  v_payload jsonb;
  v_request_payload jsonb;
  v_class_index int;
  v_type text;
  v_data jsonb;
begin
  if v_actor is null then
    raise exception using
      errcode = '28000',
      message = 'authentication_required';
  end if;

  if p_client_op_id is null or p_annotation_uid is null then
    raise exception using
      errcode = '22023',
      message = 'operation_identity_required';
  end if;

  if p_operation is null
     or p_operation not in ('create', 'modify', 'class_change', 'delete') then
    raise exception using
      errcode = '22023',
      message = 'invalid_annotation_operation';
  end if;

  if p_base_version is null or p_base_version < 0 then
    raise exception using
      errcode = '22023',
      message = 'invalid_base_version';
  end if;

  v_request_payload := case
    when p_operation = 'delete' then null
    else p_annotation
  end;

  select d.team_id into v_team_id
  from public.datasets d
  where d.id = p_dataset_id;

  if v_team_id is null then
    raise exception using
      errcode = 'P0002',
      message = 'dataset_not_found';
  end if;

  if not public.has_team_role(
    v_team_id,
    array['owner', 'admin', 'annotator']::team_role[]
  ) then
    raise exception using
      errcode = '42501',
      message = 'annotation_write_forbidden';
  end if;

  -- Dataset satiri tum islemleri siralar ve sequence artisini atomik tutar.
  select d.collaboration_sequence into v_locked_sequence
  from public.datasets d
  where d.id = p_dataset_id
  for update;

  -- Kilit alindiktan sonra kontrol edilir; ayni client_op_id yarisi tek sonuc verir.
  select e.* into v_event
  from public.annotation_events e
  where e.dataset_id = p_dataset_id
    and e.client_op_id = p_client_op_id;

  if found then
    if v_event.image_id <> p_image_id
       or v_event.annotation_uid <> p_annotation_uid::text
       or v_event.operation <> p_operation
       or v_event.base_version <> p_base_version
       or v_event.request_payload is distinct from v_request_payload then
      raise exception using
        errcode = '22023',
        message = 'idempotency_key_reused';
    end if;

    return query select
      'applied'::text,
      v_event.sequence,
      v_event.object_version,
      v_event.annotation_payload,
      true;
    return;
  end if;

  if not exists (
    select 1 from public.images i
    where i.id = p_image_id and i.dataset_id = p_dataset_id
  ) then
    raise exception using
      errcode = '22023',
      message = 'image_dataset_mismatch';
  end if;

  if p_operation = 'create' and p_base_version <> 0 then
    raise exception using
      errcode = '22023',
      message = 'create_requires_base_version_zero';
  end if;

  if p_operation <> 'delete' then
    if p_annotation is null or jsonb_typeof(p_annotation) <> 'object' then
      raise exception using
        errcode = '22023',
        message = 'annotation_payload_required';
    end if;

    if p_annotation->>'uid' is distinct from p_annotation_uid::text then
      raise exception using
        errcode = '22023',
        message = 'annotation_uid_mismatch';
    end if;

    if jsonb_typeof(p_annotation->'class_index') is distinct from 'number'
       or jsonb_typeof(p_annotation->'data') is distinct from 'object' then
      raise exception using
        errcode = '22023',
        message = 'invalid_annotation_payload';
    end if;

    v_class_index := (p_annotation->>'class_index')::int;
    v_type := p_annotation->>'type';
    v_data := p_annotation->'data';

    if v_class_index < 0
       or v_type is null
       or v_type not in ('bbox', 'polygon', 'obb', 'keypoints', 'classify') then
      raise exception using
        errcode = '22023',
        message = 'invalid_annotation_payload';
    end if;
  end if;

  if p_operation = 'create' then
    select a.* into v_annotation
    from public.annotations a
    where a.image_id = p_image_id
      and a.uid = p_annotation_uid::text;

    if found then
      v_payload := jsonb_build_object(
        'uid', v_annotation.uid,
        'class_index', v_annotation.class_index,
        'type', v_annotation.type,
        'data', v_annotation.data,
        'version', v_annotation.version,
        'is_deleted', v_annotation.is_deleted,
        'deleted_at', v_annotation.deleted_at,
        'updated_by', v_annotation.updated_by
      );
      return query select
        'conflict'::text,
        null::bigint,
        v_annotation.version,
        v_payload,
        false;
      return;
    end if;

    insert into public.annotations (
      image_id, uid, class_index, type, data, version,
      updated_by, updated_at, is_deleted, deleted_at
    ) values (
      p_image_id, p_annotation_uid::text, v_class_index, v_type, v_data, 1,
      v_actor, now(), false, null
    )
    returning * into v_annotation;
  elsif p_operation = 'modify' then
    update public.annotations a set
      class_index = v_class_index,
      data = v_data,
      version = a.version + 1,
      updated_by = v_actor,
      updated_at = now()
    where a.image_id = p_image_id
      and a.uid = p_annotation_uid::text
      and a.version = p_base_version
      and a.type = v_type
      and a.is_deleted = false
    returning * into v_annotation;

    if not found then
      select a.* into v_annotation
      from public.annotations a
      where a.image_id = p_image_id
        and a.uid = p_annotation_uid::text;

      if found then
        v_payload := jsonb_build_object(
          'uid', v_annotation.uid,
          'class_index', v_annotation.class_index,
          'type', v_annotation.type,
          'data', v_annotation.data,
          'version', v_annotation.version,
          'is_deleted', v_annotation.is_deleted,
          'deleted_at', v_annotation.deleted_at,
          'updated_by', v_annotation.updated_by
        );
        return query select
          'conflict'::text,
          null::bigint,
          v_annotation.version,
          v_payload,
          false;
      else
        return query select
          'conflict'::text,
          null::bigint,
          null::int,
          null::jsonb,
          false;
      end if;
      return;
    end if;
  elsif p_operation = 'class_change' then
    update public.annotations a set
      class_index = v_class_index,
      version = a.version + 1,
      updated_by = v_actor,
      updated_at = now()
    where a.image_id = p_image_id
      and a.uid = p_annotation_uid::text
      and a.version = p_base_version
      and a.type = v_type
      and a.data = v_data
      and a.is_deleted = false
    returning * into v_annotation;

    if not found then
      select a.* into v_annotation
      from public.annotations a
      where a.image_id = p_image_id
        and a.uid = p_annotation_uid::text;

      if found then
        v_payload := jsonb_build_object(
          'uid', v_annotation.uid,
          'class_index', v_annotation.class_index,
          'type', v_annotation.type,
          'data', v_annotation.data,
          'version', v_annotation.version,
          'is_deleted', v_annotation.is_deleted,
          'deleted_at', v_annotation.deleted_at,
          'updated_by', v_annotation.updated_by
        );
        return query select
          'conflict'::text,
          null::bigint,
          v_annotation.version,
          v_payload,
          false;
      else
        return query select
          'conflict'::text,
          null::bigint,
          null::int,
          null::jsonb,
          false;
      end if;
      return;
    end if;
  else
    update public.annotations a set
      version = a.version + 1,
      updated_by = v_actor,
      updated_at = now(),
      is_deleted = true,
      deleted_at = now()
    where a.image_id = p_image_id
      and a.uid = p_annotation_uid::text
      and a.version = p_base_version
      and a.is_deleted = false
    returning * into v_annotation;

    if not found then
      select a.* into v_annotation
      from public.annotations a
      where a.image_id = p_image_id
        and a.uid = p_annotation_uid::text;

      if found then
        v_payload := jsonb_build_object(
          'uid', v_annotation.uid,
          'class_index', v_annotation.class_index,
          'type', v_annotation.type,
          'data', v_annotation.data,
          'version', v_annotation.version,
          'is_deleted', v_annotation.is_deleted,
          'deleted_at', v_annotation.deleted_at,
          'updated_by', v_annotation.updated_by
        );
        return query select
          'conflict'::text,
          null::bigint,
          v_annotation.version,
          v_payload,
          false;
      else
        return query select
          'conflict'::text,
          null::bigint,
          null::int,
          null::jsonb,
          false;
      end if;
      return;
    end if;
  end if;

  v_payload := jsonb_build_object(
    'uid', v_annotation.uid,
    'class_index', v_annotation.class_index,
    'type', v_annotation.type,
    'data', v_annotation.data,
    'version', v_annotation.version,
    'is_deleted', v_annotation.is_deleted,
    'deleted_at', v_annotation.deleted_at,
    'updated_by', v_annotation.updated_by
  );

  update public.datasets d set
    collaboration_sequence = d.collaboration_sequence + 1
  where d.id = p_dataset_id
  returning d.collaboration_sequence into v_locked_sequence;

  insert into public.annotation_events (
    dataset_id, sequence, client_op_id, image_id, annotation_uid,
    operation, base_version, object_version, request_payload,
    annotation_payload, actor_id
  ) values (
    p_dataset_id, v_locked_sequence, p_client_op_id, p_image_id,
    p_annotation_uid::text, p_operation, p_base_version,
    v_annotation.version, v_request_payload, v_payload, v_actor
  )
  returning * into v_event;

  return query select
    'applied'::text,
    v_event.sequence,
    v_event.object_version,
    v_event.annotation_payload,
    false;
end;
$$;

revoke all on function public.apply_annotation_operation(
  uuid, uuid, uuid, uuid, text, int, jsonb
) from public, anon;
grant execute on function public.apply_annotation_operation(
  uuid, uuid, uuid, uuid, text, int, jsonb
) to authenticated;

-- =============================================================
-- Migration sonu
-- =============================================================
