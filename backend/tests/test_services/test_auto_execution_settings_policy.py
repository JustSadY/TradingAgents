from types import SimpleNamespace

from backend.services.settings_service import _enforce_auto_execution_safety


def _settings(**overrides):
    values = {
        "auto_execute_signals": False,
        "quality_gate_enabled": False,
        "decision_stability_mode": "shadow",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_enabling_auto_execution_forces_quality_and_stability_guards() -> None:
    fields = {"auto_execute_signals": True}

    _enforce_auto_execution_safety(_settings(), fields)

    assert fields["quality_gate_enabled"] is True
    assert fields["decision_stability_mode"] == "enforce"


def test_active_auto_execution_cannot_disable_its_safety_guards() -> None:
    fields = {"quality_gate_enabled": False, "decision_stability_mode": "off"}

    _enforce_auto_execution_safety(
        _settings(auto_execute_signals=True, quality_gate_enabled=True, decision_stability_mode="enforce"),
        fields,
    )

    assert fields["quality_gate_enabled"] is True
    assert fields["decision_stability_mode"] == "enforce"


def test_manual_only_mode_keeps_user_selected_guard_settings() -> None:
    fields = {"quality_gate_enabled": False, "decision_stability_mode": "shadow"}

    _enforce_auto_execution_safety(_settings(auto_execute_signals=False), fields)

    assert fields == {"quality_gate_enabled": False, "decision_stability_mode": "shadow"}
