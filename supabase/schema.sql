-- GridEdge accounts, picks and leaderboard.
--
-- Run this once against a new Supabase project (SQL Editor → paste → run).
-- It is written to be re-runnable: every object is created if absent and
-- policies are dropped before being recreated.
--
-- The shape to understand before reading:
--
--   picks is APPEND-ONLY and settlements is written only by the nightly job.
--   A bankroll is never stored — it is derived as
--
--       balance   = 100 + sum(profit) over settled picks
--       at risk   = sum(stake) over picks with no settlement yet
--       available = balance - at risk
--
--   Deriving it rather than keeping a running total is what makes regrading
--   safe: settle the same game twice and the answer is identical, and a bad
--   settlement is fixed by correcting one row instead of unwinding a balance.
--
--   Nothing outside this file may insert a pick. The browser has no INSERT
--   grant at all; picks arrive through place_pick(), called by the serverless
--   function at api/picks/create.py after it has checked the line against the
--   live sportsbook board and the kickoff against the server clock.

-- ---------------------------------------------------------------------------
-- Constants
-- ---------------------------------------------------------------------------

create schema if not exists app;

-- The leaderboard view runs under the caller's own permissions (see below), so
-- the roles that read it need to be able to call the constants it uses.
grant usage on schema app to anon, authenticated, service_role;

-- Every account opens with the same imaginary bankroll.
create or replace function app.starting_bankroll() returns numeric
  language sql immutable as $$ select 100::numeric $$;

-- ROI is profit over coins staked, so one tiny winning longshot would
-- otherwise hold first place all season having risked nothing. The floor is on
-- coins staked rather than picks made, so a single large bet still qualifies —
-- taking the top spot with one brave pick is the point, doing it for free is not.
create or replace function app.roi_qualifying_stake() returns numeric
  language sql immutable as $$ select 25::numeric $$;

grant execute on function app.starting_bankroll(), app.roi_qualifying_stake()
  to anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table if not exists public.profiles (
  id          uuid primary key references auth.users on delete cascade,
  username    text not null unique
                check (username ~ '^[A-Za-z0-9][A-Za-z0-9_]{2,19}$'),
  created_at  timestamptz not null default now()
);

-- Case-insensitive uniqueness: "Ferris" and "ferris" must not both exist, or
-- the leaderboard becomes an impersonation surface.
create unique index if not exists profiles_username_lower_idx
  on public.profiles (lower(username));

-- The only way back into an account whose password is forgotten.
--
-- There is no email address on file to send a reset link to — that is the
-- whole point of the sign-up flow — so each account is handed a one-time
-- recovery code instead, shown once at registration and never again. Only its
-- hash lives here, so possession of this table does not grant possession of
-- an account.
--
-- No role but service_role may read it. RLS is on with no policies at all,
-- which denies anon and authenticated by default even if a grant were ever
-- added by mistake.
create table if not exists public.recovery (
  user_id     uuid primary key references public.profiles(id) on delete cascade,
  code_hash   text not null,
  created_at  timestamptz not null default now(),
  rotated_at  timestamptz
);

create table if not exists public.picks (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.profiles(id) on delete cascade,

  player      text not null,
  team        text not null,
  opponent    text not null,
  stat        text not null,
  line        numeric(8,2) not null,
  side        text not null check (side in ('over', 'under')),

  -- Coins. numeric, never float: a bankroll that drifts by a hundredth every
  -- settlement is a bug nobody finds until the season is over.
  stake       numeric(12,2) not null check (stake >= 1),

  -- American odds as the books were posting them when the pick was taken. The
  -- client does not get to supply this; api/picks/create.py reads it off the
  -- board. Lines move, and a pick settles at the number that was on offer.
  price       integer not null check (abs(price) >= 100),
  book        text,

  event_id    text,
  season      integer not null,

  -- The deadline, from the odds provider's event feed rather than the browser.
  -- Note what is NOT stored: a week number. The client knows one, but a pick
  -- pointed at the wrong week settles against a game the player has already
  -- played, so the week is resolved by the settlement job from the real
  -- schedule instead of being accepted here. kickoff is the only time this
  -- table trusts, and it comes from the sportsbook feed.
  kickoff     timestamptz not null,

  -- What the model said at the time, so drift is visible afterwards.
  model_prob  numeric(6,5),
  created_at  timestamptz not null default now(),

  -- One pick per user per player/stat/line/side/game: a user may take both
  -- sides or several rungs of the ladder, but not the same rung twice.
  unique (user_id, event_id, player, stat, line, side)
);

create index if not exists picks_user_idx    on public.picks (user_id, created_at desc);
create index if not exists picks_kickoff_idx on public.picks (kickoff);

create table if not exists public.settlements (
  pick_id    uuid primary key references public.picks(id) on delete cascade,
  status     text not null check (status in ('hit', 'miss', 'void')),
  actual     numeric(8,2),
  -- Resolved from the real schedule at settlement time, for display only.
  week       integer,
  profit     numeric(12,2) not null default 0,
  graded_at  timestamptz not null default now()
);

-- Sportsbook responses, kept so the same credit is not spent twice.
--
-- These functions run as serverless handlers, so the in-process cache in
-- core/odds.py starts empty on most requests and the ten-minute window rarely
-- gets a chance to help. Persisting the responses is what makes it real: 500
-- credits a month is ample when a board everyone is looking at costs one
-- credit rather than one per cold start.
--
-- `key` is the cache key from core/odds.py ("props:<event>:<market>"), and the
-- payload is that call's response as fetched. Written only by the serverless
-- functions with the service key; nobody else may read it, because it is the
-- provider's data and redistributing it is what their terms forbid.
create table if not exists public.odds_snapshots (
  key         text primary key,
  payload     jsonb not null,
  fetched_at  timestamptz not null default now()
);

-- How many credits the provider says are left this billing period, so the
-- reserve in core/odds.py survives a cold start. One row, always.
create table if not exists public.odds_budget (
  id          integer primary key default 1 check (id = 1),
  remaining   integer,
  seen_at     timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Row-level security
--
-- Reads are open enough to render a public leaderboard; writes are closed
-- completely. There is no INSERT policy on picks or settlements by design —
-- the only paths in are the SECURITY DEFINER functions below.
-- ---------------------------------------------------------------------------

alter table public.profiles    enable row level security;
alter table public.picks       enable row level security;
alter table public.settlements enable row level security;
alter table public.recovery    enable row level security;
alter table public.odds_snapshots enable row level security;
alter table public.odds_budget    enable row level security;

-- Table privileges gate whether a role may attempt a statement at all; the
-- policies below decide which rows it then sees. Both are needed, and being
-- explicit here means this file doesn't depend on a project's default
-- privileges being untouched.
grant select on public.profiles, public.picks, public.settlements
  to anon, authenticated;

-- Note what the browser cannot do: create a profile. Registration happens in
-- api/account/register.py, which creates the auth user and the profile row
-- together, so an account can never exist in one of those two places only.
-- Nor may it rename: the username is half the sign-in identifier (see
-- core/accounts.py), and a rename that didn't also move the auth address
-- would lock the user out of their own account.
grant all on public.profiles, public.picks, public.settlements, public.recovery,
             public.odds_snapshots, public.odds_budget
  to service_role;

drop policy if exists profiles_read       on public.profiles;
drop policy if exists profiles_insert_own on public.profiles;
drop policy if exists profiles_update_own on public.profiles;

-- Usernames are public: they are the first column of the leaderboard. They are
-- also the only thing here that identifies anybody, because it is the only
-- thing the account was ever asked for.
create policy profiles_read on public.profiles
  for select using (true);

-- recovery, odds_snapshots and odds_budget get no policies whatsoever.
-- service_role bypasses RLS; everyone else is denied by having none to satisfy.
-- For the odds tables that is a licensing matter as much as a security one:
-- the provider permits storing and displaying their data, not serving it on.

drop policy if exists picks_read on public.picks;

-- Your own picks always; everyone else's only once the game has started.
-- Before kickoff a live pick is information — publishing it would turn the
-- leaderboard into a copy-trading feed and stop being a test of anyone's
-- judgement but the first mover's.
create policy picks_read on public.picks
  for select using (user_id = auth.uid() or kickoff <= now());

drop policy if exists settlements_read on public.settlements;

create policy settlements_read on public.settlements
  for select using (exists (
    select 1 from public.picks p
    where p.id = settlements.pick_id
      and (p.user_id = auth.uid() or p.kickoff <= now())
  ));

-- ---------------------------------------------------------------------------
-- Registration and recovery
-- ---------------------------------------------------------------------------

-- Bind a freshly created auth user to a username and a recovery code, in one
-- statement.
--
-- Called only by api/account/register.py, immediately after it has asked the
-- auth service for the user. Both rows or neither: an account that had an auth
-- user but no profile could sign in and never appear on the leaderboard, and
-- one with a profile but no recovery row would have no way back in — both are
-- states no user could get themselves out of.
create or replace function public.register_account(
  p_user      uuid,
  p_username  text,
  p_code_hash text
) returns public.profiles
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.profiles;
begin
  insert into public.profiles (id, username) values (p_user, p_username)
  returning * into v_row;

  insert into public.recovery (user_id, code_hash) values (p_user, p_code_hash);

  return v_row;
end;
$$;

-- Replace an account's recovery code, after one has been spent.
--
-- A recovery code is single-use in effect: recover.py verifies the old one,
-- sets the new password, then calls this with a fresh code. Rotating rather
-- than clearing means a user is never left with an account that has no way
-- back in — they finish the reset holding a code again.
create or replace function public.rotate_recovery(
  p_user      uuid,
  p_code_hash text
) returns void
language sql
security definer
set search_path = public
as $$
  insert into public.recovery (user_id, code_hash, rotated_at)
  values (p_user, p_code_hash, now())
  on conflict (user_id) do update
    set code_hash = excluded.code_hash, rotated_at = now();
$$;

-- Look an account up by name, case-insensitively, for sign-up's "is this taken"
-- check and for the recovery flow.
--
-- A function rather than a PostgREST filter on purpose: matching a username
-- through the REST API would mean `ilike`, and `_` is both a legal username
-- character here and a single-character wildcard there — so `foo_bar` would
-- quietly match `fooXbar` and hand the wrong account's recovery hash back.
create or replace function public.account_by_username(p_username text)
returns table (id uuid, username text, code_hash text)
language sql
security definer
set search_path = public
as $$
  select p.id, p.username, r.code_hash
    from public.profiles p
    left join public.recovery r on r.user_id = p.id
   where lower(p.username) = lower(trim(p_username));
$$;

-- As with place_pick: these trust what they are handed, so only the caller
-- that earned that trust may call them.
revoke all on function public.register_account(uuid, text, text)
  from public, anon, authenticated;
revoke all on function public.rotate_recovery(uuid, text)
  from public, anon, authenticated;
revoke all on function public.account_by_username(text)
  from public, anon, authenticated;

grant execute on function public.register_account(uuid, text, text) to service_role;
grant execute on function public.rotate_recovery(uuid, text)        to service_role;
grant execute on function public.account_by_username(text)          to service_role;

-- ---------------------------------------------------------------------------
-- Placing a pick
-- ---------------------------------------------------------------------------

-- Called only by the serverless function, with the service key, after the line
-- and price have been checked against the live board.
--
-- The balance check and the insert must happen in one transaction or two
-- requests arriving together can each see the same coins and both spend them.
-- The row lock on profiles is what serialises them.
create or replace function public.place_pick(
  p_user       uuid,
  p_player     text,
  p_team       text,
  p_opponent   text,
  p_stat       text,
  p_line       numeric,
  p_side       text,
  p_stake      numeric,
  p_price      integer,
  p_book       text,
  p_event_id   text,
  p_season     integer,
  p_kickoff    timestamptz,
  p_model_prob numeric
) returns public.picks
language plpgsql
security definer
set search_path = public, app
as $$
declare
  v_balance   numeric;
  v_at_risk   numeric;
  v_available numeric;
  v_row       public.picks;
begin
  if p_kickoff is null or p_kickoff <= now() then
    raise exception 'PICK_LOCKED' using errcode = 'P0001';
  end if;

  if p_stake < 1 then
    raise exception 'STAKE_TOO_SMALL' using errcode = 'P0001';
  end if;

  -- Serialise this user's concurrent submissions.
  perform 1 from public.profiles where id = p_user for update;
  if not found then
    raise exception 'NO_PROFILE' using errcode = 'P0001';
  end if;

  select app.starting_bankroll()
       + coalesce(sum(s.profit) filter (where s.status in ('hit', 'miss')), 0)
    into v_balance
    from public.picks k
    left join public.settlements s on s.pick_id = k.id
   where k.user_id = p_user;

  select coalesce(sum(k.stake), 0)
    into v_at_risk
    from public.picks k
    left join public.settlements s on s.pick_id = k.id
   where k.user_id = p_user and s.pick_id is null;

  v_available := v_balance - v_at_risk;

  if p_stake > v_available then
    raise exception 'INSUFFICIENT_FUNDS:%', round(v_available, 2) using errcode = 'P0001';
  end if;

  insert into public.picks (
    user_id, player, team, opponent, stat, line, side, stake, price, book,
    event_id, season, kickoff, model_prob
  ) values (
    p_user, p_player, p_team, p_opponent, p_stat, p_line, p_side, p_stake, p_price, p_book,
    p_event_id, p_season, p_kickoff, p_model_prob
  )
  returning * into v_row;

  return v_row;
end;
$$;

-- No one signed in may call this directly: it trusts the price it is handed,
-- and the only caller that has earned that trust is api/picks/create.py, which
-- read the price off the sportsbook board itself.
revoke all on function public.place_pick(
  uuid, text, text, text, text, numeric, text, numeric, integer, text, text,
  integer, timestamptz, numeric
) from public, anon, authenticated;

grant execute on function public.place_pick(
  uuid, text, text, text, text, numeric, text, numeric, integer, text, text,
  integer, timestamptz, numeric
) to service_role;

-- ---------------------------------------------------------------------------
-- Settling a pick
-- ---------------------------------------------------------------------------

-- Profit is derived here from the pick's own stake and price rather than
-- accepted from the caller, so a settlement can never disagree with the ticket
-- it settles. The grader supplies only what it actually observed: the status
-- and the player's real number.
create or replace function public.settle_pick(
  p_pick_id uuid,
  p_status  text,
  p_actual  numeric,
  p_week    integer default null
) returns public.settlements
language plpgsql
security definer
set search_path = public
as $$
declare
  v_pick   public.picks;
  v_profit numeric;
  v_row    public.settlements;
begin
  select * into v_pick from public.picks where id = p_pick_id;
  if not found then
    raise exception 'NO_SUCH_PICK' using errcode = 'P0001';
  end if;

  v_profit := case
    when p_status = 'hit' and v_pick.price > 0 then v_pick.stake * (v_pick.price / 100.0)
    when p_status = 'hit'                      then v_pick.stake * (100.0 / abs(v_pick.price))
    when p_status = 'miss'                     then -v_pick.stake
    else 0
  end;

  insert into public.settlements (pick_id, status, actual, week, profit, graded_at)
  values (p_pick_id, p_status, p_actual, p_week, round(v_profit, 2), now())
  on conflict (pick_id) do update
    set status = excluded.status,
        actual = excluded.actual,
        week = excluded.week,
        profit = excluded.profit,
        graded_at = excluded.graded_at
  returning * into v_row;

  return v_row;
end;
$$;

-- Likewise: only the settlement job settles anything.
revoke all on function public.settle_pick(uuid, text, numeric, integer)
  from public, anon, authenticated;

grant execute on function public.settle_pick(uuid, text, numeric, integer)
  to service_role;

-- ---------------------------------------------------------------------------
-- The leaderboard
-- ---------------------------------------------------------------------------

-- security_invoker: the view runs under the caller's RLS, so it aggregates
-- exactly the picks that caller may read. Settled picks are past kickoff and
-- therefore visible to everyone, which is what makes the board public and
-- consistent — nobody sees a different total from anybody else.
create or replace view public.leaderboard
with (security_invoker = on) as
select
  p.id                                                                as user_id,
  p.username,
  count(*) filter (where s.status = 'hit')::int                       as hits,
  count(*) filter (where s.status = 'miss')::int                      as misses,
  count(*) filter (where s.status = 'void')::int                      as voids,
  count(*) filter (where s.pick_id is null)::int                      as pending,
  coalesce(sum(s.profit) filter (where s.status in ('hit','miss')), 0) as profit,
  coalesce(sum(k.stake)  filter (where s.status in ('hit','miss')), 0) as staked,
  app.starting_bankroll()
    + coalesce(sum(s.profit) filter (where s.status in ('hit','miss')), 0) as balance,
  -- Null until there is enough staked to mean something; the UI ranks these
  -- below everyone who qualifies rather than hiding them.
  case
    when coalesce(sum(k.stake) filter (where s.status in ('hit','miss')), 0)
         >= app.roi_qualifying_stake()
    then round(
      coalesce(sum(s.profit) filter (where s.status in ('hit','miss')), 0)
      / nullif(sum(k.stake) filter (where s.status in ('hit','miss')), 0), 4)
  end                                                                  as roi,
  coalesce(sum(k.stake) filter (where s.status in ('hit','miss')), 0)
    >= app.roi_qualifying_stake()                                      as roi_qualified,
  app.roi_qualifying_stake()                                           as roi_threshold
from public.profiles p
left join public.picks k       on k.user_id = p.id
left join public.settlements s on s.pick_id = k.id
group by p.id, p.username;

grant select on public.leaderboard to anon, authenticated;

-- ---------------------------------------------------------------------------
-- The settlement job's work queue
-- ---------------------------------------------------------------------------

-- Picks whose game has started and which nothing has graded yet. Read only by
-- scripts/settle_picks.py with the service key; deliberately not granted to
-- anon or authenticated, who have no reason to enumerate it.
create or replace view public.pending_settlement
with (security_invoker = on) as
select k.*
from public.picks k
left join public.settlements s on s.pick_id = k.id
where s.pick_id is null and k.kickoff <= now();

grant select on public.pending_settlement to service_role;
