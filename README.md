# NHL Analytics

A daily data pipeline for the NHL regular season. Every morning it fetches the last two days of games from the NHL API, loads the raw JSON into Snowflake, turns it into standings and player rankings with dbt, and shows the results in a Streamlit app.

The final app lives here: [https://nhl-app.streamlit.app/](https://nhl-app.streamlit.app/)

## New additions / changes

What I have improved since the last full update of this README, on 7 October 2026.

**In the app (see [Streamlit app](#streamlit-app))**

* **New [Lead retention](#lead-retention) page.** Which teams turn their time in the lead into points, and which let their leads slip, compared with the league trend.
* **Game stats.** Opening a game now compares the two teams: shots on goal, faceoffs, power play, penalty minutes, hits, blocked shots, giveaways and takeaways.
* **Play by play log.** Every event of a game, with filters on the event type, the team and the period.
* **Rosters.** The players who dressed for each team, by position, with their sweater number. The numbers also appear next to the names in the goal log and the play by play.
* **Team colours.** When two teams have colours that are too close, the away team switches to its secondary colour, so the charts of a game stay readable.
* **Faster Games page.** It starts with the last 7 days and has a Load more button, it only builds the details of the games that are open, and it prepares its data once a day instead of on every visit.
* **Clearer game cards.** They now read away @ home, with `OT` or `SO` next to the winner's score.

**In the data (see the [dbt README](dbt/README.md))**

* **Full play by play.** `fct_games_events` holds every play of every game, not only the goals, with the players involved, the puck coordinates and the manpower situation.
* **Power play simulator.** `fct_games_pp_segments` is the project's first dbt Python model. It replays each game penalty by penalty with the NHL rules, to cut it into segments of constant strength and to count the official power play opportunities, which the play by play doesn't give.
* **Strength and net situations.** Each goal and each play now has two separate columns, one for who has more skaters and one for which net is empty, so a power play goal into an empty net keeps both.
* **Game stats model.** `fct_games_stats` gives each team's stats for each game, and feeds the new stats in the app.
* **Leading time.** `fct_games_leading_segments` cuts each game by who is leading, which gives the time each team spent in the lead for the Lead retention page.
* **Players from the play by play.** Names, teams and rosters now come from the play by play, so the separate calls to the player API are gone from the DAG.
* **Player team history.** `nhl_players_team_snapshot` now dates a move to the player's first game with the new team, instead of the day the run noticed it, and its history can be replayed date by date.
* **More robust daily load.** The DAG now loads the last two days instead of one, so a game that was not finished at the previous run is picked up.
* **More tests and documentation.** The new play by play and roster models have tests, and their columns are described.

## Why this project exists

This is a learning project. I wanted hands on practice with Airflow, dbt, Snowflake and Streamlit, and I needed a subject with real data that changes every day. The NHL was a good fit: the data is public, it updates daily during the season, and the standings rules are complex enough to be interesting to model.

Furthermore, I am a hockey fan and it is a stat heavy sport, so there are plenty of fun things to build in terms of data visualisation.

I know the setup is overkill. The standings and player stats are already available on nhl.com, a single Python script on a cron could produce most of this, and the app could probably even call the NHL API directly without storing anything. The point was not the output but building the full chain the way it is done in a company: orchestration, a warehouse with raw and modelled layers, tested transformations, and a front end reading from the warehouse.

## Hockey 101

A few rules that help to follow the rest:

* **Game length.** Three periods of 20 minutes, five skaters and a goalie on each side: that is regulation time (`REG`). There are no ties. If the score is level after regulation, the teams play a 5 minute overtime (`OT`), three against three, where the first goal wins. If nobody scores, a shootout (`SO`) decides the winner.
* **Points.** A win is worth 2 points, however it was won. A loss in overtime or in the shootout is worth 1 point, a loss in regulation 0.
* **Penalties.** A player who commits a foul goes to the penalty box, and their team plays with one skater less for a few minutes. The team with more players is on a power play: a goal it scores is a power play goal (`PPG`). A goal by the team with fewer players is a short handed goal (`SHG`). A minor penalty lasts 2 minutes and ends early if the other team scores. A major lasts 5 minutes and is served in full. When both teams are penalised at the same time, the penalties can cancel out and nobody gets a power play.
* **Pulled goalie.** A team can replace its goalie with an extra skater: when it is losing near the end of a game, or during a delayed penalty (the referee has called a penalty on the other team but waits until that team touches the puck). A goal scored with that extra skater is an extra attacker goal (`EA`). A goal scored into the empty net by the other team is an empty net goal (`EN`).
* **Penalty shot.** After some fouls on a clear scoring chance, the player gets a one on one try against the goalie (`PS`).

## Tool choices and cost

I tried to keep the project as cheap as possible while still learning tools that are used in companies.

| Tool | Role | Cost |
|---|---|---|
| Airflow | Orchestration | Free (open source), but it needs a machine to run on |
| GCP VM | Runs Airflow every morning | Less than $5 a month: the VM is only up about an hour a day |
| dbt Cloud | Transformations | Free plan |
| Snowflake | Data warehouse | Free: a new free trial account every month |
| Streamlit Community Cloud | Hosts the app | Free |
| GitHub Actions | Keeps the app awake | Free: a few minutes a day, well within the 2,000 free minutes a month |
| Claude (Pro plan) | Teacher, debugging, code reviews (see [Disclaimer on AI usage](#disclaimer-on-ai-usage)) | $20 a month |

**Airflow on GCP.** I could not leave my laptop on every morning, so Airflow runs on a GCP VM, which I set up with the help of Claude (see [Disclaimer on AI usage](#disclaimer-on-ai-usage)). A VM is not free, but Claude helped me find a way to keep it very cheap (see [Running Airflow on GCP for almost nothing](#running-airflow-on-gcp-for-almost-nothing)).

**Snowflake.** The warehouse is the hardest part to make cheap. As said above, a warehouse is not needed for a project this size, but learning one was the point. So I use Snowflake free trials and change account every month. I know it is clunky, but it saves money, and setting up the account and the connections again is a good repetition exercise.

**Keeping the app awake.** On the free plan, Streamlit puts an app to sleep after 12 hours without a visit. The next visitor then lands on a "this app has gone to sleep" page and has to wait a minute for it to start, which is not great when the link is in a CV. Waking up also empties the app's cache, so every page queries Snowflake again. A scheduled GitHub Actions workflow opens every page of the app in a headless browser three times a day (00:10, 08:10 and 16:10 UTC), so it never reaches 12 hours without traffic. A simple ping would not be enough: Streamlit only counts a visit when a browser actually renders the page. The 08:10 run comes right after the daily cache refresh, so it also loads the day's data into the cache before the first real visitor.

## Disclaimer on AI usage

This project could almost entirely have been vibe coded. The DAG, the dbt models and the Streamlit app are plain code, and an AI assistant could have written nearly all of it, save perhaps the GCP setup and the connections between the tools. That is probably how many people would do it at work to save time, but my goal was to learn. I did use Claude Code, in a way that kept me learning:

* **dbt.** I wrote the models, macros and tests myself. I then asked Claude Code to audit the project and recommend how to make it more professional and closer to dbt best practices. I let it do the clean up: renaming files and columns to follow naming conventions, adding comments, and filling the YAML files with descriptions of the models and columns.
* **Airflow.** I wrote the DAG myself, with Claude on the side as a teacher and to help me debug. The only task Claude Code wrote entirely is `stop_vm`, which shuts down the VM Airflow runs on, a part I knew very little about.
* **Streamlit.** I wrote all the charts myself, again with Claude as a teacher when the documentation was not enough. Claude Code wrote these parts entirely: the CSS that draws the goal type "pills" in `games.py`, the buttons that highlight teams on the Evolution page in `evolution.py`, the logos placed side by side when teams share a point on that chart, and the general styling, which I had not paid much attention to while building the charts. It also reorganised the code and added comments.
* **GCP VM setup.** I relied on Claude heavily here, as I had very little knowledge of it, and mostly ran the commands it recommended.
* **Keeping the app awake.** This part was written entirely by Claude Code: the GitHub Actions workflow and the Playwright script that visits the app to keep it awake.
* **README files.** I wrote most of the text in the README files myself, but I let Claude Code write the lists describing the steps and models, the lineage diagrams, tables and the formatting.

## Architecture

```
NHL API
   │   (Airflow DAG, every morning on a GCP VM)
   ▼
Snowflake  NHL_RAW.RAW          raw JSON, append only
   │   (dbt Cloud production job, triggered by Airflow)
   ▼
Snowflake  NHL_ANALYTICS.MARTS  standings, games, play by play, game stats, player rankings, team travel
   │
   ▼
Streamlit app                   games, standings, evolution, player stats, lead retention
```

A normal day:

| Time (UTC) | What happens |
|---|---|
| 06:00 | A GCP instance schedule starts the VM. Docker brings Airflow up. |
| 06:15 | The `nhl_raw_pipeline` DAG runs for the previous day and the day before. |
| right after | The DAG loads the raw data, triggers the dbt Cloud job, waits for it, then shuts the VM down. The whole run takes less than half an hour. |
| 07:00 | Backup: the instance schedule stops the VM if it is still running. |
| 08:00 | The Streamlit app drops its cache and reads the new data. |
| 08:10 | GitHub Actions opens every page of the app, which keeps it awake and loads the new data into its cache. It visits again at 16:10 and 00:10. |

## Airflow

The DAG lives in [`airflow/dags/nhl_pipeline.py`](airflow/dags/nhl_pipeline.py). Each run:

1. Calls the NHL stats API for the finished regular season games of each date to load (one mapped task per date).
2. Fetches the play by play of every game (one mapped task per game).
3. Loads everything into `NHL_RAW.RAW`: `GAMES_RAW` and `GAMES_PBP_RAW`. The play by play also holds each game's rosters, which is where the player names and teams come from. The inserts only start once all the API calls are done, so the warehouse is up for a few seconds.
4. Triggers the dbt Cloud production job and waits for it to finish. On a day without games, dbt is skipped.
5. Stops the VM it runs on.

The DAG takes the date to load as a parameter. Scheduled runs load the day before, plus the day before that again, so a game that was not finished at the previous run is picked up. A run triggered with a date loads only that date, so any past date can be loaded again, which is how I backfilled earlier games. Loading the same date twice does no harm, because dbt staging models only keep the latest load of each game.

Snowflake and dbt Cloud are reached through two Airflow connections (`snowflake_conn_25` and `dbt_conn_gas25`), created on the VM and not stored in the repo.

## Running Airflow on GCP for almost nothing

Airflow needs a machine that is on when the DAG runs. The job takes less than half an hour, so paying for a machine that runs all day would be a waste. Instead, the VM is only on for about an hour each morning:

* **A small, standard machine.** I started with a "spot" VM, which Google sells at a large discount with the catch that it can take the machine back at any time, or refuse to start it when it has no spare capacity. A run cut in the middle, or a morning without a VM, means a day of games that is not loaded. Since the VM is only on for about an hour a day, a standard e2-medium costs about a dollar a month, so the discount was not worth that risk.
* **It starts on a timer.** GCP starts the VM at 06:00 UTC, just before the DAG, and stops it at 07:00 UTC in case anything went wrong.
* **It turns itself off.** The last task of the DAG, `stop_vm`, shuts down the machine it runs on as soon as the work is done, even if an earlier task failed. That way a broken run never leaves the VM running (and billing) all day. When I start the DAG by hand, the VM stays on so I can keep working.
* **It can only turn itself off.** The VM has permission to stop itself and nothing else, so even if someone got into it, they could not touch the rest of the GCP project.

The VM also runs a lighter version of Airflow than the one I use on my laptop. The standard setup is built to share work across several machines, which is unnecessary for one small daily job, so the VM runs everything in a single place with fewer moving parts ([`docker-compose.vm.yaml`](airflow/docker-compose.vm.yaml)). The extra packages Airflow needs to talk to Snowflake and dbt Cloud are installed once, when the image is built ([`Dockerfile`](airflow/Dockerfile)), instead of every time the VM starts. This lets Airflow fit on a small, cheap machine and start faster each morning.

The Airflow web interface is not open to the internet. I reach it through a secure connection from Google Cloud Shell.

## Snowflake

Two databases:

* `NHL_RAW.RAW` holds the API responses as they come, in `VARIANT` columns. Nothing is updated or deleted: each load is appended with its load time, so any day can be rebuilt from raw.
* `NHL_ANALYTICS` holds what dbt builds, in one schema per layer: `STAGING`, `INTERMEDIATE`, `MARTS`. Development runs write to prefixed schemas (`DBT_<user>_MARTS`), so they can never overwrite production.

Airflow, dbt and the app each have their own Snowflake user, and they all share the same X-Small warehouse, `NHL_APP_WH`. The Streamlit app connects with key pair authentication rather than a password.

## dbt

The dbt project is in [`dbt/`](dbt) and runs in dbt Cloud. It goes from raw JSON to:

* `fct_league_rankings`: the standings of every team on every day of the season, with all the NHL tie breakers, including head to head results between tied teams.
* `fct_player_goals_rankings`, `fct_player_assists_rankings`, `fct_player_points_rankings`: player rankings per day.
* `fct_games_stats`: each team's stats for each game (shots, faceoffs, hits, power play...).
* `fct_games_pp_segments`: every game cut into segments of constant strength, with the official power play opportunities. This one is a Python model, because it has to replay the penalty box event by event.
* `fct_games_leading_segments`: every game cut into stretches with the same team leading, or tied.
* `fct_games`, `fct_goals`, `fct_games_events`, `fct_game_rosters`, `dim_players`, `dim_teams`, `fct_team_travel`.

The standings are cumulative and incremental: each run reads the state of the day before the new data and recomputes only the days that changed, instead of the whole season. Singular tests check that these running totals always match a full recomputation from raw.

Models, tests and the incremental logic are documented in [`dbt/README.md`](dbt/README.md).

## Streamlit app

The app is in [`app/`](app). It has five pages, switched from a navigation bar at the top. The charts are made with Altair and the tables with Streamlit's own dataframes. Every page has a season and a date picker, so you can go back to any day of a season and see things as they were that day.

### Games

This is the page I spent the most time on. It shows the last 7 days of games up to the chosen date, newest first, with a Load more button for older ones, and can be filtered on one team. Each game is a card that reads away @ home, with the two logos and the score. The winner's score is in bold, with `OT` or `SO` next to it when the game went past regulation.

Opening a game shows the timeline, then a chart and a log side by side, each with a menu to switch what it shows.

* **Timeline**: one bar for the whole game, cut by period, in the colour of the team leading at that moment (grey when the score is tied). Each goal is the logo of the team that scored it, above the bar for the home team and below for the away team. Hovering over a goal shows the scorer's headshot, the assists, the score after the goal and the type of goal. In overtime the bar stops at the winning goal, and a shootout shows as one last goal for the winner.
* **Stats** (chart, shown first): the two teams face to face. Each stat has its two values and a bar split by each team's share: shots on goal, faceoffs, power play %, penalty minutes, hits, blocked shots, giveaways and takeaways. Faceoffs also show the count, like `47% (27/57)`, and the power play shows goals over opportunities.
* **Points** (chart): one bar per player who scored or assisted, in the team's colour, goals in full colour and assists lighter, with the player's headshot at the end of the bar.
* **Goals** (log, shown first): every goal, period by period, with the scorer, the assists, the score, the time and the situation: power play, short handed, empty net, extra attacker, penalty shot or even strength, with the number of skaters on each side (`5 on 4`). A goal can be two of those at once, like a power play goal into an empty net.
* **Play by play** (log): every event of the game, period by period, with the team, a headshot, the players involved and the situation. Goals are highlighted, and whistles and period ends are thin lines between the events. It can be filtered on the event type, the team and the period.
* **Rosters** (log): the two teams side by side, with their forwards, defensemen and goalies, each with their sweater number, headshot and position.

Each team's colour comes from its logo. When the two teams of a game have colours too close to tell apart, the away team takes its secondary colour on that game's charts. The distance between two colours is computed with a formula weighted to be close to what the eye sees.

### Standings

The standings table on any date, for the whole league, a conference or a division, with the same columns as on nhl.com: games played, points, wins, regulation wins, regulation and overtime wins, goals for, goals against and goal differential. The order comes straight from dbt, with every tie breaker applied, and the rank starts again at 1 inside a conference or a division.

### Evolution

Each team's points above .500, game after game: points minus games played, so a team that takes one point per game on average stays at 0. It is a good way to compare teams that haven't played the same number of games. The idea comes from the standings chart on [MoneyPuck](https://moneypuck.com/standings.htm), which I liked a lot. There is one line per team, in its colours, with its logo at the end. When several teams have the same record, their logos are placed side by side instead of on top of each other. On the right, a button per team (logo and abbreviation, grouped by division) highlights its line and fades the others, which is handy when 32 lines are on top of each other. Moving the date back replays the season up to that day, and the axes don't move, so two dates are easy to compare.

### Player stats

Players ranked by points, goals or assists on the chosen date, with their headshot and their team's logo, for the whole league, a conference or a division. The column the table is ranked by is highlighted. The team shown is the player's current team.

### Lead retention

Which teams turn their time in the lead into points, from the start of the season up to the chosen date. The page shows one logo per team on a chart, and a table next to it with the numbers, the teams with the most points per game first. The page explains how to read the chart above it.

The chart puts the minutes a team spends in the lead per game against its points per game (2 for a win, 1 for a loss in overtime or in a shootout). Overtime adds no time in the lead, as it ends on the first goal. The red line is the league trend, a straight line fitted through the teams on the chosen date: the points per game a team usually gets for its time in the lead. A team below it gets fewer points than its time in the lead suggests, so it lets its leads slip. A toggle switches between the time in the lead over the whole game and in the 3rd period only, where a lead is closest to becoming a win.

### Cache

The data only changes once a day, so query results are cached until 08:00 UTC, after the morning load. Each query then runs once a day rather than on every visit, and the 08:10 keep-awake run triggers it before the first real visitor (see [Keeping the app awake](#tool-choices-and-cost)). The Games page loads the goals, play by play, rosters and stats of every game together, once a day, and shares them between all visitors, so opening a game doesn't run a query. The cache lives in the app's memory, so it is also emptied when the app restarts.

## Repository layout

```
airflow/
  dags/nhl_pipeline.py         the daily DAG
  Dockerfile                   Airflow image with the Snowflake and dbt Cloud providers
  docker-compose.yaml          local Airflow (CeleryExecutor)
  docker-compose.vm.yaml       Airflow on the GCP VM (LocalExecutor)
dbt/
  models/                      staging, intermediate and marts
  tests/                       singular tests
  macros/, seeds/, snapshots/
  README.md                    models, tests and the incremental logic in detail
app/
  app.py                       entry point and navigation
  games.py, game_details.py    Games page, and its game details (timeline and goals)
  standings.py                 Standings page
  evolution.py                 Evolution page
  player_stats.py              Player stats page
  lead_retention.py            Lead retention page
  common.py                    Snowflake access, daily cache, team colours, shared controls
scripts/
  replay_player_team_snapshot.py  one-off rebuild of the player team snapshot history
.github/
  workflows/keep-app-awake.yml visits the app three times a day
  scripts/keep_app_awake.py    the headless browser script it runs
```

Secrets are kept out of the repo: the `.env` file, the Snowflake private keys, `airflow/config/airflow.cfg` and the Streamlit `secrets.toml` are all ignored by git.

## Work in progress

There is so much to do in terms of visualisation that this could go on forever. Some ideas for what comes next:

* Team travel. The dbt model is already there (`fct_team_travel`): for every game, the arena a team comes from, the arena it plays in and the distance between the two. The next step is a page in the app with a map of each team's trips over the season, and a comparison of the teams: who travels the most, where, and whether the teams that travel more get worse results.
* More advanced player stats.
* Visualisations built from the puck coordinates given for each event, such as shot maps.
* Machine learning to predict results, as [MoneyPuck](https://moneypuck.com) does.
