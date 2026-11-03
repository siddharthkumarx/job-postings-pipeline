-- One row per tracked company (plus any company seen in bronze that left the tracked list).
with tracked as (
    select company_id, provider, board, company_name from {{ ref('stg_tracked_boards') }}
),

seen as (
    select distinct company_id, provider, board from {{ ref('stg_board_runs') }}
),

companies as (
    select
        coalesce(t.company_id, s.company_id) as company_id,
        coalesce(t.provider, s.provider) as provider,
        coalesce(t.board, s.board) as board,
        coalesce(t.company_name, s.board) as company_name
    from tracked as t
    full outer join seen as s on s.company_id = t.company_id
),

runs as (
    select
        company_id,
        min(run_date) filter (where status = 'ok') as first_tracked,
        arg_max(status, run_date) as last_fetch_status
    from {{ ref('stg_board_runs') }}
    group by 1
),

postings as (
    select
        company_id,
        count(*) filter (where is_open) as open_postings,
        count(*) filter (where is_open and country_code = 'US') as open_us_postings,
        count(*) as postings_seen
    from {{ ref('fct_job_postings') }}
    group by 1
)

select
    c.company_id,
    c.company_name,
    c.provider,
    c.board,
    case c.provider
        when 'greenhouse' then 'https://boards-api.greenhouse.io/v1/boards/' || c.board || '/jobs'
        when 'lever' then 'https://api.lever.co/v0/postings/' || c.board
        when 'ashby' then 'https://api.ashbyhq.com/posting-api/job-board/' || c.board
    end as board_url,
    r.first_tracked,
    case
        when r.last_fetch_status is null then null
        when r.last_fetch_status in ('ok', 'not_found', 'blocked') then r.last_fetch_status
        else 'error'
    end as last_fetch_status,
    cast(coalesce(p.open_postings, 0) as integer) as open_postings,
    cast(coalesce(p.open_us_postings, 0) as integer) as open_us_postings,
    cast(coalesce(p.postings_seen, 0) as integer) as postings_seen
from companies as c
left join runs as r on r.company_id = c.company_id
left join postings as p on p.company_id = c.company_id
