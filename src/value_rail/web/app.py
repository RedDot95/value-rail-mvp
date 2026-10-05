"""FastAPI app factory. Run: uvicorn value_rail.web.app:create_app --factory"""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from ..domain.enums import STATUS_LABEL_DE, RouteStatus
from ..domain.money import fmt_eur, fmt_pct
from ..domain.timeutil import to_display, utcnow
from ..services import AppContext
from ..valuation.replay import replay_evaluation
from . import views

TEMPLATES_DIR = Path(__file__).parent / "templates"
_basic = HTTPBasic(auto_error=False)


def _templates() -> Jinja2Templates:
    t = Jinja2Templates(directory=str(TEMPLATES_DIR))
    t.env.filters["eur"] = fmt_eur
    t.env.filters["pct"] = fmt_pct
    t.env.filters["berlin"] = to_display
    t.env.filters["unk"] = lambda v: "unbekannt" if v in (None, "unknown") else v
    t.env.filters["status_de"] = lambda s: STATUS_LABEL_DE[RouteStatus(s)]
    return t


def create_app(ctx: AppContext | None = None) -> FastAPI:
    ctx = ctx or AppContext()
    templates = _templates()
    app = FastAPI(title="Value Rail MVP (Delivery 1, offline)", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx

    def auth(creds: HTTPBasicCredentials | None = Depends(_basic)) -> None:
        st = ctx.settings
        if not st.auth_enabled:
            return
        ok = creds is not None and secrets.compare_digest(creds.username.encode(), st.basic_user.encode()) \
            and secrets.compare_digest(creds.password.encode(), st.basic_password.encode())
        if not ok:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "auth required",
                                headers={"WWW-Authenticate": 'Basic realm="value-rail"'})

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok", "live_scanning": False, "mode": "offline-delivery-1"})

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def index(request: Request):
        with ctx.session_factory() as s:
            vm = views.dashboard(s, ctx.settings, utcnow())
        return templates.TemplateResponse(request, "dashboard.html", vm | {"settings": ctx.settings})

    @app.get("/status", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def status_page(request: Request):
        with ctx.session_factory() as s:
            vm = {"system": views.system_status(s, ctx.settings, utcnow())}
        return templates.TemplateResponse(request, "status.html", vm | {"settings": ctx.settings, "any_synthetic": True})

    @app.get("/evaluations/{ev_id}", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def detail(request: Request, ev_id: int):
        with ctx.session_factory() as s:
            vm = views.evaluation_detail(s, ev_id, ctx.settings, utcnow())
        if vm is None:
            raise HTTPException(404, "evaluation not found")
        return templates.TemplateResponse(request, "detail.html", vm | {"settings": ctx.settings,
                                                                        "any_synthetic": vm["ev"].is_synthetic})

    @app.get("/evaluations/{ev_id}/replay", dependencies=[Depends(auth)])
    def replay(ev_id: int):
        with ctx.session_factory() as s:
            try:
                return JSONResponse(replay_evaluation(s, ev_id).model_dump(mode="json"))
            except KeyError:
                raise HTTPException(404, "evaluation not found")

    @app.get("/api/evaluations", dependencies=[Depends(auth)])
    def api_evaluations():
        with ctx.session_factory() as s:
            from ..storage.repo import latest_evaluations
            return JSONResponse([{"id": e.id, "route_key": e.route_key, "status": e.status, "outputs": e.outputs,
                                  "rule_version_id": e.rule_version_id, "synthetic": e.is_synthetic,
                                  "evaluated_at_utc": e.evaluated_at.isoformat()} for e in latest_evaluations(s)])

    return app
