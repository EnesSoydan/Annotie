-- =============================================================
-- Annotie P0/3: Legacy label_content -> nesne bazli collaboration v2
-- 0001-0005'ten SONRA calistirin.
-- =============================================================

alter table public.datasets
  add column if not exists collab_schema_version int not null default 1;

alter table public.images
  add column if not exists annotations_migrated_at timestamptz;

do $$ begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'datasets_collab_schema_version_valid'
      and conrelid = 'public.datasets'::regclass
  ) then
    alter table public.datasets
      add constraint datasets_collab_schema_version_valid
      check (collab_schema_version in (1, 2));
  end if;
end $$;

create or replace function public.annotation_yolo_line(
  p_class_index int,
  p_type text,
  p_data jsonb
)
returns text
language plpgsql
immutable
strict
set search_path = public
as $$
declare
  v_line text;
  v_coords text;
begin
  if p_class_index < 0 then
    raise exception using errcode = '22023', message = 'invalid_class_index';
  end if;

  if p_type = 'classify' then
    return p_class_index::text;
  elsif p_type = 'bbox' then
    v_line := p_class_index::text || ' '
      || to_char((p_data->>'x_center')::numeric, 'FM0.000000') || ' '
      || to_char((p_data->>'y_center')::numeric, 'FM0.000000') || ' '
      || to_char((p_data->>'width')::numeric, 'FM0.000000') || ' '
      || to_char((p_data->>'height')::numeric, 'FM0.000000');
  elsif p_type = 'polygon' then
    select string_agg(
      to_char((point->>0)::numeric, 'FM0.000000') || ' '
      || to_char((point->>1)::numeric, 'FM0.000000'),
      ' ' order by ordinality
    ) into v_coords
    from jsonb_array_elements(p_data->'points') with ordinality as p(point, ordinality);
    v_line := p_class_index::text || ' ' || v_coords;
  elsif p_type = 'obb' then
    select string_agg(
      to_char((corner->>0)::numeric, 'FM0.000000') || ' '
      || to_char((corner->>1)::numeric, 'FM0.000000'),
      ' ' order by ordinality
    ) into v_coords
    from jsonb_array_elements(p_data->'corners') with ordinality as c(corner, ordinality);
    v_line := p_class_index::text || ' ' || v_coords;
  elsif p_type = 'keypoints' then
    select string_agg(
      to_char((point->>0)::numeric, 'FM0.000000') || ' '
      || to_char((point->>1)::numeric, 'FM0.000000') || ' '
      || (point->>2)::int::text,
      ' ' order by ordinality
    ) into v_coords
    from jsonb_array_elements(p_data->'keypoints') with ordinality as p(point, ordinality);
    v_line := p_class_index::text || ' '
      || to_char((p_data->>'x_center')::numeric, 'FM0.000000') || ' '
      || to_char((p_data->>'y_center')::numeric, 'FM0.000000') || ' '
      || to_char((p_data->>'width')::numeric, 'FM0.000000') || ' '
      || to_char((p_data->>'height')::numeric, 'FM0.000000') || ' '
      || v_coords;
  else
    raise exception using errcode = '22023', message = 'invalid_annotation_type';
  end if;

  if v_line is null or btrim(v_line) = '' then
    raise exception using errcode = '22023', message = 'invalid_annotation_data';
  end if;
  return v_line;
end;
$$;

create or replace function public.refresh_image_label_snapshot(
  p_image_id uuid,
  p_actor uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_content text;
begin
  select string_agg(
    public.annotation_yolo_line(a.class_index, a.type, a.data),
    E'\n' order by a.created_at, a.id
  ) into v_content
  from public.annotations a
  where a.image_id = p_image_id
    and a.is_deleted = false;

  if coalesce(v_content, '') <> '' then
    v_content := v_content || E'\n';
  else
    v_content := '';
  end if;

  update public.images set
    label_content = v_content,
    label_updated_by = p_actor,
    label_updated_at = now()
  where id = p_image_id;
end;
$$;

create or replace function public.refresh_image_label_snapshot_trigger()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_image_id uuid;
  v_actor uuid;
begin
  if tg_op = 'DELETE' then
    v_image_id := old.image_id;
    v_actor := coalesce(old.updated_by, auth.uid());
  else
    v_image_id := new.image_id;
    v_actor := coalesce(new.updated_by, auth.uid());
  end if;

  perform public.refresh_image_label_snapshot(
    v_image_id,
    v_actor
  );
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

drop trigger if exists annotation_refresh_label_snapshot on public.annotations;
create trigger annotation_refresh_label_snapshot
  after insert or delete or update of class_index, type, data, is_deleted
  on public.annotations
  for each row execute function public.refresh_image_label_snapshot_trigger();

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

  if v_migrated_at is not null then
    select count(*)::int into v_count
    from public.annotations a
    where a.image_id = p_image_id and a.is_deleted = false;
    return v_count;
  end if;

  -- V1'de label_content tek dogruluk kaynagiydi; yarim/eski satirlari degistir.
  delete from public.annotations where image_id = p_image_id;

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

create or replace function public.finalize_dataset_collab_v2(p_dataset_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_actor uuid := auth.uid();
  v_team_id uuid;
begin
  if v_actor is null then
    raise exception using errcode = '28000', message = 'authentication_required';
  end if;

  select d.team_id into v_team_id
  from public.datasets d
  where d.id = p_dataset_id
  for update;
  if v_team_id is null then
    raise exception using errcode = 'P0002', message = 'dataset_not_found';
  end if;
  if not public.has_team_role(
    v_team_id, array['owner', 'admin', 'annotator']::team_role[]
  ) then
    raise exception using errcode = '42501', message = 'annotation_write_forbidden';
  end if;

  if exists (
    select 1 from public.images i
    where i.dataset_id = p_dataset_id
      and i.annotations_migrated_at is null
  ) then
    raise exception using errcode = '55000', message = 'dataset_migration_incomplete';
  end if;

  update public.datasets set collab_schema_version = 2
  where id = p_dataset_id;
end;
$$;

revoke all on function public.annotation_yolo_line(int, text, jsonb)
  from public, anon, authenticated;
revoke all on function public.refresh_image_label_snapshot(uuid, uuid)
  from public, anon, authenticated;
revoke all on function public.refresh_image_label_snapshot_trigger()
  from public, anon, authenticated;
revoke all on function public.migrate_image_annotations_v2(uuid, uuid, jsonb)
  from public, anon;
revoke all on function public.finalize_dataset_collab_v2(uuid)
  from public, anon;
grant execute on function public.migrate_image_annotations_v2(uuid, uuid, jsonb)
  to authenticated;
grant execute on function public.finalize_dataset_collab_v2(uuid)
  to authenticated;

-- =============================================================
-- Migration sonu
-- =============================================================
