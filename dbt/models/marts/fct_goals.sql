{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

-- One row per non-shootout goal, with its situation from the scoring team's point of view.
-- A reloaded game replaces all its goals (delete+insert on game_id), so a goal disallowed
-- after the first load disappears.

select *
from {{ ref('int_goals_situations') }}
