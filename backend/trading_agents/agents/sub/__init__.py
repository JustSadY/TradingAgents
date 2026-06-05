"""
Tier-2 Sub-Agents.

Reasoning units invoked *inside* a Tier-1 Main Agent node (see ``agents/main/``).
Grouped by role:

  analysts/     — market, social, news, fundamentals, macro, options, quant,
                  earnings, review (tool-using data analysts)
  researchers/  — bull, bear (investment debate)
  risk_mgmt/    — aggressive, conservative, neutral (risk debate)
  managers/     — synthesis, auditor, research manager, portfolio manager
  trader/       — execution planner

These modules keep using absolute imports, so they are orchestrated by the main
agents without any per-file wiring here.
"""
