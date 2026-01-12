"""
Bildverarbeitung - Pipeline, Zuschnitt, File-Watcher
"""

import os
import sys
import time
import shutil
import threading
from pathlib import Path
from typing import Optional, Tuple, List, Callable
from datetime import datetime
from PIL import Image
import io

# Watchdog für Ordnerüberwachung
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("⚠️ Watchdog nicht installiert - Ordnerüberwachung deaktiviert")


# ============================================================
# IMAGE PROCESSOR - Hauptverarbeitung
# ============================================================

class ImageProcessor:
    """Verarbeitet Bilder durch die komplette Pipeline"""
    
    # Unterstützte Bildformate
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
    
    def __init__(self, config, database, analyzer=None):
        """
        Args:
            config: Config-Instanz
            database: Database-Instanz
            analyzer: ImageAnalyzer-Instanz (optional, wird lazy geladen)
        """
        self.config = config
        self.db = database
        self._analyzer = analyzer
        
        # Pfade
        self.input_path = config.get_path("input")
        self.temp_path = config.get_path("temp")
        self.processed_path = config.get_path("processed")
        self.output_path = config.get_path("output")
        
        # Statistiken
        self.stats = {
            "processed": 0,
            "errors": 0,
            "last_processed": None
        }
    
    @property
    def analyzer(self):
        """Lazy-Loading des Analyzers"""
        if self._analyzer is None:
            from .analyzer import ImageAnalyzer
            self._analyzer = ImageAnalyzer(self.config)
        return self._analyzer
    
    # ========================================================
    # HAUPTPIPELINE
    # ========================================================
    
    def process_image(self, image_path: str, station: str = "default") -> Optional[dict]:
        """
        Verarbeitet ein einzelnes Bild durch die komplette Pipeline
        
        Pipeline:
        1. Bild laden
        2. Zuschnitt anwenden (falls konfiguriert)
        3. Temporär speichern
        4. Analysieren (Face, YOLO, Clothing)
        5. Annotiertes Bild speichern (mit Markierungen)
        6. Sauberes Bild speichern (ohne Markierungen)
        7. In Datenbank speichern
        
        Args:
            image_path: Pfad zum Eingabebild
            station: Station-ID für Einstellungen
            
        Returns:
            dict mit Analyse-Ergebnissen oder None bei Fehler
        """
        try:
            image_path = Path(image_path)
            
            # Prüfen ob gültiges Bild
            if not self._is_valid_image(image_path):
                print(f"⚠️ Ungültiges Bild: {image_path}")
                return None
            
            print(f"\n{'='*50}")
            print(f"📷 Verarbeite: {image_path.name}")
            print(f"{'='*50}")
            
            # 1. Bild laden
            print("1️⃣ Bild laden...")
            image = Image.open(image_path)
            original_size = image.size
            print(f"   Größe: {original_size[0]}x{original_size[1]}")
            
            # 2. Zuschnitt anwenden
            print("2️⃣ Zuschnitt prüfen...")
            image = self._apply_crop(image, station)
            
            # 3. Temporär speichern
            print("3️⃣ Temporär speichern...")
            temp_filename = f"temp_{datetime.now().strftime('%Y%m%d%H%M%S')}_{image_path.name}"
            temp_file = self.temp_path / temp_filename
            
            quality = self.config.get("processing.jpeg_quality", 85)
            image.save(temp_file, "JPEG", quality=quality)
            print(f"   Gespeichert: {temp_file.name}")
            
            # 4. Analysieren
            print("4️⃣ Bild analysieren...")
            analysis = self.analyzer.analyze_image(str(temp_file), station)
            
            if analysis:
                print(f"   ✅ Gesichter: {analysis.get('face_count', 0)}")
                print(f"   ✅ Personen: {analysis.get('person_count', 0)}")
                print(f"   ✅ Farben: {len(analysis.get('clothing_colors', []))}")
            
            # 5. Annotiertes Bild speichern (mit Markierungen)
            print("5️⃣ Annotiertes Bild erstellen...")
            annotated_filename = f"annotated_{image_path.name}"
            annotated_file = self.processed_path / annotated_filename
            
            annotated_image = self.analyzer.draw_annotations(
                str(temp_file),
                analysis
            )
            if annotated_image:
                annotated_image.save(annotated_file, "JPEG", quality=quality)
                print(f"   Gespeichert: {annotated_file.name}")
            
            # 6. Sauberes Bild speichern (ohne Markierungen)
            print("6️⃣ Output-Bild speichern...")
            output_filename = image_path.name
            output_file = self.output_path / output_filename
            image.save(output_file, "JPEG", quality=quality)
            print(f"   Gespeichert: {output_file.name}")
            
            # 7. In Datenbank speichern
            print("7️⃣ In Datenbank speichern...")
            
            # Timestamp aus Datei extrahieren
            try:
                file_time = datetime.fromtimestamp(image_path.stat().st_mtime)
                timestamp = file_time.isoformat()
            except:
                timestamp = datetime.now().isoformat()
            
            image_data = {
                "filename": image_path.name,
                "original_path": str(image_path),
                "processed_path": str(annotated_file) if annotated_image else "",
                "output_path": str(output_file),
                "timestamp": timestamp,
                "width": image.size[0],
                "height": image.size[1],
                
                # Analyse-Daten
                "faces": analysis.get("faces", []) if analysis else [],
                "face_count": analysis.get("face_count", 0) if analysis else 0,
                "face_encodings": analysis.get("face_encodings", []) if analysis else [],
                
                "persons": analysis.get("persons", []) if analysis else [],
                "person_count": analysis.get("person_count", 0) if analysis else 0,
                
                "clothing_colors": analysis.get("clothing_colors", []) if analysis else []
            }
            
            image_id = self.db.add_image(image_data)
            print(f"   ✅ ID: {image_id}")
            
            # Temp-Datei löschen
            if temp_file.exists():
                temp_file.unlink()
            
            # Original löschen falls konfiguriert
            if self.config.get("processing.delete_original", False):
                image_path.unlink()
                print(f"   🗑️ Original gelöscht")
            
            # Statistiken
            self.stats["processed"] += 1
            self.stats["last_processed"] = datetime.now().isoformat()
            
            print(f"\n✅ Verarbeitung abgeschlossen!")
            print(f"{'='*50}\n")
            
            return {
                "success": True,
                "image_id": image_id,
                "analysis": analysis,
                **image_data
            }
            
        except Exception as e:
            print(f"❌ Fehler bei Verarbeitung: {e}")
            import traceback
            traceback.print_exc()
            self.stats["errors"] += 1
            return None
    
    def process_all_pending(self, station: str = "default") -> dict:
        """
        Verarbeitet alle Bilder im Input-Ordner
        
        Returns:
            dict mit Statistiken
        """
        results = {
            "processed": 0,
            "errors": 0,
            "skipped": 0,
            "files": []
        }
        
        if not self.input_path.exists():
            return results
        
        # Alle Bilder im Input-Ordner finden
        for file_path in self.input_path.iterdir():
            if not self._is_valid_image(file_path):
                continue
            
            # Prüfen ob bereits verarbeitet
            existing = self.db.get_image_by_filename(file_path.name)
            if existing:
                results["skipped"] += 1
                continue
            
            # Verarbeiten
            result = self.process_image(str(file_path), station)
            
            if result and result.get("success"):
                results["processed"] += 1
                results["files"].append(file_path.name)
            else:
                results["errors"] += 1
        
        return results
    
    # ========================================================
    # ZUSCHNITT
    # ========================================================
    
    def _apply_crop(self, image: Image.Image, station: str) -> Image.Image:
        """
        Wendet Zuschnitt-Einstellungen an
        
        Args:
            image: PIL Image
            station: Station-ID
            
        Returns:
            Zugeschnittenes Image
        """
        # Einstellungen laden
        crop_settings = self.db.get_settings(station, "crop")
        
        if not crop_settings or not crop_settings.get("enabled", False):
            print("   Kein Zuschnitt konfiguriert")
            return image
        
        # Prozentuale Werte
        x_percent = crop_settings.get("xPercent", crop_settings.get("x_percent", 0))
        y_percent = crop_settings.get("yPercent", crop_settings.get("y_percent", 0))
        w_percent = crop_settings.get("widthPercent", crop_settings.get("width_percent", 100))
        h_percent = crop_settings.get("heightPercent", crop_settings.get("height_percent", 100))
        
        # Absolute Pixel berechnen
        width, height = image.size
        
        left = int((x_percent / 100) * width)
        top = int((y_percent / 100) * height)
        crop_width = int((w_percent / 100) * width)
        crop_height = int((h_percent / 100) * height)
        
        right = left + crop_width
        bottom = top + crop_height
        
        # Grenzen prüfen
        left = max(0, left)
        top = max(0, top)
        right = min(width, right)
        bottom = min(height, bottom)
        
        # Zuschneiden
        cropped = image.crop((left, top, right, bottom))
        
        print(f"   Zugeschnitten: {left},{top} -> {right},{bottom}")
        print(f"   Neue Größe: {cropped.size[0]}x{cropped.size[1]}")
        
        return cropped
    
    def crop_image_data(self, image_data: bytes, station: str) -> bytes:
        """
        Schneidet Bild-Bytes zu
        
        Args:
            image_data: Bild als Bytes
            station: Station-ID
            
        Returns:
            Zugeschnittene Bild-Bytes
        """
        image = Image.open(io.BytesIO(image_data))
        cropped = self._apply_crop(image, station)
        
        output = io.BytesIO()
        quality = self.config.get("processing.jpeg_quality", 85)
        cropped.save(output, "JPEG", quality=quality)
        
        return output.getvalue()
    
    # ========================================================
    # HILFSFUNKTIONEN
    # ========================================================
    
    def _is_valid_image(self, path: Path) -> bool:
        """Prüft ob Datei ein gültiges Bild ist"""
        if not path.is_file():
            return False
        
        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            return False
        
        # Prüfen ob Datei lesbar
        try:
            with Image.open(path) as img:
                img.verify()
            return True
        except:
            return False
    
    def get_stats(self) -> dict:
        """Gibt Verarbeitungsstatistiken zurück"""
        return {
            **self.stats,
            "input_count": self._count_files(self.input_path),
            "temp_count": self._count_files(self.temp_path),
            "processed_count": self._count_files(self.processed_path),
            "output_count": self._count_files(self.output_path)
        }
    
    def _count_files(self, path: Path) -> int:
        """Zählt Bilddateien in Ordner"""
        if not path.exists():
            return 0
        
        count = 0
        for f in path.iterdir():
            if f.suffix.lower() in self.SUPPORTED_FORMATS:
                count += 1
        return count
    
    def cleanup_temp(self) -> int:
        """Löscht temporäre Dateien"""
        deleted = 0
        
        if self.temp_path.exists():
            for f in self.temp_path.iterdir():
                try:
                    f.unlink()
                    deleted += 1
                except:
                    pass
        
        return deleted


# ============================================================
# FILE WATCHER - Ordnerüberwachung
# ============================================================

class FileWatcher:
    """Überwacht Ordner auf neue Bilder"""
    
    def __init__(self, config, processor: ImageProcessor, station: str = "default"):
        """
        Args:
            config: Config-Instanz
            processor: ImageProcessor-Instanz
            station: Standard-Station
        """
        self.config = config
        self.processor = processor
        self.station = station
        
        self.observer = None
        self.running = False
        self._lock = threading.Lock()
        
        # Callback für neue Bilder
        self.on_new_image: Optional[Callable] = None
        
        # Queue für Verarbeitung
        self._queue: List[str] = []
        self._processing = False
    
    def start(self) -> bool:
        """Startet die Ordnerüberwachung"""
        if not WATCHDOG_AVAILABLE:
            print("❌ Watchdog nicht verfügbar")
            return False
        
        if self.running:
            print("⚠️ Watcher läuft bereits")
            return False
        
        watch_path = self.processor.input_path
        
        if not watch_path.exists():
            watch_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Event Handler erstellen
            handler = _ImageEventHandler(self)
            
            # Observer erstellen und starten
            self.observer = Observer()
            self.observer.schedule(handler, str(watch_path), recursive=False)
            self.observer.start()
            
            self.running = True
            print(f"👁️ Watcher gestartet: {watch_path}")
            
            # Processing Thread starten
            self._start_processing_thread()
            
            return True
            
        except Exception as e:
            print(f"❌ Fehler beim Starten des Watchers: {e}")
            return False
    
    def stop(self) -> bool:
        """Stoppt die Ordnerüberwachung"""
        if not self.running:
            return False
        
        try:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=5)
                self.observer = None
            
            self.running = False
            print("🛑 Watcher gestoppt")
            return True
            
        except Exception as e:
            print(f"❌ Fehler beim Stoppen des Watchers: {e}")
            return False
    
    def add_to_queue(self, file_path: str) -> None:
        """Fügt Datei zur Verarbeitungsqueue hinzu"""
        with self._lock:
            if file_path not in self._queue:
                self._queue.append(file_path)
                print(f"📥 Zur Queue hinzugefügt: {Path(file_path).name}")
    
    def _start_processing_thread(self) -> None:
        """Startet Thread für Queue-Verarbeitung"""
        def process_queue():
            while self.running:
                if self._queue and not self._processing:
                    with self._lock:
                        if self._queue:
                            file_path = self._queue.pop(0)
                            self._processing = True
                    
                    try:
                        # Kurz warten bis Datei vollständig geschrieben
                        time.sleep(1)
                        
                        # Verarbeiten
                        result = self.processor.process_image(file_path, self.station)
                        
                        # Callback aufrufen
                        if result and self.on_new_image:
                            self.on_new_image(result)
                            
                    except Exception as e:
                        print(f"❌ Verarbeitungsfehler: {e}")
                    finally:
                        self._processing = False
                
                time.sleep(0.5)
        
        thread = threading.Thread(target=process_queue, daemon=True)
        thread.start()
    
    def is_running(self) -> bool:
        """Prüft ob Watcher läuft"""
        return self.running
    
    def get_queue_size(self) -> int:
        """Gibt Queue-Größe zurück"""
        return len(self._queue)


class _ImageEventHandler(FileSystemEventHandler):
    """Handler für Dateisystem-Events"""
    
    def __init__(self, watcher: FileWatcher):
        super().__init__()
        self.watcher = watcher
        self.processor = watcher.processor
    
    def on_created(self, event):
        """Wird aufgerufen wenn neue Datei erstellt wird"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Prüfen ob gültiges Bild
        if file_path.suffix.lower() not in ImageProcessor.SUPPORTED_FORMATS:
            return
        
        print(f"🆕 Neue Datei erkannt: {file_path.name}")
        
        # Auto-Processing aktiviert?
        if self.watcher.config.get("processing.auto_process", True):
            self.watcher.add_to_queue(str(file_path))
        else:
            print("   ℹ️ Auto-Verarbeitung deaktiviert")