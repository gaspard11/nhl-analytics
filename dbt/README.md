# NHL Analytics — dbt project

Turns raw NHL API data into daily **league standings** (with every NHL tie-breaker) and daily
**player scoring rankings** (goals, assists, points), on Snowflake.

- **Ingestion:** the Airflow DAG `nhl_raw_pipeline` (outside this repo) calls the NHL API for one date
  and appends the raw JSON to `NHL_RAW.RAW`, then triggers the dbt Cloud production job.
- **Transformation:** this project, run in dbt Cloud (dbt Fusion / dbt ≥ 1.10).
- **Output:** tables in `NHL_ANALYTICS.MARTS`, read by the app.

---

## Lineage

```
NHL_RAW.RAW (append-only, every load kept)
│
├── GAMES_RAW ──────────► stg_nhl_api__games ──┬──► int_team_game_results ──► int_league_ranking_pre_tie_breaker ──┐
│                                               │                               (cumulative state, incremental)       │
│                                               ├──► int_tied_teams_rate ◄───────────────────────────────────────────┤
│                                               │           │                                                         │
│                                               │           └──────────────► fct_league_rankings ◄───────────────────┘
│                                               ├──► fct_games
│                                               │
├── GAMES_PBP_RAW ──────► stg_nhl_api__goals ───┼──► int_player_scoring_cumulative ──► fct_player_goals_rankings
│                                               │     (cumulative state, incremental)   fct_player_assists_rankings
│                                               │                                       fct_player_points_rankings
│                                               ├──► fct_goals
│                                               │
└── PLAYERS_INFO_RAW ───► stg_nhl_api__players ─┴──► dim_players ──► snapshot nhl_players_team_snapshot

seed nhl_teams ──► dim_teams
```

## Models

### Staging — `models/staging/nhl_api/` (views, schema `STAGING`)

One model per raw table. Parses the JSON and keeps **only the latest load** of each game or player
(`qualify row_number() over (... order by fetched_at desc) = 1`), so loading the same date twice is harmless.

| Model | Grain | Notes |
|---|---|---|
| `stg_nhl_api__games` | one row per finished regular-season game | `gameStateId = 7` only. `last_period_type`: `REG` / `OT` / `SO` |
| `stg_nhl_api__goals` | one row per non-shootout goal | Latest play-by-play payload per game, picked *before* flattening |
| `stg_nhl_api__players` | one row per player | `current_team_id` is the team at load time and can be stale |

### Intermediate — `models/intermediate/` (schema `INTERMEDIATE`)

| Model | Materialization | Purpose |
|---|---|---|
| `int_team_game_results` | view | One row per team per game, with `win`, `regulation_win`, `regulation_ot_win`, `points` |
| `int_league_ranking_pre_tie_breaker` | **incremental** | Cumulative team totals per ranking date, plus day 0. Holds the state. |
| `int_tied_teams_rate` | view | Head-to-head points % between tied teams, per ranking date |
| `int_player_scoring_cumulative` | **incremental** | Cumulative goals and assists per player per ranking date. Holds the state. |

### Marts — `models/marts/` (schema `MARTS`)

| Model | Grain | Materialization |
|---|---|---|
| `fct_league_rankings` | team × ranking date | incremental |
| `fct_player_goals_rankings` | player × ranking date (players with ≥ 1 goal) | incremental |
| `fct_player_assists_rankings` | player × ranking date (players with ≥ 1 assist) | incremental |
| `fct_player_points_rankings` | player × ranking date | incremental |
| `fct_games` | game | incremental (merge on `game_id`) |
| `fct_goals` | goal | incremental (delete+insert on `game_id`) |
| `dim_players` | player | incremental (merge on `player_id`) |
| `dim_teams` | team | table |

### Standings rules

Teams are ranked per day on, in order:

1. points (win = 2, OT/SO loss = 1, regulation loss = 0)
2. fewer games played
3. regulation wins
4. regulation + OT wins
5. total wins
6. head-to-head points % among the tied teams (when two teams played an odd number of games,
   the oldest game hosted by the team with the extra home game is excluded)
7. goal differential
8. goals for

**Day 0** (the day before a season's first game) has every team at 0, all ranked last.

### Macros

| Macro | Purpose |
|---|---|
| `generate_schema_name` | Custom schemas as-is in prod (`MARTS`), prefixed everywhere else (`DBT_<you>_MARTS`) |
| `nhl_tie_group_id` | Id shared by teams tied on criteria 1–5 on the same day |
| `nhl_matchups_ids` | Id of a pair of teams, independent of home/away |

---

## How the cumulative models work

`int_league_ranking_pre_tie_breaker` and `int_player_scoring_cumulative` keep a running total per day
instead of recomputing the whole season on every run. Each run:

1. **Finds the batch start** — the earliest game date among rows loaded since the last run
   (`fetched_at > max(_source_fetched_at)` of the table: the **watermark**).
2. **Reads the prior state** — each team's / player's last row **strictly before** that date.
3. **Recomputes every date from the batch start onwards** = prior state + running sum of the daily results.
4. **Replaces those days** (`delete+insert` on `(season, ranking_date)`).

This makes every run:

| Situation | What happens |
|---|---|
| Normal day | One date is added |
| Re-run with nothing new | Nothing changes |
| Same date loaded twice | Same result (prior state is taken strictly before the date) |
| Missed day, loaded later | Caught up, in order |
| Old date backfilled | That date and every later date are recomputed |
| New season | Starts at 0 automatically (state is looked up per season) |
| `--full-refresh` / empty schema | Rebuilt from the full raw history with the same code |

The marts downstream pick up exactly the recomputed days through `_batch_loaded_at`.

---

## Environments

| Where you run | Schemas written | Example |
|---|---|---|
| dbt Cloud **production** job | as-is | `NHL_ANALYTICS.MARTS.FCT_LEAGUE_RANKINGS` |
| dbt Cloud IDE (dev) | prefixed with your dev schema | `NHL_ANALYTICS.DBT_GROBERT_MARTS.FCT_LEAGUE_RANKINGS` |

Production is detected with `DBT_CLOUD_INVOCATION_CONTEXT = prod` (set by dbt Cloud), so a dev run can
never overwrite production tables.

## Running

```
dbt build                              # models + seeds + snapshots + tests, in DAG order
dbt build -s fct_league_rankings+      # one model and everything downstream
dbt test                               # tests only
dbt test -s test_type:singular         # the business-rule tests in tests/
```

A new dev schema is empty, so the first `dbt build` there rebuilds everything from raw.

## Tests

- **Generic tests** (in the `_*__models.yml` files): grain of every model, keys, accepted values,
  relationships to `dim_teams` / `nhl_teams`.
- **Singular tests** (in `tests/`, each returns the rows that break the rule):

| Test | Catches |
|---|---|
| `assert_standings_match_recomputation` | Drift in the cumulative team totals (day counted twice, day skipped) |
| `assert_player_totals_match_recomputation` | Same for player goals and assists |
| `assert_every_game_date_has_standings` | A loaded day that was never processed |
| `assert_every_ranking_date_is_complete` | A day without all 32 teams, or ranks not starting at 1 |
| `assert_pbp_goals_match_final_score` | Play-by-play missing or loaded before the game ended |
| `assert_team_totals_never_decrease` / `assert_player_totals_never_decrease` | A day replaced with older data |
| `assert_team_record_is_consistent` | Impossible records (wins > games, points vs wins…) |
| `assert_league_totals_balance` | A game counted for only one of its two teams |

To inspect failing rows: add `--store-failures` and query `DBT_<you>_DBT_TEST__AUDIT.<test name>`.

---

## Runbook

### Load or reload a date (backfill)
Trigger the Airflow DAG `nhl_raw_pipeline` with `game_date = YYYY-MM-DD`. Reloading a date is safe:
staging keeps the latest load, and the next `dbt build` recomputes that date and every later one.

### A load was interrupted or is wrong
Symptom: `assert_pbp_goals_match_final_score` fails for all games of one date.
Either reload the date (above), or delete it from raw and rebuild:

```sql
create table NHL_RAW.RAW.GAMES_RAW_BKP clone NHL_RAW.RAW.GAMES_RAW;   -- backup first
delete from NHL_RAW.RAW.GAMES_RAW
where raw_payload:data[0]:gameDate::date = '<YYYY-MM-DD>';
```

then run `dbt build --full-refresh`. Never delete rows from the cumulative tables by hand: later days
would still include the deleted games.

### When to use `--full-refresh`
Only when needed, run manually, never in the scheduled job:
- a column was added, removed or changed type in an incremental model (`on_schema_change='fail'` stops the run on purpose)
- raw was corrected in the past (see above)

Before a full refresh in production, back up the tables (zero-copy clone is instant):

```sql
create schema NHL_ANALYTICS.MARTS_BKP clone NHL_ANALYTICS.MARTS;
```

### Deploying a change
1. Work in a branch, run `dbt build` in the dbt Cloud IDE (dev schemas).
2. Open a pull request, merge to `main`.
3. Production runs `main` on the next job run. If the change needs a full refresh, run the production job
   once with `dbt build --full-refresh -s <model>+`.

---

## Conventions

- Layers: `stg_<source>__<entity>` → `int_<description>` → `fct_<facts>` / `dim_<entities>`.
- One YAML file per folder (`_<folder>__models.yml`) with descriptions and tests.
- SQL: lowercase keywords, lowercase CTE names, import CTEs at the top (`with x as (select * from {{ ref('x') }})`),
  explicit columns in marts, a header comment in every model.
- Configs (schema, materialization) are set per folder in `dbt_project.yml`; a model's `config()` only holds
  what is specific to it (incremental strategy, keys).
- Every numeric output of a cumulative model is cast (`::integer`) so its type can't drift between runs.

## Known limitations

- **Regular season only** — the DAG requests `gameType = 2`. The `REG` / `OT` / `SO` logic assumes one OT period.
- **Teams come from the `nhl_teams` seed** (current 32 franchises). Loading an older season with different
  teams would need a per-season team list.
- **Shootouts** — the final score counts the shootout winner as one goal (NHL convention); shootout goals are
  excluded from the play-by-play and from player stats.
- **`stg_nhl_api__players.current_team_id`** is the team when the player was first loaded (players are loaded
  once). `dim_players.team_id` uses the team of the player's latest game with a point instead.
