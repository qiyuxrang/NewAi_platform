#!/bin/sh
set -eu
# Executed once by the postgres image. Password remains an environment value.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT 'CREATE DATABASE enterprise_portal' WHERE NOT EXISTS
  (SELECT FROM pg_database WHERE datname = 'enterprise_portal')\gexec
SQL
