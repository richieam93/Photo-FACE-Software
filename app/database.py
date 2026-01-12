"""
JSON Datenbank für Bildanalyse-Daten
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import threading
import hashlib

from .config import Config


# ============================================================
# DATABASE KLASSE
# ============================================================

class Database:
    """JSON-basierte Datenbank für Bildanalyse"""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.root_dir / "data" / "images.json"
        self.settings_path = config.root_dir / "data" / "settings.json"
        self.print_jobs_path = config.root_dir / "data" / "print_jobs.json"
        
        # Daten
        self.images: Dict[str, dict] = {}
        self.settings: Dict[str, dict] = {}
        self.print_jobs: List[dict] = []
        
        # Thread-Safety
        self._lock = threading.Lock()
    
    # ========================================================
    # LADEN / SPEICHERN
    # ========================================================
    
    def load(self) -> None:
        """Lädt alle Datenbanken"""
        self._load_images()
        self._load_settings()
        self._load_print_jobs()
    
    def save(self) -> None:
        """Speichert alle Datenbanken"""
        self._save_images()
        self._save_settings()
        self._save_print_jobs()
    
    def _load_images(self) -> None:
        """Lädt Bilddatenbank"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8-sig') as f:
                    self.images = json.load(f)
            except Exception as e:
                print(f"⚠️ Fehler beim Laden der Bilddatenbank: {e}")
                self.images = {}
    
    def _save_images(self) -> None:
        """Speichert Bilddatenbank"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.images, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Fehler beim Speichern der Bilddatenbank: {e}")
    
    def _load_settings(self) -> None:
        """Lädt Einstellungen"""
        if self.settings_path.exists():
            try:
                with open(self.settings_path, 'r', encoding='utf-8-sig') as f:
                    self.settings = json.load(f)
            except Exception as e:
                print(f"⚠️ Fehler beim Laden der Settings: {e}")
                self.settings = {}
    
    def _save_settings(self) -> None:
        """Speichert Einstellungen"""
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Fehler beim Speichern der Settings: {e}")
    
    def _load_print_jobs(self) -> None:
        """Lädt Druckaufträge"""
        if self.print_jobs_path.exists():
            try:
                with open(self.print_jobs_path, 'r', encoding='utf-8-sig') as f:
                    self.print_jobs = json.load(f)
            except Exception as e:
                print(f"⚠️ Fehler beim Laden der Druckaufträge: {e}")
                self.print_jobs = []
    
    def _save_print_jobs(self) -> None:
        """Speichert Druckaufträge"""
        try:
            self.print_jobs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.print_jobs_path, 'w', encoding='utf-8') as f:
                json.dump(self.print_jobs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Fehler beim Speichern der Druckaufträge: {e}")
    
    # ========================================================
    # BILDER
    # ========================================================
    
    def add_image(self, image_data: dict) -> str:
        """Fügt ein analysiertes Bild hinzu"""
        with self._lock:
            image_id = self._generate_id(image_data.get("filename", ""))
            
            self.images[image_id] = {
                "id": image_id,
                "filename": image_data.get("filename", ""),
                "original_path": image_data.get("original_path", ""),
                "processed_path": image_data.get("processed_path", ""),
                "output_path": image_data.get("output_path", ""),
                "timestamp": image_data.get("timestamp", datetime.now().isoformat()),
                
                # Analyse-Daten
                "faces": image_data.get("faces", []),
                "face_count": image_data.get("face_count", 0),
                "face_encodings": image_data.get("face_encodings", []),
                
                "persons": image_data.get("persons", []),
                "person_count": image_data.get("person_count", 0),
                
                "clothing_colors": image_data.get("clothing_colors", []),
                
                # Meta
                "width": image_data.get("width", 0),
                "height": image_data.get("height", 0),
                "created_at": datetime.now().isoformat()
            }
            
            self._save_images()
            return image_id
    
    def get_image(self, image_id: str) -> Optional[dict]:
        """Holt ein Bild nach ID"""
        return self.images.get(image_id)
    
    def get_image_by_filename(self, filename: str) -> Optional[dict]:
        """Sucht Bild nach Dateiname"""
        for img in self.images.values():
            if img.get("filename") == filename:
                return img
        return None
    
    def get_all_images(self, limit: int = None, offset: int = 0) -> List[dict]:
        """Holt alle Bilder (sortiert nach Zeit)"""
        images = list(self.images.values())
        images.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        if limit:
            return images[offset:offset + limit]
        return images[offset:]
    
    def delete_image(self, image_id: str) -> bool:
        """Löscht ein Bild"""
        with self._lock:
            if image_id in self.images:
                del self.images[image_id]
                self._save_images()
                return True
            return False
    
    def clear_images(self) -> int:
        """Löscht alle Bilder"""
        with self._lock:
            count = len(self.images)
            self.images = {}
            self._save_images()
            return count
    
    def count_images(self) -> int:
        """Zählt alle Bilder"""
        return len(self.images)
    
    def search_images(self, query: str) -> List[dict]:
        """Sucht Bilder nach Name oder Zeit"""
        results = []
        query_lower = query.lower()
        
        for img in self.images.values():
            filename = img.get("filename", "").lower()
            timestamp = img.get("timestamp", "").lower()
            
            if query_lower in filename or query_lower in timestamp:
                results.append(img)
        
        return results
    
    # ========================================================
    # SETTINGS (pro Station/Typ)
    # ========================================================
    
    def get_settings(self, station: str, settings_type: str) -> dict:
        """Holt Einstellungen für Station und Typ"""
        key = f"{station}_{settings_type}"
        return self.settings.get(key, {})
    
    def save_settings(self, station: str, settings_type: str, data: dict) -> bool:
        """Speichert Einstellungen"""
        with self._lock:
            key = f"{station}_{settings_type}"
            self.settings[key] = {
                **data,
                "updated_at": datetime.now().isoformat()
            }
            self._save_settings()
            return True
    
    def delete_settings(self, station: str, settings_type: str) -> bool:
        """Löscht Einstellungen"""
        with self._lock:
            key = f"{station}_{settings_type}"
            if key in self.settings:
                del self.settings[key]
                self._save_settings()
                return True
            return False
    
    # ========================================================
    # DRUCKAUFTRÄGE
    # ========================================================
    
    def add_print_job(self, job: dict) -> str:
        """Fügt Druckauftrag hinzu"""
        with self._lock:
            job_id = f"PJ_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.print_jobs)}"
            
            self.print_jobs.append({
                "id": job_id,
                "image_id": job.get("image_id"),
                "image_filename": job.get("image_filename"),
                "printer_type": job.get("printer_type", "small"),
                "printer_name": job.get("printer_name"),
                "price": job.get("price", 0),
                "status": "pending",
                "created_at": datetime.now().isoformat()
            })
            
            self._save_print_jobs()
            return job_id
    
    def get_print_jobs(self, limit: int = 50) -> List[dict]:
        """Holt letzte Druckaufträge"""
        return self.print_jobs[-limit:][::-1]
    
    def get_print_stats(self) -> dict:
        """Statistiken zu Druckaufträgen"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        total = len(self.print_jobs)
        today_jobs = [j for j in self.print_jobs if j.get("created_at", "").startswith(today)]
        today_revenue = sum(j.get("price", 0) for j in today_jobs)
        
        # Beliebtester Drucker
        printer_counts = {}
        for job in self.print_jobs:
            pt = job.get("printer_type", "unknown")
            printer_counts[pt] = printer_counts.get(pt, 0) + 1
        
        popular = max(printer_counts, key=printer_counts.get) if printer_counts else "-"
        
        return {
            "total_jobs": total,
            "today_jobs": len(today_jobs),
            "today_revenue": today_revenue,
            "popular_printer": popular
        }
    
    # ========================================================
    # STATISTIKEN
    # ========================================================
    
    def get_statistics(self) -> dict:
        """Allgemeine Statistiken"""
        total_faces = sum(img.get("face_count", 0) for img in self.images.values())
        total_persons = sum(img.get("person_count", 0) for img in self.images.values())
        
        return {
            "total_images": len(self.images),
            "total_faces": total_faces,
            "total_persons": total_persons,
            "settings_count": len(self.settings),
            "print_jobs": len(self.print_jobs)
        }
    
    # ========================================================
    # HILFSFUNKTIONEN
    # ========================================================
    
    def _generate_id(self, filename: str) -> str:
        """Generiert eindeutige ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        hash_input = f"{filename}_{timestamp}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"IMG_{timestamp}_{hash_value}"
