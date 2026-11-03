-- Tracked boards chosen during recon (seeds/boards.csv).
select
    md5(provider || '|' || board) as company_id,
    provider,
    board,
    company as company_name,
    try_cast(recon_date as date) as recon_date
from {{ source('bronze', 'tracked_boards') }}
