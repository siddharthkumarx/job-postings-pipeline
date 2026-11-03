-- ECB reference rates: usd_per_unit converts one unit of `currency` into USD on `rate_date`.
select
    rate_date,
    upper(currency) as currency,
    per_eur,
    usd_per_unit
from {{ source('bronze', 'fx_rates') }}
where usd_per_unit > 0
