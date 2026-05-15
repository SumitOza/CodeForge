-- CodeForge Supabase Schema
-- Run this in the Supabase SQL editor once

create table if not exists users (
  id            uuid primary key,
  email         text unique not null,
  hashed_password text not null,
  full_name     text not null,
  created_at    timestamptz default now(),
  total_builds  int default 0,
  total_tokens_used bigint default 0
);

create table if not exists api_keys (
  id            uuid primary key,
  user_id       uuid references users(id) on delete cascade,
  provider      text not null,
  encrypted_key text not null,
  key_preview   text not null,
  created_at    timestamptz default now(),
  unique(user_id, provider)
);

create table if not exists build_sessions (
  id            uuid primary key,
  user_id       uuid references users(id) on delete cascade,
  prompt        text not null,
  status        text default 'planning',
  plan          jsonb,
  files_done    text[] default '{}',
  files_failed  text[] default '{}',
  total_tokens  int default 0,
  started_at    double precision,
  completed_at  double precision
);

create table if not exists usage_logs (
  id            uuid primary key,
  user_id       uuid references users(id) on delete cascade,
  session_id    uuid references build_sessions(id) on delete cascade,
  agent         text,
  provider      text,
  model_id      text,
  tokens        int default 0,
  logged_at     timestamptz default now()
);

-- Indexes
create index if not exists idx_api_keys_user on api_keys(user_id);
create index if not exists idx_sessions_user on build_sessions(user_id);
create index if not exists idx_usage_user on usage_logs(user_id);
create index if not exists idx_usage_session on usage_logs(session_id);

-- Row Level Security (optional but recommended)
alter table users enable row level security;
alter table api_keys enable row level security;
alter table build_sessions enable row level security;
alter table usage_logs enable row level security;
