
import threading
import time


from fastapi import FastAPI
from app.db.init_db import init_db
from app.routers import auth, tenant, ticket, comments, users
from app.routers import providers
from app.services.sla_monitor import check_sla
from app.routers import sla
from app.core.config import settings

from fastapi.middleware.cors import CORSMiddleware



def _parse_cors_origins(value: str) -> list[str]:
    raw = [part.strip() for part in value.replace(";", ",").split(",")]
    origins = [o.rstrip("/") for o in raw if o]
    return origins or []


app = FastAPI(title="AI Ticketing System")
origins = _parse_cors_origins(settings.cors_origins)
allow_credentials = True
if origins == ["*"]:
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.on_event("startup")
def startup():
    init_db()
    threading.Thread(target=sla_background_job, daemon=True).start()

app.include_router(auth.router)
app.include_router(tenant.router)
app.include_router(ticket.router)
app.include_router(comments.router)
app.include_router(users.router)
app.include_router(providers.router)
app.include_router(sla.router)

def sla_background_job():
    while True:
        check_sla()
        time.sleep(30)   # runs every 30 sec




@app.get("/")
def home():
    return {"message": "Backend running"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    return {"status": "ready"}

@app.get("/ping")
def ping():
    return {"message": "pong"}
