-- Focus Grid MVP schema (tasks + push subscriptions + RLS)

create extension if not exists pgcrypto;

create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(trim(title)) > 0),
  status text not null default 'todo' check (status in ('todo', 'done')),
  priority text not null default 'normal' check (priority in ('high', 'medium', 'normal')),
  tags text[] not null default '{}',
  scheduled_date date,
  due_time time,
  estimate_minutes integer,
  energy text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  original_scheduled_date date,
  timezone text not null default 'UTC',
  top3_slot smallint check (top3_slot is null or top3_slot between 1 and 3),
  last_notified_at timestamptz
);

create table if not exists public.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  endpoint text not null,
  p256dh text not null,
  auth text not null,
  user_agent text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, endpoint)
);

create index if not exists tasks_user_updated_at_idx on public.tasks (user_id, updated_at desc);
create index if not exists tasks_user_schedule_idx on public.tasks (user_id, scheduled_date, due_time);
create index if not exists tasks_due_scan_idx on public.tasks (status, scheduled_date, due_time, last_notified_at);
create unique index if not exists tasks_user_top3_slot_idx on public.tasks (user_id, top3_slot) where top3_slot is not null;
create index if not exists push_subscriptions_user_idx on public.push_subscriptions (user_id);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists tasks_set_updated_at on public.tasks;
create trigger tasks_set_updated_at
before update on public.tasks
for each row
execute procedure public.set_updated_at();

drop trigger if exists push_subscriptions_set_updated_at on public.push_subscriptions;
create trigger push_subscriptions_set_updated_at
before update on public.push_subscriptions
for each row
execute procedure public.set_updated_at();

alter table public.tasks enable row level security;
alter table public.push_subscriptions enable row level security;

create policy "tasks_select_own"
on public.tasks
for select
to authenticated
using (auth.uid() = user_id);

create policy "tasks_insert_own"
on public.tasks
for insert
to authenticated
with check (auth.uid() = user_id);

create policy "tasks_update_own"
on public.tasks
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create policy "tasks_delete_own"
on public.tasks
for delete
to authenticated
using (auth.uid() = user_id);

create policy "push_subscriptions_select_own"
on public.push_subscriptions
for select
to authenticated
using (auth.uid() = user_id);

create policy "push_subscriptions_insert_own"
on public.push_subscriptions
for insert
to authenticated
with check (auth.uid() = user_id);

create policy "push_subscriptions_update_own"
on public.push_subscriptions
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create policy "push_subscriptions_delete_own"
on public.push_subscriptions
for delete
to authenticated
using (auth.uid() = user_id);

grant usage on schema public to authenticated;
grant all on public.tasks to authenticated;
grant all on public.push_subscriptions to authenticated;

-- Needed for realtime sync client-side.
do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'tasks'
  ) then
    alter publication supabase_realtime add table public.tasks;
  end if;
end;
$$;

create or replace function public.task_due_at_utc(task_row public.tasks)
returns timestamptz
language sql
stable
as $$
  select case
    when task_row.scheduled_date is null or task_row.due_time is null then null
    else make_timestamptz(
      extract(year from task_row.scheduled_date)::int,
      extract(month from task_row.scheduled_date)::int,
      extract(day from task_row.scheduled_date)::int,
      extract(hour from task_row.due_time)::int,
      extract(minute from task_row.due_time)::int,
      extract(second from task_row.due_time),
      coalesce(nullif(task_row.timezone, ''), 'UTC')
    )
  end;
$$;

create or replace function public.get_due_tasks(window_minutes integer default 5)
returns table (
  id uuid,
  user_id uuid,
  title text,
  scheduled_date date,
  due_time time,
  timezone text,
  due_at timestamptz
)
language sql
security definer
set search_path = public
as $$
  with bounds as (
    select
      now() as start_at,
      now() + make_interval(mins => greatest(window_minutes, 1)) as end_at
  )
  select
    t.id,
    t.user_id,
    t.title,
    t.scheduled_date,
    t.due_time,
    t.timezone,
    public.task_due_at_utc(t) as due_at
  from public.tasks t
  cross join bounds b
  where t.status = 'todo'
    and t.scheduled_date is not null
    and t.due_time is not null
    and public.task_due_at_utc(t) >= b.start_at
    and public.task_due_at_utc(t) < b.end_at
    and (t.last_notified_at is null or t.last_notified_at < public.task_due_at_utc(t))
  order by due_at asc;
$$;

create or replace function public.mark_tasks_notified(task_ids uuid[])
returns void
language sql
security definer
set search_path = public
as $$
  update public.tasks
  set last_notified_at = now(),
      updated_at = now()
  where id = any(task_ids);
$$;

revoke all on function public.get_due_tasks(integer) from public;
revoke all on function public.mark_tasks_notified(uuid[]) from public;
grant execute on function public.get_due_tasks(integer) to service_role;
grant execute on function public.mark_tasks_notified(uuid[]) to service_role;
