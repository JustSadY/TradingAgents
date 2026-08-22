import asyncio
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.core.websocket import ws_manager

_logger = logging.getLogger(__name__)
router = APIRouter()

_WS_KEEPALIVE_MESSAGE = "__tradingagents_keepalive__"
_WS_AUTH_REVALIDATION_SECONDS = 30.0


async def _reject_websocket(
    websocket: WebSocket,
    *,
    code: int,
    reason: str,
    subprotocol: str | None = None,
) -> None:
    """Send a close frame the browser can diagnose after a rejected handshake."""
    await websocket.accept(subprotocol=subprotocol)
    await websocket.close(code=code, reason=reason)


async def _analysis_websocket_access_is_current(access_token: str, expected_user_id: int) -> bool:
    """Re-check a connected analysis socket's token and page entitlement."""
    from backend.api.deps import get_user_from_access_token, has_page_access
    from backend.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            user = await get_user_from_access_token(access_token, db)
        except HTTPException:
            return False
        if user.id != expected_user_id:
            return False
        return await has_page_access(db, user, "analysis")


@router.websocket("/ws/analysis/{task_id}")
async def websocket_analysis(
    websocket: WebSocket,
    task_id: str,
):
    from backend.api.deps import (
        get_user_from_access_token,
        get_websocket_access_token,
        get_websocket_application_subprotocol,
        has_page_access,
    )
    from backend.core.database import AsyncSessionLocal
    from backend.services.analysis_service import is_task_owner

    offered_subprotocols = websocket.headers.get("sec-websocket-protocol")
    selected_subprotocol = get_websocket_application_subprotocol(offered_subprotocols)
    if selected_subprotocol is None:
        await _reject_websocket(
            websocket,
            code=1002,
            reason="Unsupported WebSocket protocol",
        )
        return

    access_token = get_websocket_access_token(offered_subprotocols)
    if not access_token:
        await _reject_websocket(
            websocket,
            code=4001,
            reason="Unauthorized",
            subprotocol=selected_subprotocol,
        )
        return

    try:
        async with AsyncSessionLocal() as db:
            try:
                user = await get_user_from_access_token(access_token, db)
            except HTTPException:
                await _reject_websocket(
                    websocket,
                    code=4001,
                    reason="Unauthorized",
                    subprotocol=selected_subprotocol,
                )
                return
            page_allowed = await has_page_access(db, user, "analysis")
        if not page_allowed:
            await _reject_websocket(
                websocket,
                code=4003,
                reason="Forbidden",
                subprotocol=selected_subprotocol,
            )
            return
        if not await is_task_owner(task_id, user.id, user.is_admin):
            await _reject_websocket(
                websocket,
                code=4003,
                reason="Forbidden",
                subprotocol=selected_subprotocol,
            )
            return
    except Exception:
        _logger.exception("Analysis WebSocket initialization failed task=%s", task_id)
        try:
            await _reject_websocket(
                websocket,
                code=1011,
                reason="Initialization failed",
                subprotocol=selected_subprotocol,
            )
        except Exception:
            _logger.debug("Could not send WebSocket initialization failure task=%s", task_id, exc_info=True)
        return

    try:
        await ws_manager.connect(task_id, websocket, subprotocol=selected_subprotocol)
        _logger.info(
            "Analysis WebSocket connected task=%s user=%s protocol=%s",
            task_id,
            user.id,
            selected_subprotocol,
        )

        async def _revalidate_or_close() -> bool:
            try:
                is_current = await _analysis_websocket_access_is_current(access_token, user.id)
            except Exception:
                _logger.exception("Analysis WebSocket revalidation failed task=%s user=%s", task_id, user.id)
                await ws_manager.disconnect(task_id, websocket)
                try:
                    await websocket.close(code=1011, reason="Authorization check failed")
                except Exception:
                    _logger.debug("Could not close WebSocket after revalidation error task=%s", task_id, exc_info=True)
                return False
            if is_current:
                return True

            _logger.info("Analysis WebSocket authorization revoked task=%s user=%s", task_id, user.id)
            await ws_manager.disconnect(task_id, websocket)
            try:
                await websocket.close(code=4001, reason="Unauthorized")
            except Exception:
                _logger.debug("Could not close revoked WebSocket task=%s", task_id, exc_info=True)
            return False

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=_WS_AUTH_REVALIDATION_SECONDS)
            except TimeoutError:
                if not await _revalidate_or_close():
                    return
                continue
            except RuntimeError:
                # Starlette raises RuntimeError ("need to call accept first")
                # rather than WebSocketDisconnect once the socket has left the
                # connected state. `wait_for` cancels the pending receive on
                # every revalidation timeout, which can consume the disconnect
                # frame without surfacing it, so this is an ordinary client
                # disconnect and not a server fault worth an ERROR + traceback.
                _logger.debug("Analysis WebSocket already disconnected task=%s", task_id)
                await ws_manager.disconnect(task_id, websocket)
                return
            if message == _WS_KEEPALIVE_MESSAGE:
                if not await _revalidate_or_close():
                    return
                continue
    except WebSocketDisconnect as exc:
        await ws_manager.disconnect(task_id, websocket)
        if exc.code not in {1000, 1001}:
            _logger.warning("Analysis WebSocket disconnected abnormally task=%s code=%s", task_id, exc.code)
    except Exception:
        _logger.exception("WebSocket error for task=%s", task_id)
        await ws_manager.disconnect(task_id, websocket)
        try:
            await websocket.close(code=1011, reason="WebSocket error")
        except Exception:
            _logger.debug("Could not close failed WebSocket task=%s", task_id, exc_info=True)
