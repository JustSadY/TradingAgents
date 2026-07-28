from backend.api.deps import WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX, get_websocket_access_token


def test_websocket_auth_prefers_private_subprotocol_over_legacy_query_token():
    token = get_websocket_access_token(
        f"chat.v1, {WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX}header-token",
        query_token="legacy-token",
    )

    assert token == "header-token"


def test_websocket_auth_uses_legacy_token_only_when_no_private_protocol_exists():
    assert get_websocket_access_token(None, query_token="legacy-token") == "legacy-token"
    assert get_websocket_access_token("chat.v1", query_token="legacy-token") == "legacy-token"


def test_websocket_auth_rejects_empty_private_protocol_token():
    assert get_websocket_access_token(WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX) is None
