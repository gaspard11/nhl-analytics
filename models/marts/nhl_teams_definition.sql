{{ config(materialized='table', schema='marts') }}


SELECT * FROM {{ref('NHL_TEAMS')}}
