{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='run_date',
        on_schema_change='append_new_columns',
    )
}}
{#
  Silver postings: one row per posting per run date, deduplicated and cleaned.
  Incremental by run date: the dates present in bronze (optionally limited by
  vars run_from/run_to) are deleted and re-inserted, so re-running a day is idempotent.
#}
with src as (
    select *
    from {{ source('bronze', 'postings') }}
    where {{ run_window() }}
),

dedup as (
    select
        *,
        row_number() over (
            partition by provider, board, posting_id, run_date
            order by fetched_at desc
        ) as dup_rank
    from src
),

chosen_salary as (
    select
        *,
        case
            when api_salary_min is not null and api_salary_period is not null then 'api'
            when desc_salary_min is not null and desc_salary_period is not null then 'description'
        end as salary_source
    from dedup
    where dup_rank = 1
)

select
    md5(provider || '|' || board || '|' || posting_id) as posting_key,
    md5(provider || '|' || board) as company_id,
    provider,
    board,
    posting_id,
    nullif(trim(requisition_id), '') as requisition_id,
    trim(regexp_replace(title, '\s+', ' ', 'g')) as title,
    nullif(trim(department), '') as department,
    nullif(trim(team), '') as team,
    nullif(trim(location_raw), '') as location_raw,
    coalesce(len(locations_all), 0) as location_count,
    {{ workplace_type('workplace_type_raw') }} as workplace_type,
    {{ employment_type('employment_type') }} as employment_type,
    nullif(trim(country_hint), '') as country_hint,
    is_listed,
    published_at,
    updated_at,
    job_url,
    salary_source,
    case salary_source when 'api' then api_salary_min when 'description' then desc_salary_min end as salary_min,
    case salary_source
        when 'api' then coalesce(api_salary_max, api_salary_min)
        when 'description' then coalesce(desc_salary_max, desc_salary_min)
    end as salary_max,
    case salary_source when 'api' then api_salary_currency when 'description' then desc_salary_currency end
        as salary_currency,
    case salary_source when 'api' then api_salary_period when 'description' then desc_salary_period end
        as salary_period,
    desc_remote_hint,
    desc_seniority_hint,
    description_sha256,
    run_date,
    fetched_at,
    schema_version
from chosen_salary
