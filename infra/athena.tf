# Optional ad-hoc SQL over curated/ (the dashboard never uses Athena). Explicit schemas
# instead of a Glue crawler: we know the columns, and crawlers cost money and can guess wrong.

resource "aws_glue_catalog_database" "main" {
  name = replace(var.project_name, "-", "_") # dashes aren't allowed
}

locals {
  # Must match CURATED_TABLES in pipeline/curate.py, column for column.
  curated_columns = {
    matches = {
      match_id       = "bigint"
      start_time     = "bigint"
      duration_s     = "int"
      duration_valid = "boolean"
      winning_team   = "string"
      match_mode     = "string"
    }
    participants = {
      match_id    = "bigint"
      player_slot = "int"
      team        = "string"
      hero_id     = "int"
      won         = "boolean"
    }
  }
}

resource "aws_glue_catalog_table" "curated" {
  for_each      = local.curated_columns
  name          = each.key
  database_name = aws_glue_catalog_database.main.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification = "parquet"
    # Partition projection: Athena derives partition paths itself, so there is no
    # MSCK REPAIR, crawler, or AddPartition call to keep in sync.
    "projection.enabled"                      = "true"
    "projection.match_date_utc.type"          = "date"
    "projection.match_date_utc.format"        = "yyyy-MM-dd"
    "projection.match_date_utc.range"         = "2026-01-01,NOW"
    "projection.match_date_utc.interval"      = "1"
    "projection.match_date_utc.interval.unit" = "DAYS"
  }

  partition_keys {
    name = "match_date_utc"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data.bucket}/curated/${each.key}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = each.value
      content {
        name = columns.key
        type = columns.value
      }
    }
  }
}

# Results land in athena-results/, which s3.tf expires after 7 days.
resource "aws_athena_workgroup" "main" {
  name          = var.project_name
  force_destroy = true

  configuration {
    enforce_workgroup_configuration = true       # queries can't override the cutoff
    bytes_scanned_cutoff_per_query  = 1073741824 # 1 GiB: a runaway query stops at ~$0.005

    result_configuration {
      output_location = "s3://${aws_s3_bucket.data.bucket}/athena-results/"
    }
  }
}

# Saved queries: they appear in the Athena console under "Saved queries" for this
# workgroup. Each one reads only the date folders it needs (partition pruning).
resource "aws_athena_named_query" "hero_win_rates" {
  name      = "hero-win-rates-last-7-days"
  workgroup = aws_athena_workgroup.main.id
  database  = aws_glue_catalog_database.main.name
  query     = <<-SQL
    -- Recomputes the dashboard's main number independently; the two should agree.
    SELECT p.hero_id,
           COUNT(*) AS games,
           ROUND(100.0 * COUNT_IF(p.won) / COUNT(*), 1) AS win_rate_pct
    FROM participants p
    WHERE p.match_date_utc >= CAST(current_date - INTERVAL '7' DAY AS varchar)
    GROUP BY p.hero_id
    ORDER BY games DESC
  SQL
}

resource "aws_athena_named_query" "ranked_vs_unranked" {
  name      = "ranked-vs-unranked-win-rate"
  workgroup = aws_athena_workgroup.main.id
  database  = aws_glue_catalog_database.main.name
  query     = <<-SQL
    -- Does a hero do better in ranked? Join on BOTH keys: match_id and the date
    -- partition, so Athena only reads matching date folders.
    SELECT p.hero_id, m.match_mode,
           COUNT(*) AS games,
           ROUND(100.0 * COUNT_IF(p.won) / COUNT(*), 1) AS win_rate_pct
    FROM participants p
    JOIN matches m
      ON m.match_id = p.match_id AND m.match_date_utc = p.match_date_utc
    WHERE p.match_date_utc >= CAST(current_date - INTERVAL '7' DAY AS varchar)
    GROUP BY p.hero_id, m.match_mode
    HAVING COUNT(*) >= 100
    ORDER BY p.hero_id, m.match_mode
  SQL
}

resource "aws_athena_named_query" "match_length" {
  name      = "match-length-by-day"
  workgroup = aws_athena_workgroup.main.id
  database  = aws_glue_catalog_database.main.name
  query     = <<-SQL
    SELECT match_date_utc,
           COUNT(*) AS matches,
           ROUND(approx_percentile(duration_s, 0.5) / 60.0, 1) AS median_minutes
    FROM matches
    WHERE duration_valid
    GROUP BY match_date_utc
    ORDER BY match_date_utc
  SQL
}

output "athena_workgroup" {
  value = aws_athena_workgroup.main.name
}

output "glue_database" {
  value = aws_glue_catalog_database.main.name
}
