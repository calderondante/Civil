-- Single private workspace. Only trusted backend/worker connect to these tables.
-- Run in your own Supabase SQL editor before starting the backend.
create table if not exists public.aas_episodes (
 id varchar(36) primary key, revision integer not null default 1, data json not null
);
create table if not exists public.aas_revisions (
 id varchar(80) primary key, episode_id varchar(36) not null, data json not null
);
create index if not exists ix_aas_revisions_episode_id on public.aas_revisions(episode_id);
create table if not exists public.aas_jobs (
 id varchar(36) primary key, episode_id varchar(36) not null,
 status varchar(20) not null default 'queued', lease_until double precision not null default 0,
 lease_token varchar(36) not null default '', attempts integer not null default 0,
 payload json not null, result json not null default '{}', error varchar(500) not null default ''
);
create index if not exists ix_aas_jobs_episode_id on public.aas_jobs(episode_id);
create index if not exists ix_aas_jobs_status on public.aas_jobs(status);
alter table public.aas_episodes enable row level security;
alter table public.aas_revisions enable row level security;
alter table public.aas_jobs enable row level security;
revoke all on public.aas_episodes, public.aas_revisions, public.aas_jobs from anon, authenticated;
-- No permissive policies: browser users must pass through the authenticated backend.
insert into storage.buckets (id,name,public) values ('academic-audio','academic-audio',false)
on conflict (id) do nothing;
-- No anonymous storage policy. Backend uses service_role; never ship that key to Vercel clients.
create unique index if not exists uq_aas_jobs_active_episode on public.aas_jobs(episode_id)
 where status in ('queued','running');
