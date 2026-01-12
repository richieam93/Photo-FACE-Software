"""
Kamera-Handler - USB Webcam Steuerung
"""

import os
import sys
import time
import threading
import base64
from pathlib import Path
from typing import Optional, Tuple, Callable
from datetime import datetime
import io

# OpenCV
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("⚠️ OpenCV nicht installiert - Kamera deaktiviert")

# PIL
from PIL import Image


# ============================================================
# CAMERA HANDLER
# ============================================================

class CameraHandler:
    """Verwaltet USB-Webcam für Kundenfotos"""
    
    def __init__(self, config):
        """
        Args:
            config: Config-Instanz
        """
        self.config = config
        
        # Kamera-Einstellungen
        self.device_id = config.get("camera.device_id", 0)
        self.width = config.get("camera.width", 1280)
        self.height = config.get("camera.height", 720)
        self.flip_horizontal = config.get("camera.flip_horizontal", True)
        
        # Kamera-Instanz
        self._camera = None
        self._lock = threading.Lock()
        
        # Streaming
        self._streaming = False
        self._stream_thread = None
        self._frame_callback: Optional[Callable] = None
    
    # ========================================================
    # KAMERA ÖFFNEN / SCHLIESSEN
    # ========================================================
    
    def open(self) -> bool:
        """
        Öffnet die Kamera

        Returns:
            True bei Erfolg
        """
        if not OPENCV_AVAILABLE:
            print("❌ OpenCV nicht verfügbar")
            return False

        with self._lock:
            # Wenn bereits geöffnet, prüfen ob noch funktional
            if self._camera is not None:
                if self._camera.isOpened():
                    return True
                else:
                    # Kamera ist nicht mehr verfügbar, aufräumen
                    try:
                        self._camera.release()
                    except:
                        pass
                    self._camera = None

            try:
                # Kamera öffnen
                self._camera = cv2.VideoCapture(self.device_id, cv2.CAP_DSHOW)  # Windows DirectShow Backend

                if not self._camera.isOpened():
                    print(f"❌ Kamera {self.device_id} konnte nicht geöffnet werden")
                    self._camera = None
                    return False

                # Wartezeit für Initialisierung
                import time
                time.sleep(0.5)

                # Auflösung setzen
                self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

                # Buffer-Größe reduzieren für bessere Performance
                self._camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                # Tatsächliche Auflösung prüfen
                actual_width = int(self._camera.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_height = int(self._camera.get(cv2.CAP_PROP_FRAME_HEIGHT))

                # Test-Frame lesen um sicherzustellen dass Kamera funktioniert
                ret, test_frame = self._camera.read()
                if not ret or test_frame is None:
                    print(f"❌ Kamera {self.device_id} liefert keine Bilder")
                    try:
                        self._camera.release()
                    except:
                        pass
                    self._camera = None
                    return False

                print(f"📷 Kamera geöffnet: {actual_width}x{actual_height}")
                return True

            except Exception as e:
                print(f"❌ Fehler beim Öffnen der Kamera: {e}")
                if self._camera is not None:
                    try:
                        self._camera.release()
                    except:
                        pass
                    self._camera = None
                return False
    
    def close(self) -> None:
        """Schließt die Kamera"""
        with self._lock:
            self.stop_stream()
            
            if self._camera is not None:
                self._camera.release()
                self._camera = None
                print("📷 Kamera geschlossen")
    
    def is_open(self) -> bool:
        """Prüft ob Kamera geöffnet ist"""
        return self._camera is not None and self._camera.isOpened()
    
    # ========================================================
    # FOTO AUFNEHMEN
    # ========================================================
    
    def capture(self) -> Optional[bytes]:
        """
        Nimmt ein Foto auf
        
        Returns:
            Bild als JPEG-Bytes oder None
        """
        if not self.is_open():
            if not self.open():
                return None
        
        with self._lock:
            try:
                # Frame lesen
                ret, frame = self._camera.read()
                
                if not ret or frame is None:
                    print("❌ Konnte kein Bild aufnehmen")
                    return None
                
                # Horizontal spiegeln
                if self.flip_horizontal:
                    frame = cv2.flip(frame, 1)
                
                # BGR -> RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Zu PIL Image
                image = Image.fromarray(frame_rgb)
                
                # Als JPEG-Bytes
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=90)
                
                return buffer.getvalue()
                
            except Exception as e:
                print(f"❌ Aufnahmefehler: {e}")
                return None
    
    def capture_to_file(self, output_path: str) -> bool:
        """
        Nimmt Foto auf und speichert es
        
        Args:
            output_path: Zielpfad
            
        Returns:
            True bei Erfolg
        """
        image_bytes = self.capture()
        
        if image_bytes is None:
            return False
        
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'wb') as f:
                f.write(image_bytes)
            
            print(f"📷 Foto gespeichert: {path.name}")
            return True
            
        except Exception as e:
            print(f"❌ Speicherfehler: {e}")
            return False
    
    def capture_base64(self) -> Optional[str]:
        """
        Nimmt Foto auf und gibt Base64-String zurück
        
        Returns:
            Base64-kodiertes JPEG oder None
        """
        image_bytes = self.capture()
        
        if image_bytes is None:
            return None
        
        return base64.b64encode(image_bytes).decode('utf-8')
    
    # ========================================================
    # VIDEO STREAM
    # ========================================================
    
    def start_stream(self, callback: Callable[[bytes], None] = None) -> bool:
        """
        Startet Video-Stream
        
        Args:
            callback: Funktion die bei jedem Frame aufgerufen wird
            
        Returns:
            True bei Erfolg
        """
        if self._streaming:
            return True
        
        if not self.is_open():
            if not self.open():
                return False
        
        self._frame_callback = callback
        self._streaming = True
        
        # Stream-Thread starten
        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()
        
        print("🎥 Video-Stream gestartet")
        return True
    
    def stop_stream(self) -> None:
        """Stoppt Video-Stream"""
        self._streaming = False
        
        if self._stream_thread is not None:
            self._stream_thread.join(timeout=2)
            self._stream_thread = None
        
        print("🎥 Video-Stream gestoppt")
    
    def _stream_loop(self) -> None:
        """Interne Stream-Schleife"""
        while self._streaming and self.is_open():
            try:
                frame_bytes = self.capture()
                
                if frame_bytes and self._frame_callback:
                    self._frame_callback(frame_bytes)
                
                # ~30 FPS
                time.sleep(0.033)
                
            except Exception as e:
                print(f"❌ Stream-Fehler: {e}")
                time.sleep(0.1)
    
    def generate_frames(self):
        """
        Generator für MJPEG-Stream (Flask/FastAPI kompatibel)
        
        Yields:
            MJPEG Frame-Bytes
        """
        if not self.is_open():
            if not self.open():
                return
        
        while True:
            frame_bytes = self.capture()
            
            if frame_bytes:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + 
                    frame_bytes + 
                    b'\r\n'
                )
            
            time.sleep(0.033)
    
    # ========================================================
    # EINSTELLUNGEN
    # ========================================================
    
    def update_settings(
        self,
        device_id: int = None,
        width: int = None,
        height: int = None,
        flip_horizontal: bool = None
    ) -> None:
        """Aktualisiert Kamera-Einstellungen"""
        restart_needed = False
        
        if device_id is not None and device_id != self.device_id:
            self.device_id = device_id
            restart_needed = True
        
        if width is not None:
            self.width = width
            restart_needed = True
        
        if height is not None:
            self.height = height
            restart_needed = True
        
        if flip_horizontal is not None:
            self.flip_horizontal = flip_horizontal
        
        # Kamera neu starten wenn nötig
        if restart_needed and self.is_open():
            self.close()
            self.open()
    
    def get_info(self) -> dict:
        """Gibt Kamera-Informationen zurück"""
        info = {
            "available": OPENCV_AVAILABLE,
            "open": self.is_open(),
            "streaming": self._streaming,
            "device_id": self.device_id,
            "settings": {
                "width": self.width,
                "height": self.height,
                "flip_horizontal": self.flip_horizontal
            }
        }
        
        if self.is_open():
            info["actual_width"] = int(self._camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            info["actual_height"] = int(self._camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            info["fps"] = int(self._camera.get(cv2.CAP_PROP_FPS))
        
        return info
    
    @staticmethod
    def list_cameras(max_check: int = 5) -> list:
        """
        Listet verfügbare Kameras auf
        
        Args:
            max_check: Maximale Anzahl zu prüfender IDs
            
        Returns:
            Liste der verfügbaren Kamera-IDs
        """
        if not OPENCV_AVAILABLE:
            return []
        
        available = []
        
        for i in range(max_check):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()
        
        return available
