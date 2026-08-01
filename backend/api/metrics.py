import secrets

from fastapi import APIRouter, HTTPException, Request, Response

from backend.core.config import get_settings
from backend.core.metrics import render_latest

router = APIRouter(tags=["metrics"])

@router.get(
    "/metrics",
    include_in_schema=False,
    responses={401: {"description": "Invalid metrics token"}, 404: {"description": "Metrics disabled"}},
)
async def metrics(request: Request):
    token = get_settings().METRICS_TOKEN
    if not token:
        raise HTTPException(status_code=404, detail="Not Found")
    auth = request.headers.get("authorization", "")
    if not secrets.compare_digest(auth, f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="Invalid metrics token")
    payload, content_type = render_latest()
    return Response(content=payload, media_type=content_type)
