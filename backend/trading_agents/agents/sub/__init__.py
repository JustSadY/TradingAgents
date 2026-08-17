"""
Tier-2 Sub-Agents.

Reasoning units invoked inside Tier-1 Main Agent nodes (see ``agents/main/``).
Grouped by role:

  analysts/     — 12 market/data evidence analyst plugins
  researchers/  — bull and bear thesis researchers
  managers/     — synthesis, auditor, research, and portfolio-manager helpers

Risk evaluation is owned by the single Tier-1 ``main/risk.py`` panel node; there
is no separate risk-management sub-agent package.
"""
