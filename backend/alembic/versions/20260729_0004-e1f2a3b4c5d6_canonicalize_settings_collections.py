"""canonicalize settings collections and LLM fallback chain

Revision ID: e1f2a3b4c5d6
Revises: d7e8f9a0b1c2
Create Date: 2026-07-29 00:04:00.000000+00:00

``webhook_events`` was stored as either a JSON-looking text value or a legacy
comma-delimited string, while LLM failover used a fixed provider/model pair.
Both are now native JSON collections.  Existing app-settings rows and preset
snapshots are converted before the retired columns are removed.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    """Inspect online schemas; SQL generation emits the new columns."""
    if op.get_context().as_sql:
        return False
    inspector = sa.inspect(op.get_bind())
    return column in {item["name"] for item in inspector.get_columns(table)}


def _has_legacy_column(table: str, column: str) -> bool:
    """Baseline columns exist in an offline upgrade script by definition."""
    return True if op.get_context().as_sql else _has_column(table, column)


def _has_table(table: str) -> bool:
    return True if op.get_context().as_sql else sa.inspect(op.get_bind()).has_table(table)


def _install_normalizers() -> None:
    # Keep this data migration inside PostgreSQL rather than trusting a later
    # application process to see every row.  ``order_filled`` was the old UI
    # spelling for the real ``trade_executed`` event.  ``risk_breach`` had no
    # producer at all, so it is deliberately dropped instead of preserving a
    # notification switch that can never fire.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pg_temp.paperclip_webhook_events(raw text)
        RETURNS json
        LANGUAGE plpgsql
        AS $$
        DECLARE
            parsed json;
            item text;
            normalized text[] := ARRAY[]::text[];
        BEGIN
            raw := btrim(coalesce(raw, ''));
            IF raw = '' THEN
                RETURN '[]'::json;
            END IF;

            IF left(raw, 1) = '[' THEN
                BEGIN
                    parsed := raw::json;
                    IF json_typeof(parsed) <> 'array' THEN
                        RETURN '[]'::json;
                    END IF;
                    FOR item IN SELECT json_array_elements_text(parsed) LOOP
                        item := lower(btrim(item));
                        IF item = 'order_filled' THEN
                            item := 'trade_executed';
                        END IF;
                        IF item IN ('analysis_complete', 'trade_executed', 'alert_triggered', 'signal_flip')
                           AND NOT item = ANY(normalized) THEN
                            normalized := array_append(normalized, item);
                        END IF;
                    END LOOP;
                EXCEPTION WHEN others THEN
                    RETURN '[]'::json;
                END;
            ELSE
                FOR item IN SELECT lower(btrim(value)) FROM unnest(string_to_array(raw, ',')) AS value LOOP
                    IF item = 'order_filled' THEN
                        item := 'trade_executed';
                    END IF;
                    IF item IN ('analysis_complete', 'trade_executed', 'alert_triggered', 'signal_flip')
                       AND NOT item = ANY(normalized) THEN
                        normalized := array_append(normalized, item);
                    END IF;
                END LOOP;
            END IF;

            RETURN to_json(normalized);
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pg_temp.paperclip_normalize_preset_settings(raw text)
        RETURNS text
        LANGUAGE plpgsql
        AS $$
        DECLARE
            doc jsonb;
            events_raw text;
            provider text;
            model text;
        BEGIN
            BEGIN
                doc := raw::jsonb;
            EXCEPTION WHEN others THEN
                -- Keep an unrelated invalid preset untouched for operator
                -- repair; collection migration must not erase user data.
                RETURN raw;
            END;
            IF jsonb_typeof(doc) <> 'object' THEN
                RETURN raw;
            END IF;

            -- Older settings-page clients serialized the whole SettingsRead
            -- response when saving a preset.  These two values are response
            -- metadata, not editable settings; leaving them in a migrated
            -- preset makes the current strict preset parser reject it.
            doc := doc - 'updated_at' - 'active_preset_name';

            IF doc ? 'webhook_events' THEN
                IF jsonb_typeof(doc -> 'webhook_events') = 'string' THEN
                    events_raw := doc ->> 'webhook_events';
                ELSE
                    events_raw := (doc -> 'webhook_events')::text;
                END IF;
                doc := jsonb_set(
                    doc,
                    '{webhook_events}',
                    pg_temp.paperclip_webhook_events(events_raw)::jsonb,
                    true
                );
            END IF;

            IF doc ? 'fallback_llm_provider' OR doc ? 'fallback_llm_model' THEN
                provider := lower(btrim(coalesce(doc ->> 'fallback_llm_provider', '')));
                model := btrim(coalesce(doc ->> 'fallback_llm_model', ''));
                IF NOT doc ? 'fallback_llm_chain' THEN
                    IF provider <> '' AND model <> '' THEN
                        doc := jsonb_set(
                            doc,
                            '{fallback_llm_chain}',
                            jsonb_build_array(jsonb_build_object('provider', provider, 'model', model)),
                            true
                        );
                    ELSE
                        doc := jsonb_set(doc, '{fallback_llm_chain}', '[]'::jsonb, true);
                    END IF;
                END IF;
                doc := doc - 'fallback_llm_provider' - 'fallback_llm_model';
            END IF;
            RETURN doc::text;
        END;
        $$
        """
    )


def _install_downgrade_preset_normalizer() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pg_temp.paperclip_downgrade_preset_settings(raw text)
        RETURNS text
        LANGUAGE plpgsql
        AS $$
        DECLARE
            doc jsonb;
            first_fallback jsonb;
        BEGIN
            BEGIN
                doc := raw::jsonb;
            EXCEPTION WHEN others THEN
                RETURN raw;
            END;
            IF jsonb_typeof(doc) <> 'object' THEN
                RETURN raw;
            END IF;

            IF doc ? 'webhook_events' THEN
                -- The former DTO expected text, so retain the JSON array as
                -- a JSON string that its old parser understands.
                doc := jsonb_set(doc, '{webhook_events}', to_jsonb((doc -> 'webhook_events')::text), true);
            END IF;
            IF doc ? 'fallback_llm_chain' THEN
                first_fallback := doc -> 'fallback_llm_chain' -> 0;
                doc := doc - 'fallback_llm_chain';
                IF first_fallback IS NOT NULL AND jsonb_typeof(first_fallback) = 'object' THEN
                    doc := jsonb_set(doc, '{fallback_llm_provider}', to_jsonb(first_fallback ->> 'provider'), true);
                    doc := jsonb_set(doc, '{fallback_llm_model}', to_jsonb(first_fallback ->> 'model'), true);
                END IF;
            END IF;
            RETURN doc::text;
        END;
        $$
        """
    )


def upgrade() -> None:
    has_old_events = _has_legacy_column("app_settings", "webhook_events")
    has_old_fallback_provider = _has_legacy_column("app_settings", "fallback_llm_provider")
    has_old_fallback_model = _has_legacy_column("app_settings", "fallback_llm_model")

    if not _has_column("app_settings", "fallback_llm_chain"):
        op.add_column(
            "app_settings",
            sa.Column(
                "fallback_llm_chain",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'::json"),
            ),
        )
    if not _has_column("app_settings", "webhook_events_v2"):
        op.add_column(
            "app_settings",
            sa.Column(
                "webhook_events_v2",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[\"analysis_complete\"]'::json"),
            ),
        )

    _install_normalizers()
    if has_old_events:
        op.execute(
            """
            DO $$
            DECLARE retired_count integer;
            BEGIN
                SELECT count(*) INTO retired_count
                FROM app_settings
                WHERE webhook_events::text ILIKE '%risk_breach%';
                IF retired_count > 0 THEN
                    RAISE NOTICE
                        'Paperclip migration removed % retired risk_breach webhook selection(s): no event producer exists',
                        retired_count;
                END IF;
            END;
            $$
            """
        )
        op.execute("UPDATE app_settings SET webhook_events_v2 = pg_temp.paperclip_webhook_events(webhook_events::text)")
    if has_old_fallback_provider or has_old_fallback_model:
        provider = "fallback_llm_provider" if has_old_fallback_provider else "NULL"
        model = "fallback_llm_model" if has_old_fallback_model else "NULL"
        op.execute(
            f"""
            UPDATE app_settings
            SET fallback_llm_chain = CASE
                WHEN CASE
                    WHEN json_typeof(fallback_llm_chain) = 'array' THEN json_array_length(fallback_llm_chain)
                    ELSE 0
                END > 0 THEN fallback_llm_chain
                WHEN btrim(coalesce({provider}, '')) <> '' AND btrim(coalesce({model}, '')) <> ''
                THEN json_build_array(json_build_object(
                    'provider', lower(btrim({provider})),
                    'model', btrim({model})
                ))
                ELSE '[]'::json
            END
            """
        )
    if _has_table("config_presets"):
        op.execute(
            "UPDATE config_presets SET settings_json = pg_temp.paperclip_normalize_preset_settings(settings_json)"
        )

    if has_old_events:
        op.drop_column("app_settings", "webhook_events")
    op.alter_column("app_settings", "webhook_events_v2", new_column_name="webhook_events")
    if has_old_fallback_provider:
        op.drop_column("app_settings", "fallback_llm_provider")
    if has_old_fallback_model:
        op.drop_column("app_settings", "fallback_llm_model")
    op.alter_column("app_settings", "fallback_llm_chain", server_default=None)
    op.alter_column("app_settings", "webhook_events", server_default=None)


def downgrade() -> None:
    # A rollback can represent only the first fallback.  The current chain is
    # retained on forward upgrades; do not use downgrade as a data-preserving
    # way to switch application versions.
    if not _has_column("app_settings", "fallback_llm_provider"):
        op.add_column("app_settings", sa.Column("fallback_llm_provider", sa.String(length=50), nullable=True))
    if not _has_column("app_settings", "fallback_llm_model"):
        op.add_column("app_settings", sa.Column("fallback_llm_model", sa.String(length=100), nullable=True))
    if not _has_column("app_settings", "webhook_events_v1"):
        op.add_column(
            "app_settings",
            sa.Column(
                "webhook_events_v1",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[\"analysis_complete\"]'"),
            ),
        )

    op.execute(
        """
        UPDATE app_settings
        SET fallback_llm_provider = fallback_llm_chain -> 0 ->> 'provider',
            fallback_llm_model = fallback_llm_chain -> 0 ->> 'model',
            webhook_events_v1 = webhook_events::text
        """
    )
    if _has_table("config_presets"):
        _install_downgrade_preset_normalizer()
        op.execute(
            "UPDATE config_presets SET settings_json = pg_temp.paperclip_downgrade_preset_settings(settings_json)"
        )

    op.drop_column("app_settings", "webhook_events")
    op.alter_column("app_settings", "webhook_events_v1", new_column_name="webhook_events")
    op.drop_column("app_settings", "fallback_llm_chain")
    op.alter_column("app_settings", "webhook_events", server_default=None)
