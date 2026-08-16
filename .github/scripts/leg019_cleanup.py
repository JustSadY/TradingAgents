from pathlib import Path


def replace_exact(path: str, old: str, new: str = "", count: int = 1) -> None:
    target = Path(path)
    text = target.read_text()
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} occurrence(s), found {actual}: {old!r}")
    target.write_text(text.replace(old, new))


def main() -> None:
    replace_exact(
        "backend/models/settings.py",
        "    max_risk_rounds: Mapped[int] = mapped_column(Integer, default=1)\n",
    )
    replace_exact("backend/models/page_permission.py", '        "max_risk_rounds",\n')
    replace_exact("backend/schemas/settings.py", "    max_risk_rounds: int = 1\n")
    replace_exact(
        "backend/schemas/settings.py",
        "    max_risk_rounds: int | None = Field(default=None, ge=1, le=10)\n",
    )
    replace_exact(
        "backend/services/analysis/config_builder.py",
        '        "max_risk_discuss_rounds": settings.max_risk_rounds,\n',
    )
    replace_exact(
        "backend/trading_agents/config.py",
        "    max_risk_discuss_rounds: int = Field(default=1, ge=1, le=10)\n",
    )
    replace_exact(
        "backend/trading_agents/graph/conditional_logic.py",
        "\n    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):\n"
        "        self.max_debate_rounds = max_debate_rounds\n"
        "        self.max_risk_discuss_rounds = max_risk_discuss_rounds",
    )
    replace_exact(
        "backend/trading_agents/graph/trading_graph.py",
        '        self.conditional_logic = ConditionalLogic(\n'
        '            max_debate_rounds=self.config["max_debate_rounds"],\n'
        '            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],\n'
        '        )\n',
        "        self.conditional_logic = ConditionalLogic()\n",
    )

    risk_tab = Path("frontend/src/components/settings/tabs/RiskTab.tsx")
    text = risk_tab.read_text()
    block = '''              <RiskRowItem label={t('settings.row_risk_rounds')} unit="tur">\n                <input\n                  type="number"\n                  min="1"\n                  max="10"\n                  className={CompactInputStyle}\n                  value={s.max_risk_rounds}\n                  onChange={e => update('max_risk_rounds', Number.parseInt(e.target.value))}\n                />\n              </RiskRowItem>\n\n'''
    if text.count(block) != 1:
        raise SystemExit("RiskTab: expected exactly one max_risk_rounds control")
    risk_tab.write_text(text.replace(block, ""))

    i18n = Path("frontend/src/i18n/settings.ts")
    lines = i18n.read_text().splitlines(keepends=True)
    matches = [line for line in lines if "'settings.row_risk_rounds':" in line]
    if len(matches) != 2:
        raise SystemExit(f"settings.ts: expected 2 risk-round translations, found {len(matches)}")
    i18n.write_text("".join(line for line in lines if "'settings.row_risk_rounds':" not in line))

    migration = Path("backend/alembic/versions/20260816_0022-cd34e5f6a7b8_remove_noop_risk_rounds.py")
    if migration.exists():
        raise SystemExit(f"{migration} already exists")
    migration.write_text(
        '''"""remove the retired no-op risk round setting

Revision ID: cd34e5f6a7b8
Revises: bc23d4e5f6a7
Create Date: 2026-08-16 13:55:00.000000+00:00

The current Risk Debate node performs one merged LLM call and never consumes
max_risk_rounds. The setting was persisted and editable despite having no
runtime effect, so remove the misleading contract and its database column.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "cd34e5f6a7b8"
down_revision: str | None = "bc23d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("app_settings", "max_risk_rounds")


def downgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("max_risk_rounds", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
'''
    )


if __name__ == "__main__":
    main()
