"""
Konfigurationsmanagement - Alle Einstellungen zentral
"""

import json
import os
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

# ============================================================
# STANDARD-KONFIGURATION
# ============================================================

DEFAULT_CONFIG = {
    # Server
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
        "debug": True
    },
    
    # Pfade (anpassbar)
    "paths": {
        "input": "photos/input",
        "temp": "photos/temp",
        "processed": "photos/processed",
        "output": "photos/output",
        "models": "models",
        "data": "data",
        "logs": "data/logs"
    },
    
    # Kamera
    "camera": {
        "device_id": 0,
        "width": 1280,
        "height": 720,
        "flip_horizontal": True
    },
    
    # Verarbeitung
    "processing": {
        "auto_process": True,
        "delete_original": False,
        "jpeg_quality": 85,
        "watch_interval": 2
    },
    
    # Face Recognition
    "face": {
        "model": "hog",
        "upsample": 1,
        "tolerance": 0.6,
        "min_face_size": 20
    },
    
    # YOLO Person Detection
    "person": {
        "enabled": True,
        "method": "auto",
        "model_size": "n",
        "confidence": 0.5,
        "min_width": 50,
        "min_height": 100
    },
    
    # Clothing Analysis
    "clothing": {
        "enabled": True,
        "body_ratio": 2.5,
        "body_width_ratio": 1.5,
        "num_colors": 3,
        "analyze_brightness": True,
        "analyze_patterns": True
    },
    
    # Crop/Zuschnitt (pro Station)
    "crop": {
        "enabled": False,
        "x_percent": 0,
        "y_percent": 0,
        "width_percent": 100,
        "height_percent": 100
    },
    
    # Suche
    "search": {
        "face_threshold": 0.6,
        "color_threshold": 50,
        "max_results": 20
    },
    
    # Drucker
    "printers": {
        "enabled": True,
        "small": {
            "name": "\\\\DESKTOP-GNK1K6H\\Hanspeter",
            "price": 5.00,
            "enabled": True
        },
        "big": {
            "name": "\\\\DESKTOP-GNK1K6H\\Hanspeter",
            "price": 8.00,
            "enabled": True
        }
    },
    
    # Karussell
    "carousel": {
        "auto_play": True,
        "interval": 5000,
        "show_faces": True,
        "show_persons": True,
        "show_colors": True
    },
    
    # App
    "app": {
        "name": "Photo Software",
        "language": "de"
    }
}


# ============================================================
# CONFIG KLASSE
# ============================================================

class Config:
    """Zentrale Konfigurationsverwaltung"""
    
    def __init__(self, config_path: str = None):
        self.root_dir = Path(__file__).parent.parent
        self.config_path = Path(config_path) if config_path else self.root_dir / "data" / "config.json"
        self.data = {}
        
    def load(self) -> dict:
        """Lädt Konfiguration aus JSON"""
        # Defaults laden
        self.data = self._deep_copy(DEFAULT_CONFIG)
        
        # Falls Datei existiert, überschreiben
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    self._deep_update(self.data, saved)
            except Exception as e:
                print(f"⚠️ Fehler beim Laden der Config: {e}")
        else:
            # Erstmalig speichern
            self.save()
        
        return self.data
    
    def save(self) -> bool:
        """Speichert Konfiguration"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ Fehler beim Speichern der Config: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Holt einen Wert (unterstützt dot-notation: 'server.port')"""
        keys = key.split('.')
        value = self.data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Setzt einen Wert (unterstützt dot-notation)"""
        keys = key.split('.')
        data = self.data
        
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        
        data[keys[-1]] = value
    
    def get_path(self, key: str) -> Path:
        """Gibt einen Pfad als absoluten Path zurück"""
        rel_path = self.get(f"paths.{key}", "")
        return self.root_dir / rel_path
    
    def ensure_directories(self) -> None:
        """Erstellt alle benötigten Ordner"""
        for key in ["input", "temp", "processed", "output", "models", "data", "logs"]:
            path = self.get_path(key)
            path.mkdir(parents=True, exist_ok=True)
    
    def _deep_copy(self, obj: dict) -> dict:
        """Tiefe Kopie eines Dicts"""
        return json.loads(json.dumps(obj))
    
    def _deep_update(self, base: dict, update: dict) -> dict:
        """Aktualisiert Dict rekursiv"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
        return base