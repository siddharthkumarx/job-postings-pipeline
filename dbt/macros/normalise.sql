{% macro annual_factor(period) -%}
    case {{ period }}
        when 'year' then 1 when 'month' then 12 when 'week' then 52
        when 'day' then 260 when 'hour' then 2080
    end
{%- endmacro %}

{% macro employment_type(col) -%}
    case
        when {{ col }} is null then 'unknown'
        when regexp_matches(lower({{ col }}), 'intern') then 'intern'
        when regexp_matches(lower({{ col }}), 'part') then 'part_time'
        when regexp_matches(lower({{ col }}), 'contract|freelance|consult') then 'contract'
        when regexp_matches(lower({{ col }}), 'temp|seasonal|fixed') then 'temporary'
        when regexp_matches(lower({{ col }}), 'full|perm|regular|salaried') then 'full_time'
        else 'unknown'
    end
{%- endmacro %}

{% macro workplace_type(col) -%}
    case
        when {{ col }} is null then null
        when regexp_matches(lower({{ col }}), 'hybrid') then 'hybrid'
        when regexp_matches(lower({{ col }}), 'remote') then 'remote'
        when regexp_matches(lower({{ col }}), 'on-?site|office|in[- ]person') then 'onsite'
    end
{%- endmacro %}
