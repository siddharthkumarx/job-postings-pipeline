-- Title → role family + title seniority, using the versioned taxonomy seeds (docs/decisions.md D-006).
with titles as (
    select distinct title from {{ ref('stg_postings') }}
),

families as (
    select
        t.title,
        r.role_family,
        row_number() over (partition by t.title order by r.priority) as pick
    from titles as t
    inner join {{ ref('role_taxonomy') }} as r
        on regexp_matches(t.title, r.pattern)
        and (r.exclude_pattern is null or not regexp_matches(t.title, r.exclude_pattern))
    where r.taxonomy_version = '{{ var("taxonomy_version") }}'
),

levels as (
    select
        t.title,
        s.seniority,
        row_number() over (partition by t.title order by s.priority) as pick
    from titles as t
    inner join {{ ref('seniority_rules') }} as s
        on regexp_matches(t.title, s.pattern)
        and (s.exclude_pattern is null or not regexp_matches(t.title, s.exclude_pattern))
    where s.taxonomy_version = '{{ var("taxonomy_version") }}'
)

select
    t.title,
    coalesce(f.role_family, 'other') as role_family,
    l.seniority as title_seniority,
    '{{ var("taxonomy_version") }}' as taxonomy_version
from titles as t
left join families as f on f.title = t.title and f.pick = 1
left join levels as l on l.title = t.title and l.pick = 1
