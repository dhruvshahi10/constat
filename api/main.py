"""Constat API. Run: uvicorn api.main:app --reload"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .deps import get_claim_store, get_repo, get_settings
from .routers import claims, evals, questionnaires, questions, review


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Constat API", version="1.0.0-rc1",
                  description="Claim-gated security answers. The system drafts, a person ships.")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                       allow_credentials=False, allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(ValueError)
    async def value_error(_: Request, e: ValueError):
        return JSONResponse(status_code=422, content={"error": str(e), "code": "INVALID"})

    @app.get("/healthz", tags=["ops"])
    def healthz():
        repo = get_repo()
        repo.count("principals")
        store = get_claim_store()
        return {"ok": True, "env": settings.env, "claim_store": settings.claim_store,
                "claims": len(store.list()) if settings.claim_store == "file" else "atlan"}

    app.include_router(claims.router)
    app.include_router(questionnaires.router)
    app.include_router(review.router)
    app.include_router(review.deals_router)
    app.include_router(questions.router)
    app.include_router(evals.router)
    return app


app = create_app()
