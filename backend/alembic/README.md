# Database migrations (Alembic)

This project is wired for [Alembic](https://alembic.sqlalchemy.org/) but the
**baseline migration must be generated once in an environment that has the
dependencies installed and a database to connect to** (it cannot be hand-written
safely). `env.py` is already configured: it reads `DATABASE_URL` from the app
settings and uses `Base.metadata` (all models) as the autogenerate target.

Run every command below from the `backend/` directory.

## Current state

`core/database.create_all_tables()` still creates tables from the models for
fresh databases and applies the legacy column/type migrations
(`core/migrations.py:_NEW_COLUMNS`). It already **defers to Alembic**: if an
`alembic_version` table exists, the legacy migrations are skipped
(`database.py` → `_has_alembic_version`). So adopting Alembic is safe and
incremental — nothing breaks until you opt in per database.

## One-time activation

### 1. Generate the baseline from the current schema

```bash
# With a database that already has the current schema (e.g. a copy of prod, or a
# fresh DB after the app created the tables once):
alembic revision --autogenerate -m "baseline"
```

Review the generated file under `alembic/versions/`. For the baseline it should
match the existing schema (mostly `create_table`s). Commit it.

### 2a. Existing databases (already have the schema)

Mark them as being at the baseline **without** re-running it:

```bash
alembic stamp head
```

### 2b. Brand-new databases

```bash
alembic upgrade head
```

## Day-to-day

After changing a model under `backend/models/`:

```bash
alembic revision --autogenerate -m "add foo column to bar"
# review the file, then:
alembic upgrade head
```

Other useful commands:

```bash
alembic current        # which revision a DB is on
alembic history        # all revisions
alembic downgrade -1   # roll back one revision
alembic upgrade --sql  # emit SQL without touching the DB (offline mode)
```

## After full adoption

Once all environments are on Alembic, the legacy `_NEW_COLUMNS` list and
`apply_column_migrations` / `apply_type_migrations` in `core/migrations.py` can
be removed, and `create_all_tables()` can be reduced to (or replaced by)
`alembic upgrade head`.
