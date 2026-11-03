{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='run_date',
    )
}}
-- One row per board per run: the fetch outcome decides whether an absent posting counts as missing.
with src as (
    select
        *,
        row_number() over (partition by provider, board, run_date order by fetched_at desc) as dup_rank
    from {{ source('bronze', 'board_runs') }}
    where {{ run_window() }}
)

select
    md5(provider || '|' || board) as company_id,
    provider,
    board,
    run_date,
    status,
    http_status,
    postings,
    invalid_postings,
    attempts,
    elapsed_s,
    bytes,
    fetched_at
from src
where dup_rank = 1
