/*
  Custom schema name macro untuk dbt-bigquery.

  Default dbt behavior: schema = {target_schema}_{custom_schema}
  Contoh: target=raw, custom=staging -> "raw_staging"

  Macro ini override agar schema (dataset) yang kita definisikan di dbt_project.yml
  digunakan AS-IS tanpa prefix.
  Contoh: custom=staging -> "staging" (bukan "raw_staging")

  Referensi: https://docs.getdbt.com/docs/build/custom-schemas
*/
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
