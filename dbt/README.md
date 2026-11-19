# NHL Analytics: dbt project

This is the transformation part of the project. It takes the raw NHL API data loaded in Snowflake and builds:

* the league standings for every day of the season, with all the NHL tie breakers,
* the season to date stats of every skater (games played, time on ice, goals, assists, points) and every goalie (games, time on ice, goals against, saves, shutouts, goals against average, save percentage) for every day,
* the games and goals, with the situation of each goal (power play, short handed, empty net, penalty shot),
* every play of every game, the rosters, and every shift of every player,
* each team's stats for each game, including the power play opportunities, worked out by replaying the penalties of the game,
* each team's travel from arena to arena during the season.

The raw data is loaded into `NHL_RAW.RAW` by the Airflow DAG `nhl_raw_pipeline` (see the [main README](../README.md)). Once the load is done, the DAG triggers the dbt Cloud production job, which builds the tables in `NHL_ANALYTICS.MARTS` that the Streamlit app reads. The project runs in dbt Cloud.

### Standings rules (https://www.nhl.com/info/standings-info/tie-breaking-procedure)

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

1. `int_league_ranking_pre_tie_breaker` computes every team's totals per day, then gives a `tie_group_id` (macro `nhl_tie_group_id`) to the teams equal on criteria 1 to 5. Teams that aren't tied get none. It also keeps the records the app shows next to the standings: home, away and shootout records, the last 10 games and the current streak.
2. `int_tied_teams_rate` only looks at those tie groups: for each one, it takes the games played so far between the teams of the group and computes each team's points % in them.
3. `fct_league_rankings` brings the two together and ranks on all 8 criteria. A team that isn't tied gets a head to head rate of 0, which changes nothing, since rule 6 only separates teams already equal on the first 5.

Day 0 is the day before a season's first game. Every team is at 0 and ranked last.

## Lineage

```
NHL_RAW.RAW (append only, every load is kept)
│
├── GAMES_RAW ──────────► stg_nhl_api__games ──┬──► int_team_game_results ──► int_league_ranking_pre_tie_breaker ──┐
│                                               │                               (cumulative, incremental)             │
│                                               ├──► int_tied_teams_rate ◄───────────────────────────────────────────┤
│                                               │           │                                                         │
│                                               │           └──────────────► fct_league_rankings ◄───────────────────┘
│                                               └──► fct_games ──► fct_team_travel ◄── dim_teams
│
├── GAMES_SHIFTS_RAW ───► stg_nhl_api__games_shifts ──► fct_games_shifts
│
└── GAMES_PBP_RAW ──────► stg_nhl_api__pbp ─────┬──► fct_games_events (also uses stg_nhl_api__games)
                                                ├──► stg_nhl_api__goals ──► fct_goals (also uses stg_nhl_api__games)
                                                └──► stg_nhl_api__game_rosters ──┬──► fct_game_rosters ──► snapshot nhl_players_team_snapshot (also uses fct_games)
                                                                                 └──► dim_players (also uses stg_nhl_api__games)

seed nhl_teams ──► dim_teams

fct_games_events ──┬──► fct_games_pp_segments (Python, also uses fct_games) ──┐
                   │                                                          │
                   └──────────────────────────────────────────────────────────┤
fct_game_rosters ─────────────────────────────────────────────────────────────┼──► fct_games_stats
fct_goals ─────────┬──► fct_games_leading_segments (also uses fct_games) ─────┤
                   └──────────────────────────────────────────────────────────┘

Player stats: per game in intermediate, season to date in the marts
(the per-game models read stg_nhl_api__games_shifts, stg_nhl_api__goals, stg_nhl_api__pbp,
stg_nhl_api__games, and for the goalies dim_players and int_team_game_results)

int_player_game_stats ─┬──────────────────────────► fct_skater_stats  (cumulative, incremental)
(every player)         │   int_skater_game_stats ──┘   (disabled until its first stat)
                       └──────────────────────────► fct_goalie_stats  (cumulative, incremental)
                           int_goalie_game_stats ──┘
```

## Models

### Staging (`models/staging/nhl_api/`, views in `STAGING`)

The models reading a raw table parse the JSON and keep only the latest load of each game (`qualify row_number() over (... order by fetched_at desc) = 1`). Because of that, loading the same date twice changes nothing.

| Model | One row per | Notes |
|---|---|---|
| `stg_nhl_api__games` | finished regular season game | Only `gameStateId = 7` (final). `last_period_type` is `REG`, `OT` or `SO` |
| `stg_nhl_api__pbp` | play (event) | The latest play by play of each game is picked before flattening, so no play is lost. `player_1_id` to `player_3_id` hold the players involved, and `player_*_desc` says what each one did |
| `stg_nhl_api__goals` | goal, shootouts excluded | Built from `stg_nhl_api__pbp`: scorer and assists are `player_1_id` to `player_3_id` |
| `stg_nhl_api__game_rosters` | player and game | Every player who dressed, from the `rosterSpots` of the latest play by play: name, team, position, sweater number, headshot |
| `stg_nhl_api__games_shifts` | shift of a player | Only the real shifts (`typeCode = 517`). The shift chart also has one row per goal (`typeCode = 505`), which is left out |

### Intermediate (`models/intermediate/`, schema `INTERMEDIATE`)

| Model | Materialization | What it does |
|---|---|---|
| `int_team_game_results` | view | One row per team per game, with `win`, `regulation_win`, `regulation_ot_win` and `points` |
| `int_league_ranking_pre_tie_breaker` | incremental (delete+insert on `season, ranking_date`) | Season to date totals per team and per day, plus day 0. This is where the running totals are stored |
| `int_tied_teams_rate` | view | Head to head points % between teams that are tied, per day |
| `int_player_game_stats` | view | One row per player, game and stat, for the stats common to skaters and goalies: time on ice, goals, assists |
| `int_goalie_game_stats` | view | One row per goalie, game and stat, for the goalie-only stats: saves, goals against, shutout |
| `int_skater_game_stats` | view, disabled | One row per skater, game and stat, for the skater-only stats. A template until its first stat is written |

### Marts (`models/marts/`, schema `MARTS`)

| Model | One row per | Materialization |
|---|---|---|
| `fct_league_rankings` | team and day | incremental (delete+insert on `season, ranking_date`) |
| `fct_skater_stats` | skater and day, from their first game | incremental (delete+insert on `season, ranking_date`), cumulative |
| `fct_goalie_stats` | goalie and day, from their first game | incremental (delete+insert on `season, ranking_date`), cumulative |
| `fct_games_shifts` | shift of a player | incremental (delete+insert on `game_id`) |
| `fct_games` | game | incremental (merge on `game_id`) |
| `fct_goals` | goal | incremental (delete+insert on `game_id`) |
| `fct_games_events` | play | incremental (delete+insert on `game_id`) |
| `fct_game_rosters` | player and game | incremental (delete+insert on `game_id`) |
| `fct_games_pp_segments` | segment of constant strength | incremental (delete+insert on `game_id`), Python model |
| `fct_games_leading_segments` | stretch of a game with the same team leading, or tied | incremental (delete+insert on `game_id`) |
| `fct_games_stats` | game, team and stat | incremental (delete+insert on `game_id`) |
| `fct_team_travel` | team and game | table |
| `dim_players` | player | incremental (merge on `player_id`) |
| `dim_teams` | team | table |

### Seed and snapshot

| Name | Type | What it does |
|---|---|---|
| `nhl_teams` | seed | The 32 teams, with conference, division, logo and home arena (name and coordinates). `dim_teams` is built from it |
| `nhl_players_team_snapshot` | snapshot (timestamp strategy on `team_since`, schema `SNAPSHOTS`) | History of each player's team. `dim_players` only keeps the current team, so the snapshot records a new version whenever it changes, for example after a trade |

The snapshot is built from `fct_game_rosters` and `fct_games`. For each player it takes the team of their most recent game, and `team_since`: the date of their first game with that team since their last game with another one. A new version is recorded when `team_since` changes, and `dbt_valid_from` is that date, so it is the date of the player's first game with the new team, not the date of the run that noticed it.

The snapshot only looks at games up to its `as_of` var (today by default). That is how its history was rebuilt: [`scripts/replay_player_team_snapshot.py`](../scripts/replay_player_team_snapshot.py) runs `dbt snapshot --vars '{as_of: ...}'` once per game date, oldest first, in a one-off dbt Cloud production job.

### Goal situations (`fct_goals`)

The play by play gives a 4 digit `situation_code` for every goal: away goalie in net (1 or 0), away skaters, home skaters, home goalie in net. `1541` means the away team had 5 skaters and the home team 4.

`fct_goals` reads that code from the scoring team's side and adds three columns:

* `strength`: skaters on each side, scoring team first, like `5 on 4`, or `Penalty shot`.
* `strength_situation`, who had more skaters:
  * `PS` (penalty shot) when the code is `0101` or `1010`: one shooter alone against the goalie,
  * `PP` (power play) when the scoring team had more skaters,
  * `SH` (short handed) when it had fewer,
  * `EV` (even strength) otherwise.
* `net_situation`, which net was empty:
  * `EN` (empty net) when the other team had pulled its goalie,
  * `EA` (extra attacker) when the scoring team had pulled its goalie,
  * `NORMAL` when both goalies were in, and on penalty shots, whose code has a 0 where a goalie is usually counted.

The two situations are independent, so a goal can be both, like `PP` + `EN`. A pulled goalie doesn't change who is on the power play, so that extra skater is left out on both sides when comparing them:

| Goal | `strength` | `strength_situation` | `net_situation` |
|---|---|---|---|
| Power play | `5 on 4` | `PP` | `NORMAL` |
| Power play with its own goalie pulled | `6 on 4` | `PP` | `EA` |
| Extra attacker | `6 on 5` | `EV` | `EA` |
| Empty net | `5 on 6` | `EV` | `EN` |
| Into the empty net of a penalised team | `5 on 5` | `PP` | `EN` |
| Short handed into an empty net | `4 on 6` | `SH` | `EN` |

The app reads these columns directly to label each goal.

### Play by play events (`fct_games_events`)

Every play of the play by play (shots, hits, faceoffs, penalties, goals, stoppages, shootout attempts…), with the players involved (`player_1_id` to `player_3_id`, and `player_*_desc` saying what each one did) and the puck coordinates. Unlike `fct_goals`, the situation is read from the game's side, not from one team's, since most plays have no scoring team:

* `strength_situation`: `PS` (penalty shot), `PP` (power play) when one team had more skaters, `EV` (even strength) otherwise. The extra skater of a pulled goalie is left out on both sides, as in `fct_goals`.
* `net_situation`: `PULLED` when a team had pulled its goalie, `NORMAL` otherwise.
* `empty_net_team_id`: the team that had pulled its goalie, null otherwise. Comparing it with the team of the play gives `EN` or `EA`, as `fct_goals` does.
* `strength_adv_team`: skaters on each side, the team with more skaters first, like `5 on 4`, or `Penalty shot`.
* `man_adv_team_id`: the team on the power play, without counting the extra skater of a pulled goalie, null when the sides are even.

A game is reloaded when either its play by play or its game row has a newer load, so `fetched_at` is the latest of the two.

### Power play segments (`fct_games_pp_segments`)

The play by play gives the penalties and the goals, but it has no event for the end of a power play, and the official number of opportunities isn't a simple count of penalties. So this model replays each game and cuts it into segments of constant strength (5v5, 5v4, 4v4, 3v3...), one row per segment. It is a Python model because each event depends on who is in the penalty box at that moment, which is a loop over the game rather than a query. It runs inside Snowflake, and each incremental run replays in full the games with newly loaded events, since the simulation needs the whole game.

The simulator (`simulate_game`) works through the goals and penalties of a game in order, with these rules:

* A team has at most 2 players in the box at once. Other penalties wait until a place is free.
* A power play goal ends the earliest running minor of the team short handed. Majors keep going.
* One minor each, with no other penalty running, gives 4 on 4 and no power play. Otherwise, equal penalties on both sides cancel out and are served with substitutes, so the strength doesn't change. The captain's choice is applied by cancelling first the penalties of the players with the fewest penalties.
* A double minor is two minors, and the penalties of one player are served one after the other, majors first.
* From the last 5 minutes of the third period, when a major is left against a minor or a double minor after cancelling, only the difference is served.
* Overtime in the regular season is 3 on 3, and a penalty gives the other team one more skater instead of taking one away from the penalised team. Shootouts are left out.
* Misconducts, game misconducts and penalty shots don't change the strength, so they are ignored. So are pulled goalies: a 6 on 5 isn't a power play.

Power plays are counted in two ways:

* `power_play_number`: consecutive uneven segments with the same team on the power play are one stretch. `5v4 → 5v3 → 5v4` is one, `5v4 → 4v4 → 5v4` is two.
* `pp_opportunities`: the official count. Each penalty served that gave the other team a man advantage counts once, on the first power play segment it overlaps. Coincidental and cancelled penalties don't count. A power play goal during a major that keeps going is a new opportunity.

`strength` is always written from the home side (`4v5` means the away team is on the power play). `pp_team_id` and `pk_team_id` are null at even strength.

### Game stats (`fct_games_stats`)

One row per game, team and stat, so a new stat is one more block in the `union all`, not a new column.

| `stat_name` | How it's computed |
|---|---|
| `Shots On Goal` | `goal` and `shot-on-goal` events of the team |
| `Faceoffs` | `faceoff` events of the team, that is the faceoffs it won |
| `Hits`, `Takeaways`, `Giveaways` | Events of that type for the team |
| `Blocked Shots` | Shots blocked by the team's players. The event belongs to the shooting team, so the blocker's team comes from `fct_game_rosters` |
| `Penalty Minutes` | Sum of the `duration` of the team's penalties |
| `Power Play Goals` | The team's goals with `strength_situation = 'PP'` in `fct_goals`, so a goal at 6 on 4 or into the empty net of a penalised team counts, and a short handed goal doesn't |
| `Power Play Opportunities` | Sum of `pp_opportunities` in `fct_games_pp_segments` |
| `Power Play %` | Goals over opportunities, as a rate between 0 and 1 |
| `Leading time` | Seconds the team spent in the lead, from `fct_games_leading_segments`. Used by the Lead retention page, not shown on the game page |

A team with no row for a stat simply had none of it, and the app shows 0.

### Leading segments (`fct_games_leading_segments`)

Cuts each game by the score, from `fct_goals`: one row per stretch with the same team leading, or tied. Two goals in a row by the leading team stay in one stretch. `leading_team_id` is 0 when the score is tied, and times are in seconds since the start of the game. Shootout goals aren't in `fct_goals`, so a game going to a shootout ends tied. Summed per team, this gives the `Leading time` stat of `fct_games_stats`, which the Lead retention page of the app compares with the points won.

### Team travel (`fct_team_travel`)

For every game of a team, this model gives the arena it played in and the arena of its previous game, with the distance between the two. The arena names and coordinates come from the `nhl_teams` seed, and the distance is computed with Snowflake's `haversine`. That is a straight line distance, not the real route. It is 0 when the team stays in the same arena, for example during a home stand, and null for the first game of the season. It isn't used by the app yet: a travel page is the next thing I want to build.

### Skater and goalie stats (`fct_skater_stats`, `fct_goalie_stats`)

Two tables of season to date stats, one row per player and per day, with no ranking. The standings need dbt to rank the teams, because of the tie breakers, but sorting players by a stat is only a sort, so the app does it on whichever stat it shows.

The stats are split in three families, each with its own per-game model in intermediate:

| Family | Per-game model | Stats |
|---|---|---|
| Common to every player | `int_player_game_stats` | games played, time on ice, goals, assists |
| Goalie only | `int_goalie_game_stats` | saves, goals against, shutouts |
| Skater only | `int_skater_game_stats` (disabled for now) | none yet |

The per-game models are in long format, one row per player, game and stat, like `fct_games_stats`, so a new stat is one more block in a `union all`. The season to date totals are kept in the two marts, `fct_skater_stats` (common + skater stats of every player but the goalies) and `fct_goalie_stats` (common + goalie stats), which pivot the per-game rows and keep the running totals (see [How the cumulative models work](#how-the-cumulative-models-work)). There is no intermediate cumulative table: the mart is the cumulative table. Computed stats, like points, the goals against average or the save percentage, are only computed there, from the totals. A game is recomputed when its game row, its play by play or its shifts have a newer load.

* **Games played and time on ice** come from the shifts, for skaters and goalies alike: a player has played a game when they had at least one shift. A backup goalie who stayed on the bench doesn't count as a game played.
* **Goals and assists** come from `stg_nhl_api__goals`, shootout goals excluded.
* **Saves and goals against** come from the play by play: the `shot-on-goal` and `goal` events with that goalie in net (`goalie_in_net_id`).

Goalie rules:

* Shootouts don't count: their goals and saves are left out, and they have no shifts.
* An empty net goal isn't charged to any goalie.
* A shutout goes to a goalie who was the only one their team used, when the team allowed no goal outside the shootout. In a game that is 0-0 until the shootout, both goalies get one. Since the final score gives the shootout winner one goal, the loser of such a game shows 1 goal against in `int_team_game_results`, and the model looks for that case.
* The goals against average (`goals_against` x 3600 / `toi_seconds`) and the save percentage (`saves` / `shots_against`) are computed on each row from the season totals. Only the counts are accumulated, because a ratio can't be added up from one game to the next.
* Every goalie is kept, as in the full stats table on nhl.com, so a goalie with one game can lead the goals against average. The app is where a minimum number of games belongs.

**Adding a stat** takes four steps: a block in the `union all` of its per-game model, a line in the pivot of the mart (`sum(iff(stat_name = '...', stat_value, 0))`), its running total and `prior_` column in the mart's cumulative CTEs, then a `--full-refresh` of the mart, whose `on_schema_change='fail'` refuses a new column otherwise. The places are marked with `TODO` in the models.

### Shifts (`fct_games_shifts`)

Every shift of every player, from the NHL shift API: period, start, end and duration, as `MM:SS`. The goalie stats only use the goalies' shifts so far.

The shift API turned out to be unreliable on past games. It never got the shifts of 50 games in a row (`2026020154` to `2026020203`, from 22 October 2026), recorded the same minutes twice for some players (game `2025020512`: both goalies 12 to 14 minutes too high once summed) and put the shifts of two teams that didn't play into a game (game `2025020565`). The NHL also publishes every game's shifts in its HTML time on ice reports, one per team, and those were clean on every game checked: each player's total equals the official time on ice of the boxscore. So the one-off DAG `backfill_shifts_from_html` reloaded every game of the 2025-2026 season and of 2026-2027 so far from those reports, in the same format as the API. Only the API's internal ids are missing (`shift_id` is null for those games).

The daily DAG still loads the shifts from the API. Three singular tests watch for the problems seen in the past: `assert_overlapping_shifts` (a player on the ice twice at the same time), `assert_shift_teams_are_correct` (a team that didn't play the game) and `assert_every_game_has_shifts` (a game without shifts, a warning only). When one of them catches a game, deleting that game's payloads from `GAMES_SHIFTS_RAW` and triggering `backfill_shifts_from_html` reloads it from the HTML, since that DAG only loads the games missing from the table.

### Macros

| Macro | What it does | Where it's used |
|---|---|---|
| `generate_schema_name` | Uses the schema as is in production (`MARTS`) and prefixes it everywhere else (`DBT_<you>_MARTS`) | Every model, seed and snapshot. dbt calls it on its own because it replaces dbt's default macro with the same name |
| `nhl_tie_group_id` | Gives the same id to the teams tied on criteria 1 to 5 on the same day | `int_league_ranking_pre_tie_breaker` (`tie_group_id`) |
| `nhl_matchups_ids` | Gives an id to a pair of teams, whichever one is at home | `int_tied_teams_rate` (`matchup_id`), to group the games between two tied teams |

## How the cumulative models work

`int_league_ranking_pre_tie_breaker`, `fct_skater_stats` and `fct_goalie_stats` store a running total per day, so a run doesn't have to recompute the whole season. On each run:

1. The model looks for rows loaded since its last run (`fetched_at` later than the highest `_source_fetched_at` already in the table) and takes the earliest game date among them. That is where the batch starts.
2. It reads each team's (or player's, or goalie's) last row before that date. That is the state to start from.
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

`fct_league_rankings`, downstream of `int_league_ranking_pre_tie_breaker`, only picks up the days that were recomputed, using `_batch_loaded_at`.

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
| `stg_nhl_api__pbp` | `game_id` + `event_id` | unique together |
| | `game_id`, `event_id` | not null |
| `stg_nhl_api__goals` | `game_id` + `event_id` | unique together |
| | `game_id`, `event_id`, `scoring_player_id` | not null |
| `stg_nhl_api__game_rosters` | `game_id` + `player_id` | unique together |
| | `game_id`, `player_id`, `team_id` | not null |
| `stg_nhl_api__games_shifts` | `game_id`, `team_id`, `player_id` | not null |
| | `period` | not null, one of 1, 2, 3, 4 |
| `int_team_game_results` | `game_id` + `team_id` | unique together |
| | `points` | one of 0, 1, 2 |
| | `result` | not null, one of `W`, `L`, `OT` |
| `int_league_ranking_pre_tie_breaker` | `season` + `ranking_date` + `team_id` | unique together |
| | whole row | wins + regulation losses + OT/SO losses = `games_played`, and the home and away splits add up to those totals |
| | whole row | the last 10 games add up to 10 (or `games_played` before the 10th game), the streak is never longer than `games_played`, and there is a streak once the team has played |
| | `streak_result` | one of `W`, `L`, `OT` |
| `int_tied_teams_rate` | `season` + `ranking_date` + `tie_group_id` + `team_id` | unique together |
| | `tie_rate` | not null, between 0 and 1 |
| `int_player_game_stats` | `game_id` + `player_id` + `stat_name` | unique together |
| | `game_id`, `stat_name`, `fetched_at` | not null |
| | `player_id` | not null, exists in `dim_players` |
| | `stat_name` | one of `toi_seconds`, `goals`, `assists` |
| | whole row | `stat_value` is 0 or more, and `toi_seconds` is at most 3,900 (60 minutes plus 5 of overtime). Catches a game whose shifts are counted twice |
| `int_goalie_game_stats` | `game_id` + `player_id` + `stat_name` | unique together |
| | `game_id`, `stat_name`, `fetched_at` | not null |
| | `player_id` | not null, exists in `dim_players` |
| | `stat_name` | one of `saves`, `goals_against`, `shutout` |
| | whole row | `stat_value` is 0 or more |
| `fct_league_rankings` | `season` + `ranking_date` + `team_id` | unique together |
| | `ranking` | not null, between 1 and 32 |
| | `team_id` | not null, exists in `dim_teams` |
| | `losses`, `ot_losses`, `home_record`, `away_record`, `shootout_record`, `last_10_record` | not null |
| | `points_pct` | between 0 and 1 |
| | `streak` | a result and a number of games, like `W2`, `L1` or `OT1` (when not null) |
| `fct_skater_stats` | `season` + `ranking_date` + `player_id` | unique together |
| | whole row | `points` = `goals` + `assists`, and `toi_seconds` ≤ 3,900 × `games_played` |
| | `player_id` | not null, exists in `dim_players` |
| | `games_played` | at least 1 |
| `fct_goalie_stats` | `season` + `ranking_date` + `player_id` | unique together |
| | whole row | `shots_against` = `goals_against` + `saves`, `shutouts` ≤ `games_played`, and `toi_seconds` ≤ 3,900 × `games_played` |
| | `player_id` | not null, exists in `dim_players` |
| | `games_played` | at least 1 |
| | `gaa` | 0 or more |
| | `save_pct` | between 0 and 1 |
| `fct_games` | `game_id` | unique, not null |
| `fct_goals` | `game_id` + `event_id` | unique together |
| | `strength_situation` | not null, one of `PS`, `PP`, `SH`, `EV` |
| | `net_situation` | not null, one of `EN`, `EA`, `NORMAL` |
| `fct_games_events` | `game_id` + `event_id` | unique together |
| | `strength_situation` | not null, one of `PS`, `PP`, `EV` |
| | `net_situation` | not null, one of `PULLED`, `NORMAL` |
| `fct_game_rosters` | `game_id` + `player_id` | unique together |
| | `team_id` | not null, exists in `dim_teams` |
| `fct_games_pp_segments` | `game_id` + `segment_number` | unique together |
| | `game_id` | not null, exists in `fct_games` |
| | `duration_seconds` | at least 1 |
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
| `assert_standings_match_recomputation` | `fct_league_rankings` | On the latest day of each season, every team's `games_played`, `points`, `total_wins`, `regulation_wins`, `regulation_ot_wins`, `goals_for`, `goals_against`, `losses` and `ot_losses` equal the same totals recomputed from scratch from `int_team_game_results`. Catches a day counted twice or skipped by the incremental runs |
| `assert_skater_totals_match_recomputation` | `fct_skater_stats` | On the latest day of each season, every skater's `games_played`, `toi_seconds`, `goals` and `assists` equal a sum from scratch over `int_player_game_stats` |
| `assert_team_totals_never_decrease` | `fct_league_rankings` | Within a season, none of `games_played`, `points`, `total_wins`, `regulation_wins`, `regulation_ot_wins`, `goals_for`, `goals_against` is lower than on the team's previous day. Catches a day replaced with older data |
| `assert_skater_totals_never_decrease` | `fct_skater_stats` | Within a season, none of `games_played`, `toi_seconds`, `goals`, `assists` is lower than on the skater's previous day |
| `assert_goalie_totals_match_recomputation` | `fct_goalie_stats` | On the latest day of each season, every goalie's `games_played`, `toi_seconds`, `goals_against`, `saves` and `shutouts` equal a sum from scratch over `int_player_game_stats` and `int_goalie_game_stats` |
| `assert_goalie_totals_never_decrease` | `fct_goalie_stats` | Within a season, none of `games_played`, `toi_seconds`, `goals_against`, `saves`, `shutouts` is lower than on the goalie's previous day |
| `assert_every_game_has_shifts` | `stg_nhl_api__games_shifts` | Every finished game has shifts. A warning, not an error: the NHL sometimes publishes a shift chart after the game, and the next daily run picks it up. A game that stays in the list for days was never published by the shift API |
| `assert_overlapping_shifts` | `stg_nhl_api__games_shifts` | No two shifts of the same player overlap in a period, and no shift is there twice. Catches a game whose shifts the API recorded twice, which would count that time twice |
| `assert_shift_teams_are_correct` | `stg_nhl_api__games_shifts` | Every shift belongs to one of the two teams of its game. Catches a shift chart holding the shifts of another game |
| `assert_every_game_date_has_standings` | `fct_league_rankings` | Every `game_date` of `stg_nhl_api__games` has standings for that season and date. Catches a day loaded into raw but never processed |
| `assert_every_ranking_date_is_complete` | `fct_league_rankings` | Every day has as many teams as the `nhl_teams` seed (32), and the best `ranking` is 1 once at least one game has been played (on day 0 every team is ranked last) |
| `assert_team_record_is_consistent` | `fct_league_rankings` | For every team and day: `total_wins` ≤ `games_played`, `regulation_wins` ≤ `regulation_ot_wins` ≤ `total_wins`, `points` ≥ 2 × `total_wins`, `points` − 2 × `total_wins` ≤ losses (each loss is worth at most 1 point), `total_wins` + `losses` + `ot_losses` = `games_played` (every game is a win, a regulation loss or an OT/SO loss), and `goal_diff` = `goals_for` − `goals_against` |
| `assert_league_totals_balance` | `fct_league_rankings` | For the whole league on every day: 2 × the sum of `total_wins` = the sum of `games_played` (one winner per game, two teams per game), and the sum of `goals_for` = the sum of `goals_against`. Catches a game counted for only one of its two teams |
| `assert_pbp_goals_match_final_score` | `stg_nhl_api__goals` | For every finished game, the number of goals in the play by play equals `home_team_score` + `away_team_score`, minus 1 for a game decided in a shootout (the final score gives the shootout winner one goal, but shootout goals are not in the play by play). Catches a play by play loaded before the end of the game, or never loaded |
