{# Filter on the run-date window given by vars run_from / run_to (both optional). #}
{% macro run_window(column='run_date') -%}
    {%- set f = var('run_from', '') -%}{%- set t = var('run_to', '') -%}
    true
    {%- if f %} and {{ column }} >= date '{{ f }}'{% endif -%}
    {%- if t %} and {{ column }} <= date '{{ t }}'{% endif -%}
{%- endmacro %}

{% macro data_dir() -%}{{ env_var('JOBPIPE_DATA', '../data') }}{%- endmacro %}
