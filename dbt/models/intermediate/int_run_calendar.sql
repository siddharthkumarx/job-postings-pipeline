-- Every run date on which at least one board was fetched successfully.
select
    run_date,
    date_trunc('week', run_date)::date as week_start,
    count(*) filter (where status = 'ok') as boards_ok,
    count(*) as boards_total
from {{ ref('stg_board_runs') }}
group by 1, 2
having count(*) filter (where status = 'ok') > 0
