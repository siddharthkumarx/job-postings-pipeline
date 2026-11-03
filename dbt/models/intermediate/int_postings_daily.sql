{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='run_date',
    )
}}
{#
  Enriched posting × run date: role family, seniority, parsed location, remote type and
  annualised salary. attr_hash covers the SCD2-tracked attributes (title, location, salary).
#}
with p as (
    select * from {{ ref('stg_postings') }}
    {% if is_incremental() %}
    where run_date in (select distinct run_date from {{ source('bronze', 'postings') }} where {{ run_window() }})
    {% endif %}
)

select
    p.posting_key,
    p.company_id,
    p.provider,
    p.board,
    p.posting_id,
    p.run_date,
    p.title,
    t.role_family,
    coalesce(t.title_seniority, p.desc_seniority_hint, 'mid') as seniority,
    case
        when t.title_seniority is not null then 'title'
        when p.desc_seniority_hint is not null then 'description'
        else 'default'
    end as seniority_source,
    t.taxonomy_version,
    p.department,
    p.location_raw,
    p.location_count,
    l.country_code,
    l.state_code,
    l.city,
    coalesce(
        p.workplace_type,
        l.remote_text,
        p.desc_remote_hint,
        case when l.city is not null then 'onsite' end,
        'unknown'
    ) as remote_type,
    case
        when p.workplace_type is not null then 'api'
        when l.remote_text is not null then 'location'
        when p.desc_remote_hint is not null then 'description'
        when l.city is not null then 'location_default'
        else 'none'
    end as remote_type_source,
    p.employment_type,
    p.salary_source,
    p.salary_min,
    p.salary_max,
    p.salary_currency,
    p.salary_period,
    p.salary_min * {{ annual_factor('p.salary_period') }} as salary_min_annual,
    p.salary_max * {{ annual_factor('p.salary_period') }} as salary_max_annual,
    p.job_url,
    p.published_at,
    p.description_sha256,
    md5(concat_ws('|',
        p.title, coalesce(p.location_raw, ''), coalesce(cast(p.salary_min as varchar), ''),
        coalesce(cast(p.salary_max as varchar), ''), coalesce(p.salary_currency, ''),
        coalesce(p.salary_period, '')
    )) as attr_hash
from p
left join {{ ref('int_title_labels') }} as t on t.title = p.title
left join {{ ref('int_locations') }} as l
    on l.location_key = coalesce(p.location_raw, '') || '|' || coalesce(p.country_hint, '')
