{% docs season %}
NHL season as an 8-digit integer: start year followed by end year, e.g. `20252026`.
{% enddocs %}

{% docs ranking_date %}
Date the standings or rankings are computed for, including that day's games.
There is one ranking date per day with at least one finished game. For team standings, there is also
day 0: the day before a season's first game, where every total is 0.
{% enddocs %}

{% docs game_id %}
NHL game id, e.g. `2025020441`: season start year, game type (`02` = regular season), then game number.
{% enddocs %}

{% docs game_date %}
Date the game was played (local date of the game, as given by the NHL API).
{% enddocs %}

{% docs team_id %}
NHL team id. Joins to `dim_teams.team_id`.
{% enddocs %}

{% docs player_id %}
NHL player id. Joins to `dim_players.player_id`.
{% enddocs %}

{% docs last_period_type %}
How the game ended: `REG` = in regulation (3 periods), `OT` = in overtime, `SO` = in a shootout.
{% enddocs %}

{% docs situation_code %}
Manpower situation when the goal was scored, as 4 digits: away goalie in net (1/0), away skaters,
home skaters, home goalie in net (1/0). E.g. `1551` = 5-on-5, `0651` = away goalie pulled for an extra attacker.
Kept as a string to preserve the leading 0.
{% enddocs %}

{% docs fetched_at %}
When the raw payload behind this row was loaded into `NHL_RAW.RAW` by the Airflow DAG.
Used as the watermark by incremental models to find new or reloaded data.
{% enddocs %}

{% docs batch_loaded_at %}
Technical column: when the dbt run that (re)computed this row happened.
Downstream incremental models use it to pick up exactly the rows recomputed since their last run.
{% enddocs %}

{% docs player_ranking %}
Rank among all players that day, computed with `rank()`: players with the same total share a rank,
and the next rank is skipped (1, 2, 2, 4…).
{% enddocs %}
