"""The tool registry is populated only by importing the bootstrap module.

`bootstrap.py` was emptied at one point and nothing noticed: the app started,
`/api/meta` answered, the settings panels rendered, and every agent tool had
silently disappeared. Registration by import side-effect has no failure mode
that surfaces on its own, so it needs a test that looks at the result.
"""

from __future__ import annotations

import pkgutil

from backend.trading_agents.agents.tools import builtin, registry


def test_bootstrap_registers_the_builtin_tools():
    import backend.trading_agents.agents.tools.bootstrap  # noqa: F401

    assert registry.list(), "importing bootstrap registered no tools"


def test_bootstrap_imports_every_builtin_module():
    """A new module under `builtin/` has to be added to the bootstrap import.

    Nothing else imports these modules, so one left out of the list registers
    nothing while looking entirely healthy in review.
    """
    import backend.trading_agents.agents.tools.bootstrap as bootstrap

    on_disk = {module.name for module in pkgutil.iter_modules(builtin.__path__)}
    imported = {name for name in vars(bootstrap) if not name.startswith("_")}

    assert on_disk - imported == set()


def test_every_registered_tool_has_a_unique_key_and_langchain_tools():
    import backend.trading_agents.agents.tools.bootstrap  # noqa: F401

    tools = registry.list()
    keys = [tool.key for tool in tools]

    assert len(keys) == len(set(keys))
    for tool in tools:
        assert tool.langchain_tool_names, f"{tool.key} exposes no LangChain tool"
