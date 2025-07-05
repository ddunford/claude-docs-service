-- Database initialization script for Document Service
-- This script sets up the initial database structure and configuration

-- Create extensions if they don't exist
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- Create application user for the service
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_user WHERE usename = 'document_service') THEN
    CREATE USER document_service WITH PASSWORD 'document_service_password';
  END IF;
END
$$;

-- Grant necessary permissions
GRANT CONNECT ON DATABASE documents TO document_service;
GRANT USAGE ON SCHEMA public TO document_service;
GRANT CREATE ON SCHEMA public TO document_service;

-- Create audit schema for tracking changes
CREATE SCHEMA IF NOT EXISTS audit;
GRANT USAGE ON SCHEMA audit TO document_service;
GRANT CREATE ON SCHEMA audit TO document_service;

-- Create application-specific schemas
CREATE SCHEMA IF NOT EXISTS documents;
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS events;

-- Grant schema permissions
GRANT USAGE ON SCHEMA documents TO document_service;
GRANT CREATE ON SCHEMA documents TO document_service;
GRANT USAGE ON SCHEMA auth TO document_service;
GRANT CREATE ON SCHEMA auth TO document_service;
GRANT USAGE ON SCHEMA events TO document_service;
GRANT CREATE ON SCHEMA events TO document_service;

-- Create audit function for tracking changes
CREATE OR REPLACE FUNCTION audit.log_changes() RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    INSERT INTO audit.audit_log (
      table_name,
      operation,
      old_data,
      changed_by,
      changed_at
    ) VALUES (
      TG_TABLE_NAME,
      TG_OP,
      row_to_json(OLD),
      current_user,
      now()
    );
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO audit.audit_log (
      table_name,
      operation,
      old_data,
      new_data,
      changed_by,
      changed_at
    ) VALUES (
      TG_TABLE_NAME,
      TG_OP,
      row_to_json(OLD),
      row_to_json(NEW),
      current_user,
      now()
    );
    RETURN NEW;
  ELSIF TG_OP = 'INSERT' THEN
    INSERT INTO audit.audit_log (
      table_name,
      operation,
      new_data,
      changed_by,
      changed_at
    ) VALUES (
      TG_TABLE_NAME,
      TG_OP,
      row_to_json(NEW),
      current_user,
      now()
    );
    RETURN NEW;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Create audit log table
CREATE TABLE IF NOT EXISTS audit.audit_log (
  id SERIAL PRIMARY KEY,
  table_name VARCHAR(255) NOT NULL,
  operation VARCHAR(10) NOT NULL,
  old_data JSONB,
  new_data JSONB,
  changed_by VARCHAR(255) NOT NULL,
  changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for audit table
CREATE INDEX IF NOT EXISTS idx_audit_log_table_name ON audit.audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON audit.audit_log(changed_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_operation ON audit.audit_log(operation);

-- Create sequence for document IDs
CREATE SEQUENCE IF NOT EXISTS documents.document_id_seq
  START WITH 1
  INCREMENT BY 1
  NO MINVALUE
  NO MAXVALUE
  CACHE 1;

-- Grant sequence permissions
GRANT USAGE ON SEQUENCE documents.document_id_seq TO document_service;

-- Create function to generate document slugs
CREATE OR REPLACE FUNCTION documents.generate_slug(title TEXT) RETURNS TEXT AS $$
BEGIN
  RETURN lower(trim(regexp_replace(
    regexp_replace(
      regexp_replace(unaccent(title), '[^a-zA-Z0-9\s-]', '', 'g'),
      '\s+', '-', 'g'
    ),
    '-+', '-', 'g'
  ), '-'));
END;
$$ LANGUAGE plpgsql;

-- Create function to update timestamp
CREATE OR REPLACE FUNCTION public.update_updated_at() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create custom types for document status
CREATE TYPE documents.document_status AS ENUM (
  'draft',
  'processing',
  'processed',
  'published',
  'archived',
  'deleted'
);

-- Create custom types for document visibility
CREATE TYPE documents.document_visibility AS ENUM (
  'private',
  'internal',
  'public'
);

-- Create custom types for user roles
CREATE TYPE auth.user_role AS ENUM (
  'admin',
  'editor',
  'viewer',
  'guest'
);

-- Create custom types for event types
CREATE TYPE events.event_type AS ENUM (
  'document_created',
  'document_updated',
  'document_deleted',
  'document_published',
  'document_archived',
  'user_created',
  'user_updated',
  'user_deleted',
  'authentication_success',
  'authentication_failure'
);

-- Set default permissions for new tables
ALTER DEFAULT PRIVILEGES IN SCHEMA documents GRANT ALL ON TABLES TO document_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT ALL ON TABLES TO document_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA events GRANT ALL ON TABLES TO document_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT ALL ON TABLES TO document_service;

-- Set default permissions for new sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA documents GRANT ALL ON SEQUENCES TO document_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT ALL ON SEQUENCES TO document_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA events GRANT ALL ON SEQUENCES TO document_service;

-- Create configuration table for application settings
CREATE TABLE IF NOT EXISTS public.app_config (
  key VARCHAR(255) PRIMARY KEY,
  value TEXT,
  description TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert default configuration values
INSERT INTO public.app_config (key, value, description) VALUES 
  ('max_file_size_mb', '20', 'Maximum file size allowed for uploads in MB'),
  ('allowed_file_types', 'pdf,doc,docx,txt,jpg,jpeg,png', 'Comma-separated list of allowed file extensions'),
  ('virus_scan_enabled', 'true', 'Enable virus scanning for uploaded files'),
  ('backup_retention_days', '30', 'Number of days to retain backup files'),
  ('session_timeout_minutes', '60', 'Session timeout in minutes')
ON CONFLICT (key) DO NOTHING;

-- Create trigger to update updated_at timestamp
CREATE TRIGGER update_app_config_updated_at
  BEFORE UPDATE ON public.app_config
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at();

-- Grant permissions on configuration table
GRANT ALL ON public.app_config TO document_service;

-- Create health check function
CREATE OR REPLACE FUNCTION public.health_check() RETURNS JSON AS $$
BEGIN
  RETURN json_build_object(
    'status', 'healthy',
    'timestamp', NOW(),
    'database', 'postgresql',
    'version', version(),
    'connections', (
      SELECT count(*) FROM pg_stat_activity 
      WHERE state = 'active' AND backend_type = 'client backend'
    )
  );
END;
$$ LANGUAGE plpgsql;

-- Grant permission to execute health check
GRANT EXECUTE ON FUNCTION public.health_check() TO document_service;

-- Log initialization completion
INSERT INTO audit.audit_log (
  table_name,
  operation,
  new_data,
  changed_by,
  changed_at
) VALUES (
  'database_init',
  'INIT',
  json_build_object(
    'message', 'Database initialization completed successfully',
    'schemas_created', ARRAY['documents', 'auth', 'events', 'audit'],
    'extensions_enabled', ARRAY['uuid-ossp', 'pg_stat_statements', 'pg_trgm', 'unaccent']
  ),
  'system',
  NOW()
);

-- Final message
DO $$
BEGIN
  RAISE NOTICE 'Database initialization completed successfully!';
  RAISE NOTICE 'Schemas created: documents, auth, events, audit';
  RAISE NOTICE 'Extensions enabled: uuid-ossp, pg_stat_statements, pg_trgm, unaccent';
  RAISE NOTICE 'User created: document_service';
END
$$;