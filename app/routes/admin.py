"""
Admin API Routes - Dashboard, Settings, Processing, Drucker
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Router erstellen
router = APIRouter()

# Templates
templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


# ============================================================
# ADMIN SEITEN
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin Dashboard Seite"""
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "config": request.app.state.config.data,
        "modules": request.app.state.modules
    })


@router.get("/editor", response_class=HTMLResponse)
@router.get("/editor/{station}", response_class=HTMLResponse)
async def editor_page(request: Request, station: str = "default"):
    """Zuschnitt-Editor Seite"""
    return templates.TemplateResponse("editor.html", {
        "request": request,
        "station": station,
        "station_name": station.upper(),
        "color": "#ff6b6b" if station == "CW" else "#4ecdc4"
    })


@router.get("/settings/{station}/{settings_type}", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    station: str,
    settings_type: str
):
    """Einstellungen Seite (Face, Person, Clothing, Display, Carousel)"""
    icons = {
        "face": "👤",
        "person": "🚶",
        "clothing": "👕",
        "crop": "✂️",
        "display": "🖼️",
        "carousel": "🎠"
    }

    # Navigation für alle verfügbaren Typen
    nav_types = ["face", "person", "clothing", "crop", "display", "carousel"]

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "station": station,
        "station_name": station.upper(),
        "settings_type": settings_type.capitalize(),
        "settings_type_lower": settings_type,
        "icon": icons.get(settings_type, "⚙️"),
        "nav_types": nav_types
    })


# ============================================================
# STATUS API
# ============================================================

@router.get("/api/status")
async def get_admin_status(request: Request):
    """Gibt System-Status zurück"""
    config = request.app.state.config
    db = request.app.state.db
    
    # Uptime berechnen
    start_time = getattr(request.app.state, 'start_time', datetime.now())
    uptime = datetime.now() - start_time
    
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_formatted = f"{hours}h {minutes}m {seconds}s"
    
    return {
        "success": True,
        "modules": request.app.state.modules,
        "watcher_running": getattr(request.app.state, 'watcher_running', False),
        "statistics": db.get_statistics(),
        "uptime_formatted": uptime_formatted,
        "paths": {
            "input": str(config.get_path("input")),
            "temp": str(config.get_path("temp")),
            "processed": str(config.get_path("processed")),
            "output": str(config.get_path("output"))
        }
    }


# ============================================================
# SETTINGS API
# ============================================================

@router.get("/api/settings/{station}/{settings_type}")
async def get_settings(request: Request, station: str, settings_type: str):
    """Holt Einstellungen für Station und Typ"""
    db = request.app.state.db
    config = request.app.state.config
    
    # Aus Datenbank laden
    settings = db.get_settings(station, settings_type)
    
    # Falls leer, Defaults aus Config
    if not settings:
        settings = config.get(settings_type, {})
    
    return {
        "success": True,
        "station": station,
        "type": settings_type,
        "settings": settings
    }


@router.post("/api/settings/{station}/{settings_type}")
async def save_settings(request: Request, station: str, settings_type: str):
    """Speichert Einstellungen"""
    db = request.app.state.db
    
    try:
        data = await request.json()
        
        success = db.save_settings(station, settings_type, data)
        
        if success:
            return {"success": True, "message": "Einstellungen gespeichert"}
        else:
            return {"success": False, "message": "Speichern fehlgeschlagen"}
            
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.delete("/api/settings/{station}/{settings_type}")
async def delete_settings(request: Request, station: str, settings_type: str):
    """Löscht Einstellungen"""
    db = request.app.state.db
    
    success = db.delete_settings(station, settings_type)
    
    return {
        "success": success,
        "message": "Einstellungen gelöscht" if success else "Keine Einstellungen gefunden"
    }


# ============================================================
# PROCESSING API
# ============================================================

@router.post("/api/processing/start")
async def start_processing(request: Request):
    """Startet Verarbeitung aller Bilder"""
    from ..services.processor import ImageProcessor
    from ..services.analyzer import ImageAnalyzer
    
    config = request.app.state.config
    db = request.app.state.db
    
    try:
        analyzer = ImageAnalyzer(config)
        processor = ImageProcessor(config, db, analyzer)
        
        result = processor.process_all_pending()
        
        return {
            "success": True,
            "processed": result["processed"],
            "errors": result["errors"],
            "skipped": result["skipped"],
            "files": result["files"]
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/processing/single")
async def process_single(request: Request):
    """Verarbeitet einzelnes Bild"""
    from ..services.processor import ImageProcessor
    from ..services.analyzer import ImageAnalyzer
    
    config = request.app.state.config
    db = request.app.state.db
    
    try:
        data = await request.json()
        image_path = data.get("path")
        station = data.get("station", "default")
        
        if not image_path:
            return {"success": False, "error": "Kein Bildpfad angegeben"}
        
        analyzer = ImageAnalyzer(config)
        processor = ImageProcessor(config, db, analyzer)
        
        result = processor.process_image(image_path, station)
        
        if result:
            return {"success": True, "result": result}
        else:
            return {"success": False, "error": "Verarbeitung fehlgeschlagen"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/processing/stats")
async def get_processing_stats(request: Request):
    """Gibt Verarbeitungs-Statistiken zurück"""
    from ..services.processor import ImageProcessor
    
    config = request.app.state.config
    db = request.app.state.db
    
    processor = ImageProcessor(config, db)
    
    return {
        "success": True,
        "stats": processor.get_stats()
    }


# ============================================================
# WATCHER API
# ============================================================

@router.post("/api/watcher/start")
async def start_watcher(request: Request):
    """Startet Ordner-Überwachung"""
    from ..services.processor import ImageProcessor, FileWatcher
    from ..services.analyzer import ImageAnalyzer
    
    config = request.app.state.config
    db = request.app.state.db
    
    # Prüfen ob bereits läuft
    if getattr(request.app.state, 'watcher_running', False):
        return {"success": False, "message": "Watcher läuft bereits"}
    
    try:
        analyzer = ImageAnalyzer(config)
        processor = ImageProcessor(config, db, analyzer)
        watcher = FileWatcher(config, processor)
        
        success = watcher.start()
        
        if success:
            request.app.state.watcher = watcher
            request.app.state.watcher_running = True
            return {"success": True, "message": "Watcher gestartet"}
        else:
            return {"success": False, "message": "Watcher konnte nicht gestartet werden"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/watcher/stop")
async def stop_watcher(request: Request):
    """Stoppt Ordner-Überwachung"""
    watcher = getattr(request.app.state, 'watcher', None)
    
    if watcher:
        watcher.stop()
        request.app.state.watcher_running = False
        return {"success": True, "message": "Watcher gestoppt"}
    
    return {"success": False, "message": "Kein Watcher aktiv"}


@router.post("/api/watcher/toggle")
async def toggle_watcher(request: Request):
    """Wechselt Watcher-Status"""
    if getattr(request.app.state, 'watcher_running', False):
        return await stop_watcher(request)
    else:
        return await start_watcher(request)


# ============================================================
# BILDER API
# ============================================================

@router.get("/api/images")
async def get_images(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    station: str = None
):
    """Gibt alle verarbeiteten Bilder zurück"""
    db = request.app.state.db
    
    images = db.get_all_images(limit=limit, offset=offset)
    
    # Nach Station filtern
    if station:
        images = [img for img in images if station.lower() in img.get("filename", "").lower()]
    
    return {
        "success": True,
        "count": len(images),
        "images": images
    }


@router.delete("/api/images/{image_id}")
async def delete_image(request: Request, image_id: str):
    """Löscht ein Bild"""
    db = request.app.state.db
    
    success = db.delete_image(image_id)
    
    return {
        "success": success,
        "message": "Bild gelöscht" if success else "Bild nicht gefunden"
    }


@router.delete("/api/images")
async def delete_all_images(request: Request):
    """Löscht alle Bilder"""
    db = request.app.state.db
    
    count = db.clear_images()
    
    return {
        "success": True,
        "deleted": count,
        "message": f"{count} Bilder gelöscht"
    }


# ============================================================
# DRUCKER API
# ============================================================

@router.get("/api/printers")
async def get_printers(request: Request):
    """Gibt Drucker-Konfiguration zurück"""
    from ..services.printer import PrinterManager
    
    config = request.app.state.config
    db = request.app.state.db
    
    manager = PrinterManager(config, db)
    
    return {
        "success": True,
        "enabled": manager.enabled,
        "printers": manager.get_all_printers(),
        "stats": manager.get_stats()
    }


@router.post("/api/printers/{printer_type}")
async def update_printer(request: Request, printer_type: str):
    """Aktualisiert Drucker-Einstellungen"""
    from ..services.printer import PrinterManager
    
    config = request.app.state.config
    db = request.app.state.db
    
    try:
        data = await request.json()
        
        manager = PrinterManager(config, db)
        success = manager.update_printer(
            printer_type,
            name=data.get("name"),
            price=data.get("price"),
            enabled=data.get("enabled"),
            paper_size=data.get("paper_size"),
            page_orientation=data.get("page_orientation"),
            photo_width=data.get("photo_width"),
            photo_height=data.get("photo_height"),
            left_margin_photo=data.get("left_margin_photo"),
            top_margin_photo=data.get("top_margin_photo"),
            left_margin_text=data.get("left_margin_text"),
            top_margin_text=data.get("top_margin_text"),
            text_rotation_angle=data.get("text_rotation_angle"),
            text_font_name=data.get("text_font_name"),
            text_size=data.get("text_size"),
            text_color=data.get("text_color"),
            enable_print_date=data.get("enable_print_date")
        )
        
        if success:
            return {"success": True, "message": "Drucker aktualisiert"}
        else:
            return {"success": False, "message": "Unbekannter Drucker-Typ"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/printers/list-windows")
async def list_windows_printers(request: Request):
    """Listet Windows-Drucker auf"""
    from ..services.printer import PrinterManager
    
    printers = PrinterManager.list_windows_printers()
    
    return {
        "success": True,
        "printers": printers
    }


@router.post("/api/printers/test/{printer_type}")
async def test_printer(request: Request, printer_type: str):
    """Testet Drucker"""
    from ..services.printer import PrinterManager
    
    config = request.app.state.config
    db = request.app.state.db
    
    manager = PrinterManager(config, db)
    printer_info = manager.get_printer_info(printer_type)
    
    if not printer_info:
        return {"success": False, "message": "Unbekannter Drucker-Typ"}
    
    result = PrinterManager.test_printer(printer_info["name"])
    
    return result


# ============================================================
# KAMERA API
# ============================================================

@router.get("/api/camera/info")
async def get_camera_info(request: Request):
    """Gibt Kamera-Informationen zurück"""
    from ..services.camera import CameraHandler
    
    config = request.app.state.config
    camera = CameraHandler(config)
    
    return {
        "success": True,
        "info": camera.get_info(),
        "available_cameras": CameraHandler.list_cameras()
    }


@router.post("/api/camera/settings")
async def update_camera_settings(request: Request):
    """Aktualisiert Kamera-Einstellungen"""
    config = request.app.state.config
    
    try:
        data = await request.json()
        
        if "device_id" in data:
            config.set("camera.device_id", data["device_id"])
        if "width" in data:
            config.set("camera.width", data["width"])
        if "height" in data:
            config.set("camera.height", data["height"])
        if "flip_horizontal" in data:
            config.set("camera.flip_horizontal", data["flip_horizontal"])
        
        config.save()
        
        return {"success": True, "message": "Kamera-Einstellungen gespeichert"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/camera/test")
async def test_camera(request: Request):
    """Macht Testaufnahme"""
    from ..services.camera import CameraHandler
    
    config = request.app.state.config
    camera = CameraHandler(config)
    
    image_base64 = camera.capture_base64()
    camera.close()
    
    if image_base64:
        return {
            "success": True,
            "image": f"data:image/jpeg;base64,{image_base64}"
        }
    else:
        return {"success": False, "message": "Kamera-Aufnahme fehlgeschlagen"}


# ============================================================
# LOGS API
# ============================================================

@router.get("/api/logs")
async def get_logs(request: Request, lines: int = 100):
    """Gibt Log-Einträge zurück"""
    config = request.app.state.config
    log_path = config.get_path("logs") / "app.log"
    
    if not log_path.exists():
        return {"success": True, "logs": []}
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:]
        
        return {
            "success": True,
            "logs": [line.strip() for line in last_lines]
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/api/logs")
async def clear_logs(request: Request):
    """Löscht Logs"""
    import logging

    config = request.app.state.config
    log_path = config.get_path("logs") / "app.log"

    try:
        # Logging temporär abschalten
        root_logger = logging.getLogger()
        handlers_to_reopen = []

        # File Handler finden und schließen
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler) and str(log_path) in handler.baseFilename:
                handlers_to_reopen.append(handler)
                root_logger.removeHandler(handler)
                handler.close()

        # Datei löschen
        if log_path.exists():
            log_path.unlink()

        # Handler wieder öffnen
        for handler in handlers_to_reopen:
            # Neuen Handler mit gleicher Datei erstellen
            new_handler = logging.FileHandler(log_path, encoding='utf-8')
            new_handler.setLevel(handler.level)
            new_handler.setFormatter(handler.formatter)
            root_logger.addHandler(new_handler)

        return {"success": True, "message": "Logs gelöscht"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# SYSTEM API
# ============================================================

@router.post("/api/system/cleanup")
async def cleanup_temp(request: Request):
    """Räumt temporäre Dateien auf"""
    from ..services.processor import ImageProcessor
    
    config = request.app.state.config
    db = request.app.state.db
    
    processor = ImageProcessor(config, db)
    deleted = processor.cleanup_temp()
    
    return {
        "success": True,
        "deleted": deleted,
        "message": f"{deleted} temporäre Dateien gelöscht"
    }


@router.get("/api/config")
async def get_config(request: Request):
    """Gibt Konfiguration zurück"""
    config = request.app.state.config
    
    return {
        "success": True,
        "config": config.data
    }


@router.post("/api/config")
async def update_config(request: Request):
    """Aktualisiert Konfiguration"""
    config = request.app.state.config
    
    try:
        data = await request.json()
        
        for key, value in data.items():
            config.set(key, value)
        
        config.save()
        
        return {"success": True, "message": "Konfiguration gespeichert"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}
