"""
Customer API Routes - Kundenbereich, Suche, Druck
"""

import os
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.templating import Jinja2Templates

# Services importieren (für Background Tasks)
from ..services.printer import PrinterManager

# Router erstellen
router = APIRouter()

# Templates
templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


# ============================================================
# KUNDEN SEITEN
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def customer_page(request: Request):
    """Kunden Hauptseite mit Karussell"""
    config = request.app.state.config
    db = request.app.state.db
    
    # Letzte Bilder für Karussell
    images = db.get_all_images(limit=50)
    
    # Carousel Settings aus Config holen
    carousel_settings = config.get("carousel", {})
    
    return templates.TemplateResponse("customer.html", {
        "request": request,
        "config": config.data,
        "images": images,
        "carousel_settings": carousel_settings
    })


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    """Such-Ergebnisseite"""
    return templates.TemplateResponse("search_results.html", {
        "request": request,
        "config": request.app.state.config.data
    })


# ============================================================
# KARUSSELL API
# ============================================================

@router.get("/api/carousel/images")
async def get_carousel_images(
    request: Request,
    limit: int = 50
):
    """Gibt Bilder für Karussell zurück"""
    db = request.app.state.db
    config = request.app.state.config

    # Carousel settings aus Datenbank laden
    carousel_settings = db.get_settings("default", "carousel")
    max_images = carousel_settings.get("max_images", 50) if carousel_settings else 50

    # Limit auf max_images beschränken
    effective_limit = min(limit, max_images)

    images = db.get_all_images(limit=effective_limit)

    # Nur relevante Daten für Karussell
    carousel_images = []
    for img in images:
        carousel_images.append({
            "id": img.get("id"),
            "filename": img.get("filename"),
            "timestamp": img.get("timestamp"),
            "output_path": img.get("output_path"),
            "face_count": img.get("face_count", 0),
            "person_count": img.get("person_count", 0),
            "clothing_colors": img.get("clothing_colors", [])
        })

    return {
        "success": True,
        "count": len(carousel_images),
        "images": carousel_images,
        "settings": carousel_settings or {}
    }


@router.get("/api/carousel/settings")
async def get_carousel_settings(request: Request):
    """Gibt Karussell-Einstellungen zurück"""
    config = request.app.state.config
    
    return {
        "success": True,
        "settings": config.get("carousel", {})
    }


# ============================================================
# KAMERA API (Kundenbereich)
# ============================================================

@router.get("/api/camera/stream")
async def camera_stream(request: Request):
    """MJPEG Kamera-Stream"""
    from ..services.camera import CameraHandler
    
    config = request.app.state.config
    camera = CameraHandler(config)
    
    return StreamingResponse(
        camera.generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.post("/api/camera/capture")
async def capture_photo(request: Request):
    """Nimmt Foto für Suche auf"""
    from ..services.camera import CameraHandler
    
    config = request.app.state.config
    camera = CameraHandler(config)
    
    image_base64 = camera.capture_base64()
    camera.close()
    
    if image_base64:
        return {
            "success": True,
            "image": f"data:image/jpeg;base64,{image_base64}",
            "image_data": image_base64
        }
    else:
        return {"success": False, "message": "Aufnahme fehlgeschlagen"}


# ============================================================
# SUCH API
# ============================================================

@router.post("/api/search/face")
async def search_by_face(request: Request):
    """Sucht nach Gesicht"""
    from ..services.searcher import ImageSearcher
    from ..services.analyzer import ImageAnalyzer
    import base64
    import tempfile
    
    config = request.app.state.config
    db = request.app.state.db
    
    try:
        data = await request.json()
        image_data = data.get("image")  # Base64 encoded
        
        if not image_data:
            return {"success": False, "message": "Kein Bild übermittelt"}
        
        # Base64 dekodieren und temporär speichern
        if image_data.startswith("data:"):
            image_data = image_data.split(",")[1]
        
        image_bytes = base64.b64decode(image_data)
        
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(image_bytes)
            temp_path = f.name
        
        # Face Encoding extrahieren
        analyzer = ImageAnalyzer(config)
        encoding = analyzer.get_face_encoding(temp_path)
        
        # Temp-Datei löschen
        os.unlink(temp_path)
        
        if not encoding:
            return {
                "success": False,
                "message": "Kein Gesicht im Foto erkannt. Bitte erneut versuchen."
            }
        
        # Suche durchführen
        searcher = ImageSearcher(config, db)
        results = searcher.search_by_face(encoding)
        
        return {
            "success": True,
            "count": len(results),
            "results": results
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/search/color")
async def search_by_color(request: Request):
    """Sucht nach Kleiderfarben"""
    from ..services.searcher import ImageSearcher
    
    config = request.app.state.config
    db = request.app.state.db
    
    try:
        data = await request.json()
        colors = data.get("colors", [])  # [{"rgb": [r,g,b]}, ...]
        
        if not colors:
            return {"success": False, "message": "Keine Farben ausgewählt"}
        
        searcher = ImageSearcher(config, db)
        results = searcher.search_by_color(colors)
        
        return {
            "success": True,
            "count": len(results),
            "results": results
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/search/combined")
async def search_combined(request: Request):
    """Kombinierte Suche (Gesicht + Farben)"""
    from ..services.searcher import ImageSearcher
    from ..services.analyzer import ImageAnalyzer
    import base64
    import tempfile
    
    config = request.app.state.config
    db = request.app.state.db
    
    try:
        data = await request.json()
        image_data = data.get("image")
        colors = data.get("colors", [])
        face_weight = data.get("face_weight", 0.7)
        color_weight = data.get("color_weight", 0.3)
        
        encoding = None
        
        # Face Encoding extrahieren falls Bild vorhanden
        if image_data:
            if image_data.startswith("data:"):
                image_data = image_data.split(",")[1]
            
            image_bytes = base64.b64decode(image_data)
            
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(image_bytes)
                temp_path = f.name
            
            analyzer = ImageAnalyzer(config)
            encoding = analyzer.get_face_encoding(temp_path)
            os.unlink(temp_path)
        
        # Suche durchführen
        searcher = ImageSearcher(config, db)
        results = searcher.search(
            face_encoding=encoding,
            colors=colors if colors else None,
            face_weight=face_weight,
            color_weight=color_weight
        )
        
        return {
            "success": True,
            "count": len(results),
            "results": results,
            "face_detected": encoding is not None
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# DRUCK API
# ============================================================

@router.post("/api/print")
async def print_image(background_tasks: BackgroundTasks, request: Request):
    """Druckt ein Bild"""
    from ..services.printer import PrinterManager

    config = request.app.state.config
    db = request.app.state.db

    try:
        data = await request.json()

        image_id = data.get("image_id")
        printer_type = data.get("printer_type", "small")
        copies = data.get("copies", 1)

        if not image_id:
            return {"success": False, "message": "Keine Bild-ID angegeben"}

        # Bild aus Datenbank holen
        image_data = db.get_image(image_id)

        if not image_data:
            return {"success": False, "message": f"Bild mit ID '{image_id}' nicht gefunden"}

        image_path = image_data.get("original_path")

        if not image_path or not Path(image_path).exists():
            return {"success": False, "message": f"Bilddatei nicht gefunden: {image_path}"}

        # Druckauftrag im Hintergrund starten
        background_tasks.add_task(
            perform_print_job,
            config,
            db,
            image_path,
            printer_type,
            copies
        )

        # Sofortige Rückmeldung
        return {
            "success": True,
            "message": "Druckauftrag wurde gestartet",
            "printer_type": printer_type,
            "copies": copies
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def perform_print_job(config, db, image_path: str, printer_type: str, copies: int):
    """Führt Druckauftrag im Hintergrund aus"""
    try:
        manager = PrinterManager(config, db)
        result = manager.print_image(image_path, printer_type, copies)

        if result["success"]:
            print(f"✅ Hintergrund-Druck erfolgreich: {Path(image_path).name}")
        else:
            print(f"❌ Hintergrund-Druck fehlgeschlagen: {result.get('error', 'Unbekannter Fehler')}")

    except Exception as e:
        print(f"❌ Hintergrund-Druck Fehler: {e}")


@router.get("/api/print/price")
async def get_print_price(
    request: Request,
    printer_type: str = "small",
    copies: int = 1
):
    """Gibt Druckpreis zurück"""
    from ..services.printer import PrinterManager
    
    config = request.app.state.config
    db = request.app.state.db
    
    manager = PrinterManager(config, db)
    price = manager.get_price(printer_type, copies)
    
    printer_info = manager.get_printer_info(printer_type)
    
    return {
        "success": True,
        "printer_type": printer_type,
        "copies": copies,
        "price_per_copy": printer_info["price"] if printer_info else 0,
        "total_price": price,
        "currency": "CHF"
    }


@router.get("/api/print/options")
async def get_print_options(request: Request):
    """Gibt Druck-Optionen zurück"""
    from ..services.printer import PrinterManager
    
    config = request.app.state.config
    db = request.app.state.db
    
    manager = PrinterManager(config, db)
    
    return {
        "success": True,
        "enabled": manager.enabled,
        "options": manager.get_all_printers()
    }


# ============================================================
# BILD API
# ============================================================

@router.get("/api/image/{image_id}")
async def get_image_data(request: Request, image_id: str):
    """Gibt Bild-Daten zurück"""
    db = request.app.state.db
    
    image_data = db.get_image(image_id)
    
    if not image_data:
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")
    
    return {
        "success": True,
        "image": image_data
    }


@router.get("/api/image/{image_id}/file")
async def get_image_file(request: Request, image_id: str, original: bool = False):
    """Gibt Bilddatei zurück"""
    db = request.app.state.db

    image_data = db.get_image(image_id)

    if not image_data:
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")

    # Wähle Pfad basierend auf Parameter
    if original:
        image_path = image_data.get("original_path")
    else:
        image_path = image_data.get("output_path")

    if not image_path or not Path(image_path).exists():
        raise HTTPException(status_code=404, detail="Bilddatei nicht gefunden")

    return FileResponse(
        image_path,
        media_type="image/jpeg",
        filename=image_data.get("filename", "image.jpg")
    )


@router.get("/api/image/{image_id}/annotated")
async def get_annotated_image(request: Request, image_id: str):
    """Gibt annotiertes Bild zurück"""
    db = request.app.state.db
    
    image_data = db.get_image(image_id)
    
    if not image_data:
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")
    
    image_path = image_data.get("processed_path")
    
    if not image_path or not Path(image_path).exists():
        # Fallback auf normales Bild
        image_path = image_data.get("output_path")
    
    if not image_path or not Path(image_path).exists():
        raise HTTPException(status_code=404, detail="Bilddatei nicht gefunden")
    
    return FileResponse(
        image_path,
        media_type="image/jpeg",
        filename=f"annotated_{image_data.get('filename', 'image.jpg')}"
    )


# ============================================================
# FARB-PALETTE
# ============================================================

@router.get("/api/colors/palette")
async def get_color_palette(request: Request):
    """Gibt vordefinierte Farbpalette zurück"""
    palette = [
        {"name": "Rot", "hex": "#ff0000", "rgb": [255, 0, 0]},
        {"name": "Dunkelrot", "hex": "#8b0000", "rgb": [139, 0, 0]},
        {"name": "Orange", "hex": "#ffa500", "rgb": [255, 165, 0]},
        {"name": "Gelb", "hex": "#ffff00", "rgb": [255, 255, 0]},
        {"name": "Grün", "hex": "#00ff00", "rgb": [0, 255, 0]},
        {"name": "Dunkelgrün", "hex": "#006400", "rgb": [0, 100, 0]},
        {"name": "Türkis", "hex": "#00ced1", "rgb": [0, 206, 209]},
        {"name": "Blau", "hex": "#0000ff", "rgb": [0, 0, 255]},
        {"name": "Dunkelblau", "hex": "#00008b", "rgb": [0, 0, 139]},
        {"name": "Lila", "hex": "#800080", "rgb": [128, 0, 128]},
        {"name": "Pink", "hex": "#ff69b4", "rgb": [255, 105, 180]},
        {"name": "Braun", "hex": "#8b4513", "rgb": [139, 69, 19]},
        {"name": "Beige", "hex": "#f5f5dc", "rgb": [245, 245, 220]},
        {"name": "Weiß", "hex": "#ffffff", "rgb": [255, 255, 255]},
        {"name": "Grau", "hex": "#808080", "rgb": [128, 128, 128]},
        {"name": "Schwarz", "hex": "#000000", "rgb": [0, 0, 0]}
    ]
    
    return {
        "success": True,
        "colors": palette
    }
