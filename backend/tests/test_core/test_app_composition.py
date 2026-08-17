from fastapi.routing import APIRoute, APIWebSocketRoute

from backend.app.factory import create_app


def test_create_app_registers_health_and_analysis_websocket():
    app = create_app()
    http_routes = {route.path for route in app.routes if isinstance(route, APIRoute)}
    websocket_routes = {route.path for route in app.routes if isinstance(route, APIWebSocketRoute)}

    assert "/health" in http_routes
    assert "/ws/analysis/{task_id}" in websocket_routes


def test_websocket_route_is_owned_by_realtime_module():
    app = create_app()
    route = next(
        route
        for route in app.routes
        if isinstance(route, APIWebSocketRoute) and route.path == "/ws/analysis/{task_id}"
    )

    assert route.endpoint.__module__ == "backend.realtime.analysis_websocket"
