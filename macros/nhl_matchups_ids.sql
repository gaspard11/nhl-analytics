{% macro nhl_matchups_ids(
    home_team_id = 'home_team_id',
    away_team_id = 'away_team_id'
) %}
    {{ dbt_utils.generate_surrogate_key([
        "least(" ~ home_team_id ~ ", " ~ away_team_id ~ ")",
        "greatest(" ~ home_team_id ~ ", " ~ away_team_id ~ ")"
    ]) }}
{% endmacro %}