-- 0002 — RBAC, preferences & seed data
-- Permission-key RBAC (roles aggregate granular keys) and the global+user
-- preference layers, both stored as jsonb so new keys need no migration.

CREATE TABLE permissions (
    key          text PRIMARY KEY,
    description  text NOT NULL DEFAULT ''
);

CREATE TABLE roles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key         text NOT NULL UNIQUE,
    name        text NOT NULL,
    description text NOT NULL DEFAULT '',
    is_system   boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE role_permissions (
    role_id         uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_key  text NOT NULL REFERENCES permissions(key) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_key)
);

CREATE TABLE user_roles (
    user_id  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id  uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- ── Preferences (3-layer merge: defaults -> global -> user) ────────────────
CREATE TABLE app_settings (
    id    smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    data  jsonb NOT NULL DEFAULT '{}'::jsonb
);
INSERT INTO app_settings (id, data) VALUES (1, '{}'::jsonb);

CREATE TABLE user_preferences (
    user_id  uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data     jsonb NOT NULL DEFAULT '{}'::jsonb,
    revision bigint NOT NULL DEFAULT 0
);
CREATE TRIGGER trg_user_prefs_revision BEFORE INSERT OR UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION wv_set_revision();

-- ── Seed permission keys ───────────────────────────────────────────────────
INSERT INTO permissions (key, description) VALUES
    ('catalog.read',     'Read watched titles and statistics'),
    ('ingest.write',     'Import files and run provider syncs'),
    ('profiles.manage',  'Manage household members'),
    ('settings.manage',  'Manage global app settings'),
    ('plugins.manage',   'Configure plugins and secrets'),
    ('mcp.use',          'Use the MCP server'),
    ('mcp.tool.search',  'Use the MCP search tool'),
    ('mcp.tool.stats',   'Use the MCP statistics tool');

-- ── Seed roles ─────────────────────────────────────────────────────────────
INSERT INTO roles (key, name, description, is_system) VALUES
    ('admin',  'Administrator', 'Full household administration', true),
    ('member', 'Member',        'Standard household member',     true);

-- admin gets everything
INSERT INTO role_permissions (role_id, permission_key)
SELECT r.id, p.key FROM roles r CROSS JOIN permissions p WHERE r.key = 'admin';

-- member gets read + own ingest + mcp
INSERT INTO role_permissions (role_id, permission_key)
SELECT r.id, p.key FROM roles r CROSS JOIN permissions p
WHERE r.key = 'member'
  AND p.key IN ('catalog.read','ingest.write','mcp.use','mcp.tool.search','mcp.tool.stats');
