# Database migrations (Alembic)

PostgreSQL schema changes are versioned with
[Alembic](https://alembic.sqlalchemy.org/). The checked-in baseline revision
(`89f1a049b357`) and all later revisions are the source of truth for a
PostgreSQL deployment.

Run the commands below from `backend/`.

## Runtime behaviour

- A fresh PostgreSQL database runs `alembic upgrade head` during application
  startup.
- A complete pre-Alembic installation is stamped at the checked-in baseline,
  then upgraded through every later revision. Startup refuses to stamp a
  partial schema because that would claim missing baseline tables exist.
- SQLite is only the lightweight local development/test path. It builds its
  schema from the ORM metadata with `Base.metadata.create_all` and has no
  migration history at all; it is not a substitute for PostgreSQL Alembic
  revisions. An existing SQLite file is never migrated — delete it to pick up
  model changes.

## Upgrade an existing database

Back up the database first, then let the application startup upgrade it or run:

```bash
alembic upgrade head
```

For an already-complete, unversioned installation, use the application startup
path so its baseline-safety check runs. If it reports a partial schema, restore
or repair that schema before stamping any revision manually.

## Day-to-day changes

After changing a model under `backend/models/`:

```bash
alembic revision --autogenerate -m "describe the schema change"
# Review the generated file, including data migration and downgrade safety.
alembic upgrade head
```

Useful checks:

```bash
alembic current
alembic heads
alembic history
alembic upgrade --sql
```

Do not edit an applied historical revision to change a production schema. Add
a new revision that converts existing data before removing retired columns or
formats.
