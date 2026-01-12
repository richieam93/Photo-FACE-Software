"""
Bildanalyse - Gesichtserkennung, YOLO, Kleiderfarben
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import colorsys

# Face Recognition
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    print("⚠️ face_recognition nicht installiert")

# OpenCV
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("⚠️ OpenCV nicht installiert")

# YOLO
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("⚠️ ultralytics (YOLO) nicht installiert")

# Sklearn für Farbclustering
try:
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️ sklearn nicht installiert - Farbanalyse eingeschränkt")


# ============================================================
# DATENKLASSEN
# ============================================================

@dataclass
class FaceData:
    """Daten eines erkannten Gesichts"""
    location: Tuple[int, int, int, int]  # top, right, bottom, left
    encoding: Optional[List[float]] = None
    clothing_colors: Optional[List[dict]] = None


@dataclass
class PersonData:
    """Daten einer erkannten Person"""
    bbox: Tuple[int, int, int, int]  # x, y, width, height
    confidence: float = 0.0
    clothing_colors: Optional[List[dict]] = None


# ============================================================
# IMAGE ANALYZER
# ============================================================

class ImageAnalyzer:
    """Analysiert Bilder: Gesichter, Personen, Kleiderfarben"""
    
    # Farbnamen-Mapping
    COLOR_NAMES = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "orange": (255, 165, 0),
        "purple": (128, 0, 128),
        "pink": (255, 192, 203),
        "brown": (139, 69, 19),
        "black": (0, 0, 0),
        "white": (255, 255, 255),
        "gray": (128, 128, 128),
        "cyan": (0, 255, 255),
        "magenta": (255, 0, 255),
        "navy": (0, 0, 128),
        "teal": (0, 128, 128),
        "olive": (128, 128, 0),
        "maroon": (128, 0, 0),
        "beige": (245, 245, 220)
    }
    
    def __init__(self, config):
        """
        Args:
            config: Config-Instanz
        """
        self.config = config
        
        # YOLO Model (lazy loading)
        self._yolo_model = None
        
        # Module-Status
        self.modules = {
            "face_recognition": FACE_RECOGNITION_AVAILABLE,
            "opencv": OPENCV_AVAILABLE,
            "yolo": YOLO_AVAILABLE,
            "sklearn": SKLEARN_AVAILABLE
        }
    
    # ========================================================
    # HAUPT-ANALYSE
    # ========================================================
    
    def analyze_image(self, image_path: str, station: str = "default") -> Optional[dict]:
        """
        Führt komplette Bildanalyse durch
        
        Args:
            image_path: Pfad zum Bild
            station: Station-ID für Einstellungen
            
        Returns:
            dict mit allen Analyse-Ergebnissen
        """
        try:
            # Bild laden
            image = face_recognition.load_image_file(image_path) if FACE_RECOGNITION_AVAILABLE else None
            pil_image = Image.open(image_path)
            
            result = {
                "faces": [],
                "face_count": 0,
                "face_encodings": [],
                "persons": [],
                "person_count": 0,
                "clothing_colors": [],
                "image_size": pil_image.size
            }
            
            # 1. Gesichtserkennung
            if FACE_RECOGNITION_AVAILABLE and image is not None:
                face_result = self._analyze_faces(image, station)
                result["faces"] = face_result["faces"]
                result["face_count"] = face_result["count"]
                result["face_encodings"] = face_result["encodings"]
            
            # 2. Personenerkennung (YOLO)
            person_settings = self.config.get("person", {})
            if person_settings.get("enabled", True):
                person_result = self._detect_persons(image_path, station)
                result["persons"] = person_result["persons"]
                result["person_count"] = person_result["count"]
            
            # 3. Kleiderfarben-Analyse
            clothing_settings = self.config.get("clothing", {})
            if clothing_settings.get("enabled", True):
                colors = self._analyze_clothing_colors(
                    pil_image,
                    result["faces"],
                    result["persons"],
                    station
                )
                result["clothing_colors"] = colors
            
            return result
            
        except Exception as e:
            print(f"❌ Analysefehler: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # ========================================================
    # GESICHTSERKENNUNG
    # ========================================================
    
    def _analyze_faces(self, image: np.ndarray, station: str) -> dict:
        """
        Erkennt Gesichter im Bild
        
        Args:
            image: Bild als numpy array (RGB)
            station: Station-ID
            
        Returns:
            dict mit faces, count, encodings
        """
        # Einstellungen laden
        face_config = self.config.get("face", {})
        model = face_config.get("model", "hog")
        upsample = face_config.get("upsample", 1)
        min_size = face_config.get("min_face_size", 20)
        
        # Gesichter finden
        face_locations = face_recognition.face_locations(
            image,
            number_of_times_to_upsample=upsample,
            model=model
        )
        
        # Zu kleine Gesichter filtern
        filtered_locations = []
        for loc in face_locations:
            top, right, bottom, left = loc
            width = right - left
            height = bottom - top
            
            if width >= min_size and height >= min_size:
                filtered_locations.append(loc)
        
        # Encodings berechnen
        face_encodings = face_recognition.face_encodings(image, filtered_locations)
        
        # Ergebnisse formatieren
        faces = []
        encodings_list = []
        
        for i, loc in enumerate(filtered_locations):
            top, right, bottom, left = loc
            
            face_data = {
                "location": {
                    "top": int(top),
                    "right": int(right),
                    "bottom": int(bottom),
                    "left": int(left)
                },
                "width": int(right - left),
                "height": int(bottom - top),
                "center": {
                    "x": int((left + right) / 2),
                    "y": int((top + bottom) / 2)
                }
            }
            faces.append(face_data)
            
            # Encoding als Liste speichern
            if i < len(face_encodings):
                encodings_list.append(face_encodings[i].tolist())
        
        print(f"   👤 Gesichter gefunden: {len(faces)}")
        
        return {
            "faces": faces,
            "count": len(faces),
            "encodings": encodings_list
        }
    
    # ========================================================
    # PERSONENERKENNUNG (YOLO)
    # ========================================================
    
    def _detect_persons(self, image_path: str, station: str) -> dict:
        """
        Erkennt Personen mit YOLO
        
        Args:
            image_path: Pfad zum Bild
            station: Station-ID
            
        Returns:
            dict mit persons, count
        """
        person_config = self.config.get("person", {})
        method = person_config.get("method", "auto")
        
        # Methode wählen
        if method == "auto":
            if YOLO_AVAILABLE:
                return self._detect_persons_yolo(image_path, person_config)
            elif OPENCV_AVAILABLE:
                return self._detect_persons_hog(image_path, person_config)
        elif method == "yolo" and YOLO_AVAILABLE:
            return self._detect_persons_yolo(image_path, person_config)
        elif method == "hog" and OPENCV_AVAILABLE:
            return self._detect_persons_hog(image_path, person_config)
        
        print("   ⚠️ Keine Personenerkennung verfügbar")
        return {"persons": [], "count": 0}
    
    def _detect_persons_yolo(self, image_path: str, config: dict) -> dict:
        """YOLO-basierte Personenerkennung"""
        try:
            # Model laden (lazy)
            if self._yolo_model is None:
                model_size = config.get("model_size", "n")
                model_path = self.config.get_path("models") / f"yolov8{model_size}.pt"
                
                if not model_path.exists():
                    # Download falls nicht vorhanden
                    print(f"   📥 Lade YOLO Model: yolov8{model_size}.pt")
                    self._yolo_model = YOLO(f"yolov8{model_size}.pt")
                else:
                    self._yolo_model = YOLO(str(model_path))
            
            # Inference
            confidence = config.get("confidence", 0.5)
            results = self._yolo_model(image_path, conf=confidence, verbose=False)
            
            persons = []
            min_width = config.get("min_width", 50)
            min_height = config.get("min_height", 100)
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Nur "person" Klasse (ID 0)
                    if int(box.cls[0]) == 0:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        width = x2 - x1
                        height = y2 - y1
                        
                        # Mindestgröße prüfen
                        if width >= min_width and height >= min_height:
                            persons.append({
                                "bbox": {
                                    "x": int(x1),
                                    "y": int(y1),
                                    "width": int(width),
                                    "height": int(height)
                                },
                                "confidence": float(box.conf[0]),
                                "method": "yolo"
                            })
            
            print(f"   🚶 Personen (YOLO): {len(persons)}")
            return {"persons": persons, "count": len(persons)}
            
        except Exception as e:
            print(f"   ❌ YOLO Fehler: {e}")
            return {"persons": [], "count": 0}
    
    def _detect_persons_hog(self, image_path: str, config: dict) -> dict:
        """HOG-basierte Personenerkennung (OpenCV)"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return {"persons": [], "count": 0}
            
            # HOG Detektor
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            
            # Parameter
            win_stride = tuple(config.get("win_stride", [8, 8]))
            padding = tuple(config.get("padding", [16, 16]))
            scale = config.get("scale", 1.05)
            
            # Erkennung
            boxes, weights = hog.detectMultiScale(
                image,
                winStride=win_stride,
                padding=padding,
                scale=scale
            )
            
            persons = []
            min_width = config.get("min_width", 50)
            min_height = config.get("min_height", 100)
            
            for i, (x, y, w, h) in enumerate(boxes):
                if w >= min_width and h >= min_height:
                    persons.append({
                        "bbox": {
                            "x": int(x),
                            "y": int(y),
                            "width": int(w),
                            "height": int(h)
                        },
                        "confidence": float(weights[i]) if i < len(weights) else 0.5,
                        "method": "hog"
                    })
            
            print(f"   🚶 Personen (HOG): {len(persons)}")
            return {"persons": persons, "count": len(persons)}
            
        except Exception as e:
            print(f"   ❌ HOG Fehler: {e}")
            return {"persons": [], "count": 0}
    
    # ========================================================
    # KLEIDERFARBEN-ANALYSE
    # ========================================================
    
    def _analyze_clothing_colors(
        self,
        image: Image.Image,
        faces: List[dict],
        persons: List[dict],
        station: str
    ) -> List[dict]:
        """
        Analysiert Kleiderfarben basierend auf erkannten Gesichtern/Personen
        
        Args:
            image: PIL Image
            faces: Liste der erkannten Gesichter
            persons: Liste der erkannten Personen
            station: Station-ID
            
        Returns:
            Liste der Farbanalysen pro Person
        """
        clothing_config = self.config.get("clothing", {})
        num_colors = clothing_config.get("num_colors", 3)
        body_ratio = clothing_config.get("body_ratio", 2.5)
        body_width_ratio = clothing_config.get("body_width_ratio", 1.5)
        
        all_colors = []
        
        # 1. Basierend auf Gesichtern
        for i, face in enumerate(faces):
            loc = face.get("location", {})
            
            # Körperbereich unter Gesicht berechnen
            face_width = loc.get("right", 0) - loc.get("left", 0)
            face_height = loc.get("bottom", 0) - loc.get("top", 0)
            
            body_top = loc.get("bottom", 0)
            body_left = loc.get("left", 0) - int(face_width * (body_width_ratio - 1) / 2)
            body_width = int(face_width * body_width_ratio)
            body_height = int(face_height * body_ratio)
            
            # Grenzen prüfen
            body_left = max(0, body_left)
            body_right = min(image.size[0], body_left + body_width)
            body_bottom = min(image.size[1], body_top + body_height)
            
            # Bereich ausschneiden
            body_region = image.crop((body_left, body_top, body_right, body_bottom))
            
            # Farben analysieren
            colors = self._extract_dominant_colors(body_region, num_colors)
            
            all_colors.append({
                "source": "face",
                "index": i,
                "colors": colors,
                "region": {
                    "x": body_left,
                    "y": body_top,
                    "width": body_right - body_left,
                    "height": body_bottom - body_top
                }
            })
        
        # 2. Basierend auf YOLO-Personen (falls keine Gesichter)
        if not faces and persons:
            for i, person in enumerate(persons):
                bbox = person.get("bbox", {})
                
                # Obere Hälfte der Person (Oberkörper)
                x = bbox.get("x", 0)
                y = bbox.get("y", 0)
                w = bbox.get("width", 0)
                h = bbox.get("height", 0)
                
                # Oberkörper-Region (mittlere 60%)
                body_top = y + int(h * 0.2)
                body_bottom = y + int(h * 0.6)
                body_left = x + int(w * 0.1)
                body_right = x + int(w * 0.9)
                
                body_region = image.crop((body_left, body_top, body_right, body_bottom))
                colors = self._extract_dominant_colors(body_region, num_colors)
                
                all_colors.append({
                    "source": "person",
                    "index": i,
                    "colors": colors,
                    "region": {
                        "x": body_left,
                        "y": body_top,
                        "width": body_right - body_left,
                        "height": body_bottom - body_top
                    }
                })
        
        print(f"   🎨 Farb-Regionen analysiert: {len(all_colors)}")
        return all_colors
    
    def _extract_dominant_colors(self, image: Image.Image, n_colors: int = 3) -> List[dict]:
        """
        Extrahiert dominante Farben aus Bildbereich
        
        Args:
            image: PIL Image (Ausschnitt)
            n_colors: Anzahl zu extrahierender Farben
            
        Returns:
            Liste der dominanten Farben mit Prozentangaben
        """
        if not SKLEARN_AVAILABLE:
            return self._extract_colors_simple(image, n_colors)
        
        try:
            # Bild verkleinern für Performance
            image = image.resize((100, 100))
            
            # In numpy array konvertieren
            pixels = np.array(image)
            
            # Falls Graustufen oder RGBA
            if len(pixels.shape) == 2:
                pixels = np.stack([pixels] * 3, axis=-1)
            elif pixels.shape[2] == 4:
                pixels = pixels[:, :, :3]
            
            # Reshape für KMeans
            pixels = pixels.reshape(-1, 3)
            
            # KMeans Clustering
            kmeans = KMeans(n_clusters=n_colors, random_state=42, n_init=10)
            kmeans.fit(pixels)
            
            # Zentren und Labels
            centers = kmeans.cluster_centers_
            labels = kmeans.labels_
            
            # Farbanteile berechnen
            label_counts = np.bincount(labels)
            percentages = label_counts / len(labels) * 100
            
            # Sortieren nach Häufigkeit
            sorted_indices = np.argsort(percentages)[::-1]
            
            colors = []
            for idx in sorted_indices:
                r, g, b = centers[idx].astype(int)
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                
                # Nächsten Farbnamen finden
                color_name = self._get_color_name(r, g, b)
                
                # Helligkeit berechnen
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                brightness_label = "hell" if brightness > 128 else "dunkel"
                
                colors.append({
                    "rgb": [int(r), int(g), int(b)],
                    "hex": hex_color,
                    "percentage": round(float(percentages[idx]), 1),
                    "name": color_name,
                    "brightness": brightness_label
                })
            
            return colors
            
        except Exception as e:
            print(f"   ⚠️ Farbextrahierung Fehler: {e}")
            return self._extract_colors_simple(image, n_colors)
    
    def _extract_colors_simple(self, image: Image.Image, n_colors: int) -> List[dict]:
        """Einfache Farbextraktion ohne sklearn"""
        try:
            # Bild verkleinern und Farben quantisieren
            image = image.resize((50, 50))
            image = image.quantize(colors=n_colors)
            palette = image.getpalette()[:n_colors * 3]
            
            colors = []
            for i in range(0, len(palette), 3):
                r, g, b = palette[i], palette[i+1], palette[i+2]
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                
                colors.append({
                    "rgb": [r, g, b],
                    "hex": hex_color,
                    "percentage": round(100 / n_colors, 1),
                    "name": self._get_color_name(r, g, b),
                    "brightness": "hell" if (r + g + b) / 3 > 128 else "dunkel"
                })
            
            return colors
            
        except:
            return []
    
    def _get_color_name(self, r: int, g: int, b: int) -> str:
        """Findet nächsten Farbnamen"""
        min_distance = float('inf')
        closest_name = "unknown"
        
        for name, (cr, cg, cb) in self.COLOR_NAMES.items():
            distance = ((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2) ** 0.5
            if distance < min_distance:
                min_distance = distance
                closest_name = name
        
        return closest_name
    
    # ========================================================
    # BILD ANNOTIEREN
    # ========================================================
    
    def draw_annotations(self, image_path: str, analysis: dict) -> Optional[Image.Image]:
        """
        Zeichnet Markierungen auf das Bild
        
        Args:
            image_path: Pfad zum Bild
            analysis: Analyse-Ergebnisse
            
        Returns:
            Annotiertes PIL Image
        """
        try:
            image = Image.open(image_path)
            draw = ImageDraw.Draw(image)
            
            # Schriftart
            try:
                font = ImageFont.truetype("arial.ttf", 16)
                font_small = ImageFont.truetype("arial.ttf", 12)
            except:
                font = ImageFont.load_default()
                font_small = font
            
            # 1. Gesichter zeichnen (grün)
            faces = analysis.get("faces", [])
            for i, face in enumerate(faces):
                loc = face.get("location", {})
                
                left = loc.get("left", 0)
                top = loc.get("top", 0)
                right = loc.get("right", 0)
                bottom = loc.get("bottom", 0)
                
                # Rechteck
                draw.rectangle(
                    [left, top, right, bottom],
                    outline="#00ff00",
                    width=3
                )
                
                # Label
                draw.text(
                    (left, top - 20),
                    f"Face {i+1}",
                    fill="#00ff00",
                    font=font
                )
            
            # 2. Personen zeichnen (blau)
            persons = analysis.get("persons", [])
            for i, person in enumerate(persons):
                bbox = person.get("bbox", {})
                
                x = bbox.get("x", 0)
                y = bbox.get("y", 0)
                w = bbox.get("width", 0)
                h = bbox.get("height", 0)
                
                # Rechteck
                draw.rectangle(
                    [x, y, x + w, y + h],
                    outline="#0088ff",
                    width=2
                )
                
                # Konfidenz
                conf = person.get("confidence", 0) * 100
                draw.text(
                    (x, y - 20),
                    f"Person {i+1} ({conf:.0f}%)",
                    fill="#0088ff",
                    font=font
                )
            
            # 3. Kleiderfarben zeichnen
            clothing_colors = analysis.get("clothing_colors", [])
            for cc in clothing_colors:
                region = cc.get("region", {})
                colors = cc.get("colors", [])
                
                if not colors:
                    continue
                
                x = region.get("x", 0)
                y = region.get("y", 0)
                w = region.get("width", 0)
                h = region.get("height", 0)
                
                # Kleiner Bereich für Farbpalette
                palette_y = y + h + 5
                palette_size = 20
                
                for j, color in enumerate(colors[:3]):
                    hex_color = color.get("hex", "#888888")
                    px = x + j * (palette_size + 2)
                    
                    draw.rectangle(
                        [px, palette_y, px + palette_size, palette_y + palette_size],
                        fill=hex_color,
                        outline="#ffffff",
                        width=1
                    )
            
            # Info-Text oben
            face_count = analysis.get("face_count", 0)
            person_count = analysis.get("person_count", 0)
            
            info_text = f"👤 {face_count} Gesichter | 🚶 {person_count} Personen"
            draw.rectangle([0, 0, 300, 30], fill="rgba(0,0,0,128)")
            draw.text((10, 5), info_text, fill="#ffffff", font=font)
            
            return image
            
        except Exception as e:
            print(f"❌ Annotierungsfehler: {e}")
            return None
    
    # ========================================================
    # HILFSFUNKTIONEN
    # ========================================================
    
    def get_face_encoding(self, image_path: str) -> Optional[List[float]]:
        """
        Extrahiert Face Encoding aus Bild (für Suche)
        
        Args:
            image_path: Pfad zum Bild
            
        Returns:
            Face Encoding als Liste oder None
        """
        if not FACE_RECOGNITION_AVAILABLE:
            return None
        
        try:
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            
            if encodings:
                return encodings[0].tolist()
            return None
            
        except Exception as e:
            print(f"❌ Encoding Fehler: {e}")
            return None
    
    def get_available_modules(self) -> dict:
        """Gibt verfügbare Module zurück"""
        return self.modules