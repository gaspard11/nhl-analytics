# NHL Analytics: dbt project

This is the transformation part of the project. It takes the raw NHL API data loaded in Snowflake and builds:

* the league standings for every day of the season, with all the NHL tie breakers,
* the player rankings (goals, assists, points) for every day,
* the games and goals, with the situation of each goal (power play, short handed, empty net, penalty shot),
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

* `strength`: skaters on each side, scoring team first, like `5 on 4`, or `Penalty shot`.
* `goal_type`:
  * `PS` (penalty shot) when the code is `0101` or `1010`: one shooter alone against the goalie,
  * `EN` (empty net) when the other team had pulled its goalie,
  * `PPG` (power play) when the scoring team had more skaters,
  * `SHG` (short handed) when it had fewer,
  * `EA` (extra attacker) when the scoring team had pulled its goalie and the sides were otherwise even, like 6 on 5,
  * `EV` (even strength) otherwise.

A team that pulls its own goalie for an extra attacker is not on a power play, so that extra skater is left out when comparing the two sides. The app reads these two columns directly to label each goal.

### Team travel (`fct_team_travel`)

For every game of a team, this model gives the arena it played in and the arena of its previous game, with the distance between the two. The arena names and coordinates come from the `nhl_teams` seed, and the distance is computed with Snowflake's `haversine`. That is a straight line distance, not the real route. It is 0 when the team stays in the same arena, for example during a home stand, and null for the first game of the season. It isn't used by the app yet: a travel page is the next thing I want to build.

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

Rule 6 is what shapes the models. Criteria 1 to 5 and 7 to 8 are season totals of each team on its own, but head to head can't be computed that way: it only makes sense between the teams that are still tied after rule 5, and it depends on which teams those are on that day. So the standings are built in three steps:

1. `int_league_ranking_pre_tie_breaker` computes every team's totals per day, then gives a `tie_group_id` (macro `nhl_tie_group_id`) to the teams equal on criteria 1 to 5. Teams that aren't tied get none.
2. `int_tied_teams_rate` only looks at those tie groups: for each one, it takes the games played so far between the teams of the group and computes each team's points % in them.
3. `fct_league_rankings` brings the two together and ranks on all 8 criteria. A team that isn't tied gets a head to head rate of 0, which changes nothing, since rule 6 only separates teams already equal on the first 5.

Day 0 is the day before a season's first game. Every team is at 0 and ranked last.

### Macros

| Macro | What it does | Where it's used |
|---|---|---|
| `generate_schema_name` | Uses the schema as is in production (`MARTS`) and prefixes it everywhere else (`DBT_<you>_MARTS`) | Every model, seed and snapshot. dbt calls it on its own because it replaces dbt's default macro with the same name |
| `nhl_tie_group_id` | Gives the same id to the teams tied on criteria 1 to 5 on the same day | `int_league_ranking_pre_tie_breaker` (`tie_group_id`) |
| `nhl_matchups_ids` | Gives an id to a pair of teams, whichever one is at home | `int_tied_teams_rate` (`matchup_id`), to group the games between two tied teams |

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

## Tests

### Generic tests

They are declared in the `_*__models.yml` files, next to the descriptions.

| Model | Columns | Test |
|---|---|---|
| `stg_nhl_api__games` | `game_id` | unique, not null |
| | `season`, `game_date` | not null |
| | `home_team_id`, `away_team_id` | not null, exists in the `nhl_teams` seed |
| | `last_period_type` | one of `REG`, `OT`, `SO` |
| `stg_nhl_api__goals` | `game_id` + `event_id` | unique together |
| | `game_id`, `event_id`, `scoring_player_id` | not null |
| `stg_nhl_api__players` | `player_id` | unique, not null |
| `int_team_game_results` | `game_id` + `team_id` | unique together |
| | `points` | one of 0, 1, 2 |
| `int_league_ranking_pre_tie_breaker` | `season` + `ranking_date` + `team_id` | unique together |
| `int_tied_teams_rate` | `season` + `ranking_date` + `tie_group_id` + `team_id` | unique together |
| | `tie_rate` | not null, between 0 and 1 |
| `int_player_scoring_cumulative` | `season` + `ranking_date` + `player_id` | unique together |
| | `number_of_points` | at least 1 |
| `fct_league_rankings` | `season` + `ranking_date` + `team_id` | unique together |
| | `ranking` | not null, between 1 and 32 |
| | `team_id` | not null, exists in `dim_teams` |
| `fct_player_goals_rankings`, `fct_player_assists_rankings`, `fct_player_points_rankings` | `season` + `ranking_date` + `player_id` | unique together |
| | `ranking` | not null |
| `fct_games` | `game_id` | unique, not null |
| `fct_goals` | `game_id` + `event_id` | unique together |
| | `goal_type` | not null, one of `PS`, `EN`, `PPG`, `SHG`, `EA`, `EV` |
| `fct_team_travel` | `game_id` + `team_id` | unique together |
| | `team_id` | not null, exists in `dim_teams` |
| | `arena_name` | not null |
| | `distance_km` | 0 or more |
| `dim_players` | `player_id` | unique, not null |
| `dim_teams` | `team_id` | unique, not null |
| | `arena_name` | not null |
| | `arena_latitude` | not null, between -90 and 90 |
| | `arena_longitude` | not null, between -180 and 180 |

### Singular tests

They are in `tests/`. Each one returns the rows that break its rule, so a passing test returns nothing.

| Test | Model checked | Rule |
|---|---|---|
| `assert_standings_match_recomputation` | `fct_league_rankings` | On the latest day of each season, every team's `games_played`, `points`, `total_wins`, `regulation_wins`, `regulation_ot_wins`, `goals_for` and `goals_against` equal the same totals recomputed from scratch from `int_team_game_results`. Catches a day counted twice or skipped by the incremental runs |
| `assert_player_totals_match_recomputation` | `int_player_scoring_cumulative` | On the latest day of each season, every player's `number_of_goals` and `number_of_assists` equal a count from scratch over `stg_nhl_api__goals` (scorer, first assist, second assist) |
| `assert_team_totals_never_decrease` | `fct_league_rankings` | Within a season, none of `games_played`, `points`, `total_wins`, `regulation_wins`, `regulation_ot_wins`, `goals_for`, `goals_against` is lower than on the team's previous day. Catches a day replaced with older data |
| `assert_player_totals_never_decrease` | `int_player_scoring_cumulative` | Within a season, `number_of_goals` and `number_of_assists` are never lower than on the player's previous day |
| `assert_every_game_date_has_standings` | `fct_league_rankings` | Every `game_date` of `stg_nhl_api__games` has standings for that season and date. Catches a day loaded into raw but never processed |
| `assert_every_ranking_date_is_complete` | `fct_league_rankings` | Every day has as many teams as the `nhl_teams` seed (32), and the best `ranking` is 1 once at least one game has been played (on day 0 every team is ranked last) |
| `assert_team_record_is_consistent` | `fct_league_rankings` | For every team and day: `total_wins` ≤ `games_played`, `regulation_wins` ≤ `regulation_ot_wins` ≤ `total_wins`, `points` ≥ 2 × `total_wins`, `points` − 2 × `total_wins` ≤ losses (each loss is worth at most 1 point), and `goal_diff` = `goals_for` − `goals_against` |
| `assert_league_totals_balance` | `fct_league_rankings` | For the whole league on every day: 2 × the sum of `total_wins` = the sum of `games_played` (one winner per game, two teams per game), and the sum of `goals_for` = the sum of `goals_against`. Catches a game counted for only one of its two teams |
| `assert_pbp_goals_match_final_score` | `stg_nhl_api__goals` | For every finished game, the number of goals in the play by play equals `home_team_score` + `away_team_score`, minus 1 for a game decided in a shootout (the final score gives the shootout winner one goal, but shootout goals are not in the play by play). Catches a play by play loaded before the end of the game, or never loaded |

## Known limitations

* Regular season only: the DAG requests `gameType = 2`, and the `REG` / `OT` / `SO` logic assumes a single overtime period.
* Teams come from the `nhl_teams` seed, with the current 32 franchises and their current arenas. An older season with other teams, or a game played at a neutral site (like the Global Series games in Europe), would need more than one arena per team.
* Shootouts: the final score gives the shootout winner one extra goal, as the NHL does. Shootout goals are left out of the play by play and of player stats.
* `stg_nhl_api__players.current_team_id` is the team when the player was first loaded, since players are only loaded once. `dim_players.team_id` uses the team of the player's latest game with a point instead.
