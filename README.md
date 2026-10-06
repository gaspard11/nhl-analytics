# NHL Analytics

A daily data pipeline for the NHL regular season. Every morning it fetches the previous day's games from the NHL API, loads the raw JSON into Snowflake, turns it into standings and player rankings with dbt, and shows the results in a Streamlit app.

## Why this project exists

This is a learning project. I wanted hands on practice with Airflow, dbt, Snowflake and Streamlit, and I needed a subject with real data that changes every day. The NHL was a good fit: the data is public, it updates daily during the season, and the standings rules are complex enough to be interesting to model.

It is also a stat heavy sport, so there are plenty of fun things to build in terms of data visualisation.

I know the setup is overkill. The standings and player stats are already available on nhl.com, a single Python script on a cron could produce most of this, and the app could probably even call the NHL API directly without storing anything. The point was not the output but building the full chain the way it is done in a company: orchestration, a warehouse with raw and modelled layers, tested transformations, and a front end reading from the warehouse.

## Tool choices and cost

I tried to keep the project as cheap as possible while still learning tools that are used in companies.

| Tool | Role | Cost |
|---|---|---|
| Airflow | Orchestration | Free (open source), but it needs a machine to run on |
| GCP VM | Runs Airflow every morning | Low: the VM is only up about an hour a day |
| dbt Cloud | Transformations | Free plan |
| Snowflake | Data warehouse | About $5 to $15 a month during the season |
| Streamlit Community Cloud | Hosts the app | Free |

**Airflow on GCP.** I could not leave my laptop on every morning, so Airflow runs on a GCP VM, which I set up with the help of Claude (see [Disclaimer on AI usage](#disclaimer-on-ai-usage)). A VM is not free, but Claude helped me find a way to keep it very cheap (see [Running Airflow on GCP for almost nothing](#running-airflow-on-gcp-for-almost-nothing)).

**Snowflake.** The warehouse is the hardest part to make cheap. As said above, a warehouse is not needed for a project this size, but learning one was the point, so I chose Snowflake on the Standard edition, at $2 per credit. What keeps the bill down:

* **One X-Small warehouse.** The smallest size, billed 1 credit per hour of running time.
* **Auto-suspend after 60 seconds.** The warehouse only runs while queries run. Each restart is billed for at least 60 seconds.
* **A short daily load.** The Airflow load and the dbt run keep the warehouse up for a few minutes, about 0.05 to 0.15 credits a day ($0.10 to $0.30).
* **App cache.** The app caches query results until the next morning's load, so visits mostly hit the cache instead of waking the warehouse.
* **Tiny data.** Everything fits in a few dozen MB, so storage costs almost nothing.

Most of the bill comes from development rather than from the pipeline: a day of working on the app, or a large backfill, can cost as much as several weeks of daily runs. In the off season, the DAG finds no games and skips dbt, so the cost drops to almost zero.

## Disclaimer on AI usage

This project could almost entirely have been vibe coded. The DAG, the dbt models and the Streamlit app are plain code, and an AI assistant could have written nearly all of it, except perhaps the GCP setup and the connections between the tools. That is probably how many people would do it at work to save time, but my goal was to learn. I did use Claude Code, in a way that kept me learning:

* **dbt.** I wrote the models, macros and tests myself. I then asked Claude Code to audit the project and recommend how to make it more professional and closer to dbt best practices. I let it do the clean up: renaming files and columns to follow naming conventions, adding comments, and filling the YAML files with descriptions of the models and columns.
* **Airflow.** I wrote the DAG myself, with Claude on the side as a teacher and to help me debug. The only task Claude Code wrote entirely is `stop_vm`, which shuts down the VM Airflow runs on, a part I knew very little about.
* **Streamlit.** I wrote all the charts myself, again with Claude as a teacher when the documentation was not enough. Claude Code wrote these parts entirely: the CSS that draws the goal type "pills" in `games.py`, the buttons that highlight teams in the standings evolution in `standings.py`, and the general styling, which I had not paid much attention to while building the charts. It also reorganised the code and added comments.
* **GCP VM setup.** I relied on Claude heavily here, as I had very little knowledge of it, and mostly ran the commands it recommended.

## Architecture

```
NHL API
   │   (Airflow DAG, every morning on a GCP VM)
   ▼
Snowflake  NHL_RAW.RAW          raw JSON, append only
   │   (dbt Cloud production job, triggered by Airflow)
   ▼
Snowflake  NHL_ANALYTICS.MARTS  standings, games, goals, player rankings
   │
   ▼
Streamlit app                   games, standings, evolution, player stats
```

A normal day:

| Time (UTC) | What happens |
|---|---|
| 10:00 | A GCP instance schedule starts the VM. Docker brings Airflow up. |
| 10:15 | The `nhl_raw_pipeline` DAG runs for the previous day. |
| right after | The DAG loads the raw data, triggers the dbt Cloud job, waits for it, then shuts the VM down. The whole run takes less than half an hour. |
| 11:00 | Backup: the instance schedule stops the VM if it is still running. |
| 12:00 | The Streamlit app drops its cache and reads the new data. |

## Airflow

The DAG lives in [`dags/nhl_pipeline.py`](dags/nhl_pipeline.py). For one game date it:

1. Calls the NHL stats API for the finished regular season games of that day.
2. Loads that payload into `NHL_RAW.RAW.GAMES_RAW`.
3. Fetches the play by play of every game (one mapped task per game) and loads it into `GAMES_PBP_RAW`.
4. Collects every player who scored or assisted, skips the ones already in `DIM_PLAYERS`, fetches the others and loads them into `PLAYERS_INFO_RAW`.
5. Triggers the dbt Cloud production job and waits for it to finish. On a day without games, dbt is skipped.
6. Stops the VM it runs on.

Scheduled runs use `game_date = yesterday`. Any date can be loaded or reloaded by triggering the DAG by hand with `game_date = YYYY-MM-DD`. Reloading a date is safe, because staging keeps only the latest load of each game.

Snowflake and dbt Cloud are reached through two Airflow connections (`snowflake_conn_25` and `dbt_conn_gas25`), created on the VM and not stored in the repo.

## Running Airflow on GCP for almost nothing

Airflow needs a machine that is up when the DAG runs. Keeping a VM running all day for a job that takes less than half an hour would cost far more than the job is worth, so the VM is only up for about an hour a day:

* **Spot e2-medium.** Spot VMs cost a fraction of the normal price. Google can reclaim them, which is acceptable for a job that can simply run again.
* **Instance schedule.** A GCP instance schedule starts the VM at 10:00 UTC, before the DAG, and stops it at 11:00 UTC as a safety net.
* **The DAG turns its own machine off.** The last task, `stop_vm`, asks the GCE metadata server for the VM's name, zone and an access token, then calls the Compute Engine API to stop the instance. It runs even when an upstream task failed, so a broken run never leaves the VM billing all day. Manual runs skip it, so the VM stays up while I work in the Airflow UI.
* **Least privilege.** The VM's service account has a custom role, `vmSelfStop`, that holds a single permission: `compute.instances.stop`. It can turn the VM off and nothing else.

The VM runs a lighter Airflow stack than the local one ([`docker-compose.vm.yaml`](docker-compose.vm.yaml)): LocalExecutor instead of Celery, so no Redis or worker containers, and the Snowflake and dbt Cloud providers are built into the image ([`Dockerfile`](Dockerfile)) instead of being installed on every start. The local [`docker-compose.yaml`](docker-compose.yaml) is the standard CeleryExecutor setup, used for development.

The Airflow UI is not exposed to the internet. I reach it through an SSH tunnel from Cloud Shell.

## Snowflake

Two databases:

* `NHL_RAW.RAW` holds the API responses as they come, in `VARIANT` columns. Nothing is updated or deleted: each load is appended with its load time, so any day can be rebuilt from raw.
* `NHL_ANALYTICS` holds what dbt builds, in one schema per layer: `STAGING`, `INTERMEDIATE`, `MARTS`. Development runs write to prefixed schemas (`DBT_<user>_MARTS`), so they can never overwrite production.

The Streamlit app connects with key pair authentication rather than a password.

## dbt

The dbt project is in [`dbt/`](dbt) and runs in dbt Cloud. It goes from raw JSON to:

* `fct_league_rankings`: the standings of every team on every day of the season, with all the NHL tie breakers, including head to head results between tied teams.
* `fct_player_goals_rankings`, `fct_player_assists_rankings`, `fct_player_points_rankings`: player rankings per day.
* `fct_games`, `fct_goals`, `dim_players`, `dim_teams`, `fct_team_travel`.

The standings are cumulative and incremental: each run reads the state of the day before the new data and recomputes only the days that changed, instead of the whole season. Singular tests check that these running totals always match a full recomputation from raw.

Models, tests, the incremental logic and a runbook are documented in [`dbt/README.md`](dbt/README.md).

## Streamlit app

The app is in [`app/`](app). Run it with `streamlit run app.py` from that folder. It has four pages, switched from a navigation bar at the top:

* **Games**: every game up to a chosen date, filterable by team. Each game opens on a timeline of the score with the goals placed on it, the points of each player, and the goal log with the situation of every goal (power play, short handed, empty net).
* **Standings**: the standings table on any date, for the league, a conference or a division.
* **Evolution**: points above .500 game after game for every team, with teams to highlight.
* **Player stats**: player rankings by points, goals or assists.

The data only changes once a day, so query results are cached until 12:00 UTC, after the morning load. Snowflake is then queried once for the day rather than on every visit.

## Repository layout

```
dags/                    Airflow DAG
dbt/                     dbt project (models, tests, seeds, snapshots, macros)
app/                     Streamlit app
Dockerfile               Airflow image with the Snowflake and dbt Cloud providers
docker-compose.yaml      local Airflow (CeleryExecutor)
docker-compose.vm.yaml   Airflow on the GCP VM (LocalExecutor)
```

Secrets are kept out of the repo: `.env`, the Snowflake private keys, `config/airflow.cfg` and the Streamlit `secrets.toml` are all ignored by git.

## Limitations

* Regular season only. Playoffs, with several overtimes of 20 minutes, are not handled.
* Teams come from a seed of the current 32 franchises, so older seasons with other teams would need a per season team list.
* `stop_vm` is the last task of the DAG and runs whatever happens before it, so a failed run still ends green in the Airflow grid. The colour of each task has to be checked to see a failure.
* No alerting yet: a failed run is only noticed by looking at Airflow or at the app.

## Work in progress

There is so much to do in terms of visualisation that this could go on forever. Some ideas for what comes next:

* More advanced player stats.
* Loading the full play by play instead of only the goals.
* Visualisations built from the puck coordinates given for each event, such as shot maps.
* Machine learning to predict results, as [MoneyPuck](https://moneypuck.com) does.
