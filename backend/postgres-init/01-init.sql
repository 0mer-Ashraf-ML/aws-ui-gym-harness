-- PostgreSQL initialization script
-- This script runs when the database is first created

-- Ensure the database exists
SELECT 'CREATE DATABASE harness_main_aws'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'harness_main_aws')\gexec

-- Set up proper permissions
GRANT ALL PRIVILEGES ON DATABASE harness_main_aws TO postgres;

-- Create extensions if needed
\c harness_main_aws;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Set timezone
SET timezone = 'UTC';
