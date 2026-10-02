---
name: database-migrations
description: Safe database schema migration patterns. Reference when creating or altering tables, adding indexes, running data backfills, or planning zero-downtime schema changes.
---

# Database Migration Patterns

Safe, reversible database schema changes for production systems.

## Core Principles

1. **Every change is a migration** — never alter production databases manually
2. **Migrations are immutable once deployed** — never edit a migration that has run in production
3. **Schema and data migrations are separate** — never mix DDL and DML in one migration
4. **Test against production-sized data** — a migration that works on 100 rows may lock on 10M rows
5. **Rollbacks use new forward migrations** — a "rollback" is just a new migration that undoes the change

## Migration Safety Checklist

Before applying any migration:

- [ ] New columns are nullable or have a default (never add NOT NULL without default on existing tables)
- [ ] Indexes are created concurrently, not inline (avoids write locks)
- [ ] Data backfill is a separate migration from the schema change
- [ ] Migration has been tested against a copy of production data
- [ ] Rollback plan is documented

## PostgreSQL Patterns

### Adding a Column Safely

```sql
-- GOOD: Nullable column — no lock
ALTER TABLE users ADD COLUMN avatar_url TEXT;

-- GOOD: Column with default (Postgres 11+: instant, no rewrite)
ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;

-- BAD: NOT NULL without default — rewrites every row, long lock
ALTER TABLE users ADD COLUMN role TEXT NOT NULL;
```

### Adding an Index Without Downtime

```sql
-- BAD: Blocks all writes during index build
CREATE INDEX idx_users_email ON users (email);

-- GOOD: Non-blocking, allows concurrent writes
CREATE INDEX CONCURRENTLY idx_users_email ON users (email);
-- Note: CONCURRENTLY cannot run inside a transaction block.
-- Most migration tools need special handling for this.
```

### Renaming a Column (Zero-Downtime — Expand-Contract)

Never rename directly in production. Use 3 separate migrations:

```sql
-- Migration 1: Add the new column
ALTER TABLE users ADD COLUMN display_name TEXT;

-- Migration 2 (data): Backfill
UPDATE users SET display_name = username WHERE display_name IS NULL;

-- [Deploy app that reads/writes both columns]

-- Migration 3: Drop the old column
ALTER TABLE users DROP COLUMN username;
```

### Large Data Migrations (Batching)

```sql
-- BAD: Updates all rows in one transaction — long lock
UPDATE users SET normalized_email = LOWER(email);

-- GOOD: Batch update, commits in chunks
DO $$
DECLARE
  batch_size INT := 10000;
  rows_updated INT;
BEGIN
  LOOP
    UPDATE users
    SET normalized_email = LOWER(email)
    WHERE id IN (
      SELECT id FROM users
      WHERE normalized_email IS NULL
      LIMIT batch_size
      FOR UPDATE SKIP LOCKED
    );
    GET DIAGNOSTICS rows_updated = ROW_COUNT;
    EXIT WHEN rows_updated = 0;
    COMMIT;
  END LOOP;
END $$;
```

## Prisma (TypeScript / Node.js)

```bash
# Create migration from schema changes
npx prisma migrate dev --name add_user_avatar

# Apply in production
npx prisma migrate deploy

# For operations Prisma can't express (e.g., CONCURRENTLY):
npx prisma migrate dev --create-only --name add_email_index
# Then manually edit the generated SQL file
```

```prisma
model User {
  id        String   @id @default(cuid())
  email     String   @unique
  name      String?
  avatarUrl String?  @map("avatar_url")
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")

  @@map("users")
  @@index([email])
}
```

## Drizzle (TypeScript / Node.js)

```bash
npx drizzle-kit generate   # Generate migration from schema
npx drizzle-kit migrate    # Apply migrations
npx drizzle-kit push       # Push directly (dev only, no migration file)
```

```typescript
import { pgTable, text, timestamp, uuid, boolean } from "drizzle-orm/pg-core";

export const users = pgTable("users", {
  id:        uuid("id").primaryKey().defaultRandom(),
  email:     text("email").notNull().unique(),
  name:      text("name"),
  isActive:  boolean("is_active").notNull().default(true),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});
```

## Django (Python)

```bash
python manage.py makemigrations          # Generate from model changes
python manage.py migrate                 # Apply
python manage.py showmigrations          # Show status
python manage.py makemigrations --empty app_name -n description  # Empty migration for custom SQL
```

### Data Migration (Django)

```python
from django.db import migrations

def backfill_display_names(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    batch_size = 5000
    qs = User.objects.filter(display_name="")
    while qs.exists():
        batch = list(qs[:batch_size])
        for user in batch:
            user.display_name = user.username
        User.objects.bulk_update(batch, ["display_name"], batch_size=batch_size)

class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_add_display_name")]
    operations = [
        migrations.RunPython(backfill_display_names, migrations.RunPython.noop),
    ]
```

### SeparateDatabaseAndState (Remove column safely)

```python
# Remove from Django model without dropping from DB yet:
class Migration(migrations.Migration):
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="user", name="legacy_field"),
            ],
            database_operations=[],  # Drop in the next migration
        ),
    ]
```

## Zero-Downtime Strategy (Expand-Contract)

```
Phase 1 — EXPAND
  Add new column/table (nullable or with default).
  Deploy: app writes to BOTH old and new.
  Run backfill migration.

Phase 2 — MIGRATE
  Deploy: app reads from NEW, writes to BOTH.
  Verify data consistency.

Phase 3 — CONTRACT
  Deploy: app only uses NEW.
  Run migration to drop old column/table.
```

## Anti-Patterns

| Anti-Pattern | Why It Fails | Fix |
|-------------|-------------|-----|
| Manual SQL in production | No audit trail, unrepeatable | Always use migration files |
| Editing a deployed migration | Causes drift between environments | New migration instead |
| NOT NULL without default on existing table | Full table rewrite + lock | Add nullable, backfill, then add constraint |
| `CREATE INDEX` on large table | Blocks writes during build | `CREATE INDEX CONCURRENTLY` |
| Schema + data in one migration | Hard to rollback, long transactions | Separate migrations |
| Dropping column before removing code | App errors on missing column | Remove code first, drop next deploy |
