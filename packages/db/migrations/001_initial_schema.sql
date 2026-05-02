create table if not exists market_snapshots (
  id text primary key,
  ticker text not null,
  snapshot_time timestamptz not null,
  last_price numeric(18, 4) not null,
  best_bid numeric(18, 4) not null,
  best_ask numeric(18, 4) not null,
  bid_depth numeric(18, 4) not null,
  ask_depth numeric(18, 4) not null,
  volume numeric(20, 4) not null,
  total_turnover numeric(20, 4) not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists market_snapshots_ticker_time_idx
  on market_snapshots (ticker, snapshot_time);

create table if not exists candles (
  id text primary key,
  ticker text not null,
  timeframe text not null,
  candle_time timestamptz not null,
  open numeric(18, 4) not null,
  high numeric(18, 4) not null,
  low numeric(18, 4) not null,
  close numeric(18, 4) not null,
  volume numeric(20, 4) not null,
  vwap numeric(18, 4),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists candles_ticker_timeframe_time_idx
  on candles (ticker, timeframe, candle_time);

create table if not exists signals (
  id text primary key,
  ticker text not null,
  strategy text not null,
  direction text not null,
  status text not null,
  entry_zone_low numeric(18, 4) not null,
  entry_zone_high numeric(18, 4) not null,
  stop_loss numeric(18, 4) not null,
  target1 numeric(18, 4),
  target2 numeric(18, 4),
  confidence numeric(8, 4),
  valid_until timestamptz not null,
  features jsonb not null default '{}'::jsonb,
  status_reason text,
  latest_price numeric(18, 4),
  max_favorable_move_percent numeric(12, 6),
  max_adverse_move_percent numeric(12, 6),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists signals_ticker_status_idx
  on signals (ticker, status);

create index if not exists signals_strategy_status_idx
  on signals (strategy, status);

create table if not exists signal_events (
  id text primary key,
  signal_id text not null references signals (id) on delete cascade,
  previous_status text not null,
  new_status text not null,
  reason text not null,
  latest_price numeric(18, 4) not null,
  event_time timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists signal_events_signal_time_idx
  on signal_events (signal_id, event_time);

create table if not exists signal_outcomes (
  id text primary key,
  signal_id text not null references signals (id) on delete cascade,
  ticker text not null,
  strategy text not null,
  final_status text not null,
  entry_price numeric(18, 4) not null,
  exit_price numeric(18, 4) not null,
  return_percent numeric(12, 6) not null,
  max_favorable_move_percent numeric(12, 6) not null,
  max_adverse_move_percent numeric(12, 6) not null,
  opened_at timestamptz not null,
  closed_at timestamptz not null,
  close_reason text not null,
  created_at timestamptz not null default now()
);

create index if not exists signal_outcomes_strategy_closed_idx
  on signal_outcomes (strategy, closed_at);

create table if not exists strategy_daily_stats (
  id text primary key,
  strategy text not null,
  trade_date date not null,
  signals_generated integer not null default 0,
  wins integer not null default 0,
  losses integer not null default 0,
  expired integer not null default 0,
  invalidated integer not null default 0,
  total_return_percent numeric(12, 6) not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists strategy_daily_stats_strategy_date_idx
  on strategy_daily_stats (strategy, trade_date);
