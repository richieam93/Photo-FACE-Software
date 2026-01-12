"""
FastAPI Hauptanwendung - Photo Software
"""

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import uvicorn

# Pfad zum App-Verzeichnis
APP_DIR = Path(__file__).parent
ROOT_DIR = APP_DIR.parent

# Imports
from .config import Config
from .database import Database

# ============================================================
# LIFESPAN - Start/Stop Events
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup und Shutdown Events"""
    # === STARTUP ===
    print("=" * 50)
    print("Photo Software startet...")
    print("=" * 50)
    
    # Config laden
    app.state.config = Config()
    app.state.config.load()
    print("Konfiguration geladen")
    
    # Datenbank initialisieren
    app.state.db = Database(app.state.config)
    app.state.db.load()
    print("Datenbank geladen ({} Bilder)".format(app.state.db.count_images()))
    
    # Ordner erstellen
    app.state.config.ensure_directories()
    print("Ordner erstellt/geprüft")
    
    # File Watcher
    app.state.watcher_running = False
    
    # Module prüfen
    app.state.modules = check_modules()
    print("Module geprüft")
    
    # Startzeit speichern
    from datetime import datetime
    app.state.start_time = datetime.now()
    
    print("=" * 50)
    print("Server läuft auf: http://localhost:8000")
    print("Admin: http://localhost:8000/admin/")
    print("=" * 50)
    
    yield
    
    # === SHUTDOWN ===
    print("\nServer wird beendet...")
    
    # Datenbank speichern
    app.state.db.save()
    print("Datenbank gespeichert")
    
    # Config speichern
    app.state.config.save()
    print("Konfiguration gespeichert")
    
    print("Auf Wiedersehen!")


def check_modules() -> dict:
    """Prüft verfügbare Module"""
    modules = {
        "face_recognition": False,
        "opencv": False,
        "yolo": False,
        "watchdog": False
    }
    
    try:
        import face_recognition
        modules["face_recognition"] = True
    except ImportError:
        pass
    
    try:
        import cv2
        modules["opencv"] = True
    except ImportError:
        pass
    
    try:
        from ultralytics import YOLO
        modules["yolo"] = True
    except ImportError:
        pass
    
    try:
        import watchdog
        modules["watchdog"] = True
    except ImportError:
        pass
    
    return modules


# ============================================================
# APP ERSTELLEN
# ============================================================

app = FastAPI(
    title="Photo Software",
    description="Foto-Analyse mit Gesichtserkennung und Kleidersuche",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files
static_path = APP_DIR / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Templates
templates_path = APP_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# ============================================================
# ROUTEN REGISTRIEREN
# ============================================================

from .routes import admin, customer, gallery

app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(customer.router, prefix="/customer", tags=["Customer"])
app.include_router(gallery.router, prefix="/gallery", tags=["Gallery"])

# ============================================================
# HAUPT-ROUTEN
# ============================================================

@app.get("/")
async def root():
    """Startseite - Weiterleitung zur Kundenseite"""
    return RedirectResponse(url="/customer/")


@app.get("/api/status")
async def api_status(request: Request):
    """API Status"""
    from datetime import datetime
    
    uptime = datetime.now() - request.app.state.start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return {
        "status": "online",
        "version": "1.0.0",
        "modules": request.app.state.modules,
        "images_count": request.app.state.db.count_images(),
        "watcher_running": request.app.state.watcher_running,
        "uptime": "{}h {}m {}s".format(hours, minutes, seconds)
    }


# ============================================================
# MAIN
# ============================================================

def run():
    """Server starten"""
    config = Config()
    config.load()
    
    host = config.get("server.host", "0.0.0.0")
    port = config.get("server.port", 8000)
    debug = config.get("server.debug", True)
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=debug
    )


if __name__ == "__main__":
    run()