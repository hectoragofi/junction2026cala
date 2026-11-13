"""Standalone runner for the investor check page: `uvicorn app.diligence:app --port 8041`."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .cala import PERIMETER_DIR
from .agent import router as agent_router
from .investor import router

app = FastAPI(title="Perimeter investor check")
app.include_router(router)
app.include_router(agent_router)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(PERIMETER_DIR / "web" / "ask.html", headers={"Cache-Control": "no-cache"})
