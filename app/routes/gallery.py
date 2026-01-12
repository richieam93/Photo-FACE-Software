"""
Gallery API Routes - Einfache Galerie + Karussell
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

# Router erstellen
router = APIRouter()

# Templates
templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


# ============================================================
# GALERIE SEITEN
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def gallery_page(request: Request):
    """Einfache Galerie Seite (ohne Analyse)"""
    config = request.app.state.config
    db = request.app.state.db
    
    images = db.get_all_images(limit=100)
    
    return templates.TemplateResponse("gallery.html", {
        "request": request,
        "config": config.data,
        "images": images
    })


# ============================================================
# GALERIE API
# ============================================================

@router.get("/api/images")
async def get_gallery_images(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str = None,
    date_from: str = None,
    date_to: str = None,
    start_hour: int = Query(None, ge=0, le=23),
    start_minute: int = Query(None, ge=0, le=59),
    end_hour: int = Query(None, ge=0, le=23),
    end_minute: int = Query(None, ge=0, le=59),
    sort: str = "newest"
):
    """
    Gibt Galerie-Bilder zurück mit Filter-Optionen

    Args:
        limit: Maximale Anzahl
        offset: Start-Index
        search: Suchbegriff (Dateiname)
        date_from: Datum von (YYYY-MM-DD)
        date_to: Datum bis (YYYY-MM-DD)
        start_hour: Startstunde (0-23)
        start_minute: Startminute (0-59)
        end_hour: Endstunde (0-23)
        end_minute: Endminute (0-59)
        sort: Sortierung (newest, oldest, name)
    """
    db = request.app.state.db

    # Alle Bilder holen
    all_images = db.get_all_images()

    # Filtern
    filtered = all_images

    # Nach Name suchen
    if search:
        search_lower = search.lower()
        filtered = [
            img for img in filtered
            if search_lower in img.get("filename", "").lower()
        ]

    # Nach Datum filtern
    if date_from:
        try:
            from_date = datetime.fromisoformat(date_from)
            filtered = [
                img for img in filtered
                if datetime.fromisoformat(img.get("timestamp", "2000-01-01")[:10]) >= from_date
            ]
        except:
            pass

    if date_to:
        try:
            to_date = datetime.fromisoformat(date_to)
            filtered = [
                img for img in filtered
                if datetime.fromisoformat(img.get("timestamp", "2099-12-31")[:10]) <= to_date
            ]
        except:
            pass

    # Nach Uhrzeit filtern
    if start_hour is not None and end_hour is not None:
        filtered = [
            img for img in filtered
            if _is_time_in_range(img.get("timestamp", ""), start_hour, start_minute or 0, end_hour, end_minute or 0)
        ]

    # Sortieren
    if sort == "oldest":
        filtered.sort(key=lambda x: x.get("timestamp", ""))
    elif sort == "name":
        filtered.sort(key=lambda x: x.get("filename", ""))
    else:  # newest (default)
        filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # Pagination
    total = len(filtered)
    paginated = filtered[offset:offset + limit]

    # Nur relevante Daten
    gallery_images = []
    for img in paginated:
        gallery_images.append({
            "id": img.get("id"),
            "filename": img.get("filename"),
            "timestamp": img.get("timestamp"),
            "time_formatted": _format_time(img.get("timestamp")),
            "output_path": img.get("output_path"),
            "face_count": img.get("face_count", 0),
            "person_count": img.get("person_count", 0)
        })

    return {
        "success": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(gallery_images),
        "images": gallery_images
    }


@router.get("/api/image/{image_id}")
async def get_single_image(request: Request, image_id: str):
    """Gibt einzelnes Bild mit Details zurück"""
    db = request.app.state.db
    
    image = db.get_image(image_id)
    
    if not image:
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")
    
    return {
        "success": True,
        "image": {
            **image,
            "time_formatted": _format_time(image.get("timestamp"))
        }
    }


@router.get("/api/search")
async def search_gallery(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Sucht in Galerie nach Dateiname oder Zeit
    
    Args:
        q: Suchbegriff
        limit: Maximale Ergebnisse
    """
    db = request.app.state.db
    
    results = db.search_images(q)[:limit]
    
    # Formatieren
    formatted = []
    for img in results:
        formatted.append({
            "id": img.get("id"),
            "filename": img.get("filename"),
            "timestamp": img.get("timestamp"),
            "time_formatted": _format_time(img.get("timestamp")),
            "face_count": img.get("face_count", 0),
            "person_count": img.get("person_count", 0)
        })
    
    return {
        "success": True,
        "query": q,
        "count": len(formatted),
        "results": formatted
    }


# ============================================================
# BILD-DATEIEN
# ============================================================

@router.get("/image/{image_id}")
async def serve_image(request: Request, image_id: str, original: bool = True):
    """Liefert Bilddatei aus"""
    db = request.app.state.db

    image = db.get_image(image_id)

    if not image:
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")

    # Wähle Pfad basierend auf Parameter
    if original:
        image_path = image.get("original_path")
    else:
        image_path = image.get("output_path")

    if not image_path or not Path(image_path).exists():
        raise HTTPException(status_code=404, detail="Bilddatei nicht gefunden")

    return FileResponse(
        image_path,
        media_type="image/jpeg",
        filename=image.get("filename", "image.jpg")
    )


@router.get("/thumbnail/{image_id}")
async def serve_thumbnail(request: Request, image_id: str, size: int = 200, original: bool = False):
    """Liefert Thumbnail aus (generiert bei Bedarf)"""
    from PIL import Image
    import io
    from fastapi.responses import Response

    db = request.app.state.db

    image_data = db.get_image(image_id)

    if not image_data:
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")

    # Wähle Pfad basierend auf Parameter
    if original:
        image_path = image_data.get("original_path")
    else:
        image_path = image_data.get("output_path") or image_data.get("original_path")

    if not image_path or not Path(image_path).exists():
        raise HTTPException(status_code=404, detail="Bilddatei nicht gefunden")
    
    try:
        # Thumbnail erstellen
        img = Image.open(image_path)
        img.thumbnail((size, size))
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=80)
        buffer.seek(0)
        
        return Response(
            content=buffer.getvalue(),
            media_type="image/jpeg"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# STATISTIKEN
# ============================================================

@router.get("/api/stats")
async def get_gallery_stats(request: Request):
    """Gibt Galerie-Statistiken zurück"""
    db = request.app.state.db
    
    all_images = db.get_all_images()
    
    if not all_images:
        return {
            "success": True,
            "stats": {
                "total_images": 0,
                "total_faces": 0,
                "total_persons": 0,
                "oldest_image": None,
                "newest_image": None
            }
        }
    
    total_faces = sum(img.get("face_count", 0) for img in all_images)
    total_persons = sum(img.get("person_count", 0) for img in all_images)
    
    # Sortiert nach Zeit
    sorted_images = sorted(all_images, key=lambda x: x.get("timestamp", ""))
    
    return {
        "success": True,
        "stats": {
            "total_images": len(all_images),
            "total_faces": total_faces,
            "total_persons": total_persons,
            "oldest_image": sorted_images[0].get("timestamp") if sorted_images else None,
            "newest_image": sorted_images[-1].get("timestamp") if sorted_images else None,
            "images_today": _count_today(all_images)
        }
    }


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def _format_time(timestamp: str) -> str:
    """Formatiert Timestamp für Anzeige"""
    if not timestamp:
        return "-"
    
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return timestamp[:16] if len(timestamp) > 16 else timestamp


def _count_today(images: list) -> int:
    """Zählt Bilder von heute"""
    today = datetime.now().strftime("%Y-%m-%d")

    count = 0
    for img in images:
        ts = img.get("timestamp", "")
        if ts.startswith(today):
            count += 1

    return count


def _is_time_in_range(timestamp: str, start_hour: int, start_minute: int, end_hour: int, end_minute: int) -> bool:
    """Prüft ob Timestamp innerhalb der Uhrzeit-Range liegt"""
    if not timestamp:
        return False

    try:
        # Parse timestamp
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Extrahiere Stunde und Minute
        hour = dt.hour
        minute = dt.minute

        # Konvertiere alles zu Minuten seit Mitternacht für einfacheren Vergleich
        current_minutes = hour * 60 + minute
        start_minutes = start_hour * 60 + start_minute
        end_minutes = end_hour * 60 + end_minute

        # Prüfe ob im Bereich
        return start_minutes <= current_minutes <= end_minutes

    except Exception as e:
        print(f"Fehler beim Parsen des Timestamps '{timestamp}': {e}")
        return False
