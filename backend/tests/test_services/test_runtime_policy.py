from types import SimpleNamespace

from backend.services.agent_settings_service import build_agent_runtime_state
from backend.trading_agents.agent_catalog import AgentInfo
from backend.trading_agents.graph.trading_graph import TradingAgentsGraph


def test_server_tool_disable_is_a_hard_ceiling():
    tool = SimpleNamespace(default_enabled=True)
    runtime_ctx = {
        "server_settings": {"news": {"enabled": False}},
        "user_settings": {"news": {"enabled": True}},
    }

    assert TradingAgentsGraph._is_tool_enabled(None, "news", tool, runtime_ctx) is False

def test_user_may_disable_but_not_revive_server_disabled_agent():
    agent = AgentInfo(
        key="test_agent",
        label="Test",
        description="",
        category="analyst",
        default_enabled=True,
    )
    disabled_server = SimpleNamespace(enabled=False, settings={})
    enabled_user = SimpleNamespace(enabled=True, settings={})
    disabled_user = SimpleNamespace(enabled=False, settings={})

    assert build_agent_runtime_state(agent, disabled_server, enabled_user)["enabled"] is False
    assert build_agent_runtime_state(agent, None, disabled_user)["enabled"] is False

def test_user_can_enable_default_disabled_agent_when_no_server_override():
    agent = AgentInfo(
        key="macro",
        label="Macro Analyst",
        description="",
        category="analyst",
        default_enabled=False,
    )
    enabled_user = SimpleNamespace(enabled=True, settings={})
    disabled_user = SimpleNamespace(enabled=False, settings={})

    assert build_agent_runtime_state(agent, None, None)["enabled"] is False
    assert build_agent_runtime_state(agent, None, enabled_user)["enabled"] is True
    assert build_agent_runtime_state(agent, None, disabled_user)["enabled"] is False
    disabled_server = SimpleNamespace(enabled=False, settings={})
    assert build_agent_runtime_state(agent, disabled_server, enabled_user)["enabled"] is False

