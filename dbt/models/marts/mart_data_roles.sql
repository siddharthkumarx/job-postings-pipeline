-- Data roles: data engineer, analytics engineer, data analyst, ML engineer.
select *
from {{ ref('fct_job_postings') }}
where role_family in (
    {%- for f in var('data_role_families') %}'{{ f }}'{% if not loop.last %}, {% endif %}{% endfor -%}
)
