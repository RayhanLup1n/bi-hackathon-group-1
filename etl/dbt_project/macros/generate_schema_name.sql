/*
  Custom schema name macro untuk dbt-postgres.

  Default dbt behavior: schema = {target_schema}_{custom_schema}
  Contoh: target=main, custom=staging → "main_staging"

  Macro ini override agar schema yang kita definisikan di dbt_project.yml
  digunakan ASIS tanpa prefix.
  Contoh: custom=staging → "staging" (bukan "main_staging")

  Referensi: https://docs.getdbt.com/docs/build/custom-schemas
*/
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
