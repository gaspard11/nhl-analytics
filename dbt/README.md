# NHL Analytics: dbt project

This is the transformation part of the project. It takes the raw NHL API data loaded in Snowflake and builds:

* the league standings for every day of the season, with all the NHL tie breakers,
* the player rankings (goals, assists, points) for every day,
* the games and goals, with the situation of each goal (power play, short handed, empty net),
* each team's travel from arena to arena during the season.

The raw data is loaded into `NHL_RAW.RAW` by the Airflow DAG `nhl_raw_pipeline` (see the [main README](../README.md)). Once the load is done, the DAG triggers the dbt Cloud production job, which builds the tables in `NHL_ANALYTICS.MARTS` that the Streamlit app reads. The project runs in dbt Cloud and needs dbt 1.10 or later (or dbt Fusion).

## Lineage

```
NHL_RAW.RAW (append only, every load is kept)
│
├── GAMES_RAW ──────────► stg_nhl_api__games ──┬──► int_team_game_results ──► int_league_ranking_pre_tie_breaker ──┐
│                                               │                               (cumulative, incremental)             │
│                                               ├──► int_tied_teams_rate ◄───────────────────────────────────────────┤
│                                               │           │                                                         │
│                                               │           └──────────────► fct_league_rankings ◄───────────────────┘
│                                               ├──► fct_games ──► fct_team_travel ◄── dim_teams
│                                               │
├── GAMES_PBP_RAW ──────► stg_nhl_api__goals ───┼──► int_player_scoring_cumulative ──► fct_player_goals_rankings
│                                               │     (cumulative, incremental)         fct_player_assists_rankings
│                                               │                                       fct_player_points_rankings
│                                               ├──► fct_goals (also uses stg_nhl_api__games)
│                                               │
└── PLAYERS_INFO_RAW ───► stg_nhl_api__players ─┴──► dim_players ──► snapshot nhl_players_team_snapshot

seed nhl_teams ──► dim_teams
```

## Models

### Staging (`models/staging/nhl_api/`, views in `STAGING`)

There is one model per raw table. Each one parses the JSON and keeps only the latest load of each game or player (`qualify row_number() over (... order by fetched_at desc) = 1`). Because of that, loading the same date twice changes nothing.

| Model | One row per | Notes |
|---|---|---|
| `stg_nhl_api__games` | finished regular season game | Only `gameStateId = 7` (final). `last_period_type` is `REG`, `OT` or `SO` |
| `stg_nhl_api__goals` | goal, shootouts excluded | The latest play by play of each game is picked before flattening, so no goal is lost |
| `stg_nhl_api__players` | player | `current_team_id` is the team at load time and can be out of date |

### Intermediate (`models/intermediate/`, schema `INTERMEDIATE`)

| Model | Materialization | What it does |
|---|---|---|
| `int_team_game_results` | view | One row per team per game, with `win`, `regulation_win`, `regulation_ot_win` and `points` |
| `int_league_ranking_pre_tie_breaker` | incremental | Season to date totals per team and per day, plus day 0. This is where the running totals are stored |
| `int_tied_teams_rate` | view | Head to head points % between teams that are tied, per day |
| `int_player_scoring_cumulative` | incremental | Season to date goals and assists per player and per day |

### Marts (`models/marts/`, schema `MARTS`)

| Model | One row per | Materialization |
|---|---|---|
| `fct_league_rankings` | team and day | incremental |
| `fct_player_goals_rankings` | player and day (players with at least one goal) | incremental |
| `fct_player_assists_rankings` | player and day (players with at least one assist) | incremental |
| `fct_player_points_rankings` | player and day | incremental |
| `fct_games` | game | incremental (merge on `game_id`) |
| `fct_goals` | goal | incremental (delete+insert on `game_id`) |
| `fct_team_travel` | team and game | table |
| `dim_players` | player | incremental (merge on `player_id`) |
| `dim_teams` | team | table |

### Goal situations (`fct_goals`)

The play by play gives a 4 digit `situation_code` for every goal: away goalie in net (1 or 0), away skaters, home skaters, home goalie in net. `1541` means the away team had 5 skaters and the home team 4.

`fct_goals` reads that code from the scoring team's side and adds two columns:

* `strength`: skaters on each side, scoring team first, like `5 on 4`.
* `goal_type`:
  * `EN` (empty net) when the other team had pulled its goalie,
  * `PPG` (power play) when the scoring team had more skaters,
  * `SHG` (short handed) when it had fewer,
  * `EV` (even strength) otherwise.

A team that pulls its own goalie for an extra attacker is not on a power play, so that extra skater is left out when comparing the two sides.

### Team travel (`fct_team_travel`)

For every game of a team, this model gives the arena it played in and the arena of its previous game, with the distance between the two. The arena names and coordinates come from the `nhl_teams` seed, and the distance is computed with Snowflake's `haversine`. That is a straight line distance, not the real route. It is 0 when the team stays in the same arena, for example during a home stand, and null for the first game of the season. The app uses this model for its travel map.

### Standings rules

Each day, teams are ranked on:

1. points (win = 2, overtime or shootout loss = 1, regulation loss = 0)
2. fewer games played
3. regulation wins
4. regulation and overtime wins
5. total wins
6. head to head points % between the tied teams. When two teams have played an odd number of games against each other, the oldest game hosted by the team with the extra home game is left out.
7. goal differential
8. goals for

Day 0 is the day before a season's first game. Every team is at 0 and ranked last.

### Macros

| Macro | What it does |
|---|---|
| `generate_schema_name` | Uses the schema as is in production (`MARTS`) and prefixes it everywhere else (`DBT_<you>_MARTS`) |
| `nhl_tie_group_id` | Gives the same id to the teams tied on criteria 1 to 5 on the same day |
| `nhl_matchups_ids` | Gives an id to a pair of teams, whichever one is at home |

## How the cumulative models work

`int_league_ranking_pre_tie_breaker` and `int_player_scoring_cumulative` store a running total per day, so a run doesn't have to recompute the whole season. On each run:

1. The model looks for rows loaded since its last run (`fetched_at` later than the highest `_source_fetched_at` already in the table) and takes the earliest game date among them. That is where the batch starts.
2. It reads each team's (or player's) last row before that date. That is the state to start from.
3. It recomputes every day from the batch start onwards, by adding the daily results to that state.
4. It replaces those days in the table (`delete+insert` on `season, ranking_date`).

So in practice:

| Situation | Result |
|---|---|
| Normal day | One day is added |
| Run again with nothing new | Nothing changes |
| Same date loaded twice | Same result, because the state is read strictly before the date |
| A day was missed and loaded later | It is caught up, in order |
| An old date is reloaded | That date and every date after it are recomputed |
| New season | Starts from 0 on its own, since the state is looked up per season |
| `--full-refresh` or an empty schema | Everything is rebuilt from raw with the same code |

The marts downstream only pick up the days that were recomputed, using `_batch_loaded_at`.

## Environments

| Where it runs | Schemas | Example |
|---|---|---|
| dbt Cloud production job | as is | `NHL_ANALYTICS.MARTS.FCT_LEAGUE_RANKINGS` |
| dbt Cloud IDE (development) | prefixed with the dev schema | `NHL_ANALYTICS.DBT_GROBERT_MARTS.FCT_LEAGUE_RANKINGS` |

dbt Cloud sets `DBT_CLOUD_INVOCATION_CONTEXT = prod` in production, and `generate_schema_name` relies on it. A development run can't write to the production tables.

## Running

```
dbt build                              # models, seeds, snapshots and tests, in order
dbt build -s fct_league_rankings+      # one model and everything after it
dbt test                               # tests only
dbt test -s test_type:singular         # only the business rule tests in tests/
```

A new development schema starts empty, so the first `dbt build` in it rebuilds everything from raw.

## Tests

The generic tests are in the `_*__models.yml` files. They check the grain of every model, the keys, the accepted values (`last_period_type`, `goal_type`, points), value ranges (ranks, coordinates, distances) and the relationships to `dim_teams` and `nhl_teams`.

The singular tests are in `tests/`. Each one returns the rows that break a rule:

| Test | What it catches |
|---|---|
| `assert_standings_match_recomputation` | Team running totals that drifted (a day counted twice or skipped) |
| `assert_player_totals_match_recomputation` | The same for player goals and assists |
| `assert_every_game_date_has_standings` | A loaded day that was never processed |
| `assert_every_ranking_date_is_complete` | A day without all 32 teams, or ranks that don't start at 1 |
| `assert_pbp_goals_match_final_score` | Play by play missing, or loaded before the game ended |
| `assert_team_totals_never_decrease` and `assert_player_totals_never_decrease` | A day replaced with older data |
| `assert_team_record_is_consistent` | Impossible records, like more wins than games |
| `assert_league_totals_balance` | A game counted for only one of its two teams |

To look at the failing rows, add `--store-failures` and query `DBT_<you>_DBT_TEST__AUDIT.<test name>`.

## Runbook

### Load or reload a date

Trigger the Airflow DAG `nhl_raw_pipeline` with `game_date = YYYY-MM-DD`. Reloading is safe: staging keeps the latest load, and the next `dbt build` recomputes that date and every date after it.

### A load was interrupted or is wrong

This usually shows up as `assert_pbp_goals_match_final_score` failing for every game of one date. Either reload the date (see above), or delete it from raw and rebuild:

```sql
create table NHL_RAW.RAW.GAMES_RAW_BKP clone NHL_RAW.RAW.GAMES_RAW;   -- backup first
delete from NHL_RAW.RAW.GAMES_RAW
where raw_payload:data[0]:gameDate::date = '<YYYY-MM-DD>';
```

Then run `dbt build --full-refresh`. Don't delete rows from the cumulative tables by hand: the days after would still include the deleted games.

### When to use `--full-refresh`

Only when it is needed, run by hand, never in the scheduled job:

* a column was added, removed or changed type in an incremental model (`on_schema_change='fail'` stops the run on purpose),
* raw data was corrected in the past (see above).

Before a full refresh in production, back up the tables. A zero copy clone is instant:

```sql
create schema NHL_ANALYTICS.MARTS_BKP clone NHL_ANALYTICS.MARTS;
```

### Deploying a change

1. Work in a branch and run `dbt build` in the dbt Cloud IDE (development schemas).
2. Open a pull request and merge it into `main`.
3. The next production run uses `main`. If the change needs a full refresh, run the production job once with `dbt build --full-refresh -s <model>+`.

## Conventions

* Layers: `stg_<source>__<entity>`, then `int_<description>`, then `fct_<facts>` and `dim_<entities>`.
* One YAML file per folder (`_<folder>__models.yml`) with the descriptions and tests. Descriptions shared by several models are in `models/_docs.md`.
* SQL: lowercase keywords and CTE names, import CTEs at the top, explicit columns in the marts, and a comment at the top of every model.
* Schema and materialization are set per folder in `dbt_project.yml`. A model's `config()` only holds what is specific to it (incremental strategy, keys).
* Every number coming out of a cumulative model is cast (`::integer`), so its type can't change from one run to the next.

## Known limitations

* Regular season only: the DAG requests `gameType = 2`, and the `REG` / `OT` / `SO` logic assumes a single overtime period.
* Teams come from the `nhl_teams` seed, with the current 32 franchises and their current arenas. An older season with other teams, or a game played at a neutral site (like the Global Series games in Europe), would need more than one arena per team.
* Shootouts: the final score gives the shootout winner one extra goal, as the NHL does. Shootout goals are left out of the play by play and of player stats.
* `stg_nhl_api__players.current_team_id` is the team when the player was first loaded, since players are only loaded once. `dim_players.team_id` uses the team of the player's latest game with a point instead.
