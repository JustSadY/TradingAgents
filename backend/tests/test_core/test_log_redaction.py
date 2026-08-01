from collections import OrderedDict

def test_dynamic_redaction_literals_are_bounded_lru(monkeypatch):
    from backend.core import log_redaction

    monkeypatch.setattr(log_redaction, "_DYNAMIC_LITERALS", OrderedDict())
    monkeypatch.setattr(log_redaction, "_MAX_DYNAMIC_LITERALS", 2)

    log_redaction.register_sensitive_literal("first-secret")
    log_redaction.register_sensitive_literal("second-secret")
    log_redaction.register_sensitive_literal("first-secret")
    log_redaction.register_sensitive_literal("third-secret")

    assert list(log_redaction._DYNAMIC_LITERALS) == ["first-secret", "third-secret"]
    assert log_redaction.redact_text("first-secret third-secret") == "***REDACTED*** ***REDACTED***"
    assert log_redaction.redact_text("second-secret") == "second-secret"

def test_dynamic_redaction_prefers_longer_overlapping_literals(monkeypatch):
    from backend.core import log_redaction

    monkeypatch.setattr(log_redaction, "_DYNAMIC_LITERALS", OrderedDict())
    log_redaction.register_sensitive_literal("https://hooks.example/token")
    log_redaction.register_sensitive_literal("https://hooks.example/token/longer")

    assert log_redaction.redact_text("url=https://hooks.example/token/longer") == "url=***REDACTED***"
