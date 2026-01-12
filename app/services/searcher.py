"""
Bildsuche - Gesichtserkennung und Farbbasierte Suche
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import colorsys

# Face Recognition
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False


# ============================================================
# DATENKLASSEN
# ============================================================

@dataclass
class SearchResult:
    """Einzelnes Suchergebnis"""
    image_id: str
    filename: str
    score: float  # 0-100%
    match_type: str  # 'face', 'color', 'combined'
    face_score: float = 0.0
    color_score: float = 0.0
    details: Dict = None
    
    def to_dict(self) -> dict:
        return {
            "image_id": self.image_id,
            "filename": self.filename,
            "score": round(self.score, 1),
            "match_type": self.match_type,
            "face_score": round(self.face_score, 1),
            "color_score": round(self.color_score, 1),
            "details": self.details or {}
        }


# ============================================================
# IMAGE SEARCHER
# ============================================================

class ImageSearcher:
    """Sucht Bilder nach Gesicht oder Kleiderfarben"""
    
    def __init__(self, config, database):
        """
        Args:
            config: Config-Instanz
            database: Database-Instanz
        """
        self.config = config
        self.db = database
        
        # Such-Einstellungen
        self.face_threshold = config.get("search.face_threshold", 0.6)
        self.color_threshold = config.get("search.color_threshold", 50)
        self.max_results = config.get("search.max_results", 20)
    
    # ========================================================
    # KOMBINIERTE SUCHE
    # ========================================================
    
    def search(
        self,
        face_encoding: List[float] = None,
        colors: List[dict] = None,
        face_weight: float = 0.7,
        color_weight: float = 0.3,
        limit: int = None
    ) -> List[dict]:
        """
        Kombinierte Suche nach Gesicht und/oder Farben
        
        Args:
            face_encoding: Face-Encoding des Suchbilds
            colors: Liste der Suchfarben [{"rgb": [r,g,b]}, ...]
            face_weight: Gewichtung der Gesichtserkennung (0-1)
            color_weight: Gewichtung der Farbsuche (0-1)
            limit: Maximale Ergebnisse
            
        Returns:
            Liste der Suchergebnisse sortiert nach Score
        """
        limit = limit or self.max_results
        results = []
        
        # Alle Bilder aus Datenbank
        all_images = self.db.get_all_images()
        
        if not all_images:
            return []
        
        for image_data in all_images:
            face_score = 0.0
            color_score = 0.0
            match_details = {}
            
            # 1. Face-Matching
            if face_encoding and FACE_RECOGNITION_AVAILABLE:
                face_result = self._match_face(
                    face_encoding,
                    image_data.get("face_encodings", [])
                )
                face_score = face_result["score"]
                match_details["face"] = face_result
            
            # 2. Color-Matching
            if colors:
                color_result = self._match_colors(
                    colors,
                    image_data.get("clothing_colors", [])
                )
                color_score = color_result["score"]
                match_details["color"] = color_result
            
            # 3. Kombinierter Score
            if face_encoding and colors:
                # Beide Kriterien
                combined_score = (face_score * face_weight + color_score * color_weight)
                match_type = "combined"
            elif face_encoding:
                combined_score = face_score
                match_type = "face"
            elif colors:
                combined_score = color_score
                match_type = "color"
            else:
                continue
            
            # Mindest-Score prüfen
            min_score = 20  # Mindestens 20% Übereinstimmung
            if combined_score >= min_score:
                result = SearchResult(
                    image_id=image_data.get("id", ""),
                    filename=image_data.get("filename", ""),
                    score=combined_score,
                    match_type=match_type,
                    face_score=face_score,
                    color_score=color_score,
                    details=match_details
                )
                results.append(result)
        
        # Nach Score sortieren
        results.sort(key=lambda x: x.score, reverse=True)
        
        # Limit anwenden
        results = results[:limit]
        
        # Als dict zurückgeben
        return [r.to_dict() for r in results]
    
    # ========================================================
    # GESICHTSSUCHE
    # ========================================================
    
    def search_by_face(
        self,
        face_encoding: List[float],
        limit: int = None
    ) -> List[dict]:
        """
        Sucht Bilder nach Gesicht
        
        Args:
            face_encoding: Face-Encoding des Suchbilds
            limit: Maximale Ergebnisse
            
        Returns:
            Liste der Suchergebnisse
        """
        return self.search(
            face_encoding=face_encoding,
            colors=None,
            face_weight=1.0,
            color_weight=0.0,
            limit=limit
        )
    
    def search_by_face_image(
        self,
        image_path: str,
        limit: int = None
    ) -> List[dict]:
        """
        Sucht Bilder anhand eines Gesichtsfotos
        
        Args:
            image_path: Pfad zum Suchbild
            limit: Maximale Ergebnisse
            
        Returns:
            Liste der Suchergebnisse
        """
        if not FACE_RECOGNITION_AVAILABLE:
            return []
        
        try:
            # Gesicht im Suchbild finden
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            
            if not encodings:
                print("⚠️ Kein Gesicht im Suchbild gefunden")
                return []
            
            # Mit erstem gefundenen Gesicht suchen
            return self.search_by_face(encodings[0].tolist(), limit)
            
        except Exception as e:
            print(f"❌ Fehler bei Gesichtssuche: {e}")
            return []
    
    def _match_face(
        self,
        search_encoding: List[float],
        image_encodings: List[List[float]]
    ) -> dict:
        """
        Vergleicht Gesichts-Encodings
        
        Args:
            search_encoding: Encoding des Suchgesichts
            image_encodings: Encodings im Bild
            
        Returns:
            dict mit score und details
        """
        if not image_encodings or not FACE_RECOGNITION_AVAILABLE:
            return {"score": 0.0, "matched": False, "distance": 1.0}
        
        try:
            search_np = np.array(search_encoding)
            
            best_distance = 1.0
            best_index = -1
            
            for i, encoding in enumerate(image_encodings):
                encoding_np = np.array(encoding)
                
                # Euklidische Distanz berechnen
                distance = np.linalg.norm(search_np - encoding_np)
                
                if distance < best_distance:
                    best_distance = distance
                    best_index = i
            
            # Score berechnen (0 = perfekt, 1 = keine Übereinstimmung)
            # Threshold ist typisch 0.6
            threshold = self.face_threshold
            
            if best_distance <= threshold:
                # Lineare Skalierung: 0 -> 100%, threshold -> 50%
                score = max(0, 100 - (best_distance / threshold) * 50)
                matched = True
            else:
                # Über Threshold: 50% -> 0%
                score = max(0, 50 - ((best_distance - threshold) / (1 - threshold)) * 50)
                matched = False
            
            return {
                "score": score,
                "matched": matched,
                "distance": round(best_distance, 4),
                "threshold": threshold,
                "matched_face_index": best_index
            }
            
        except Exception as e:
            print(f"❌ Face-Matching Fehler: {e}")
            return {"score": 0.0, "matched": False, "distance": 1.0}
    
    # ========================================================
    # FARBSUCHE
    # ========================================================
    
    def search_by_color(
        self,
        colors: List[dict],
        limit: int = None
    ) -> List[dict]:
        """
        Sucht Bilder nach Kleiderfarben
        
        Args:
            colors: Liste der Suchfarben [{"rgb": [r,g,b]}, ...]
            limit: Maximale Ergebnisse
            
        Returns:
            Liste der Suchergebnisse
        """
        return self.search(
            face_encoding=None,
            colors=colors,
            face_weight=0.0,
            color_weight=1.0,
            limit=limit
        )
    
    def _match_colors(
        self,
        search_colors: List[dict],
        image_colors: List[dict]
    ) -> dict:
        """
        Vergleicht Kleiderfarben
        
        Args:
            search_colors: Gesuchte Farben
            image_colors: Farben im Bild
            
        Returns:
            dict mit score und details
        """
        if not search_colors or not image_colors:
            return {"score": 0.0, "matched_colors": []}
        
        try:
            matched_colors = []
            total_score = 0.0
            
            # Alle Farben aus dem Bild sammeln
            all_image_colors = []
            for color_set in image_colors:
                colors_list = color_set.get("colors", [])
                all_image_colors.extend(colors_list)
            
            if not all_image_colors:
                return {"score": 0.0, "matched_colors": []}
            
            # Jede Suchfarbe prüfen
            for search_color in search_colors:
                search_rgb = search_color.get("rgb", [128, 128, 128])
                
                best_match = None
                best_distance = float('inf')
                
                for img_color in all_image_colors:
                    img_rgb = img_color.get("rgb", [128, 128, 128])
                    
                    # Farbdistanz berechnen
                    distance = self._color_distance(search_rgb, img_rgb)
                    
                    if distance < best_distance:
                        best_distance = distance
                        best_match = img_color
                
                # Score für diese Farbe
                threshold = self.color_threshold
                
                if best_distance <= threshold:
                    color_score = 100 - (best_distance / threshold) * 50
                    matched_colors.append({
                        "search": search_rgb,
                        "found": best_match.get("rgb") if best_match else None,
                        "distance": round(best_distance, 1),
                        "score": round(color_score, 1)
                    })
                    total_score += color_score
                else:
                    color_score = max(0, 50 - ((best_distance - threshold) / threshold) * 50)
                    total_score += color_score
            
            # Durchschnittlicher Score
            avg_score = total_score / len(search_colors) if search_colors else 0
            
            return {
                "score": avg_score,
                "matched_colors": matched_colors,
                "threshold": self.color_threshold
            }
            
        except Exception as e:
            print(f"❌ Farb-Matching Fehler: {e}")
            return {"score": 0.0, "matched_colors": []}
    
    def _color_distance(self, color1: List[int], color2: List[int]) -> float:
        """
        Berechnet Farbdistanz (euklidisch im RGB-Raum)
        
        Args:
            color1: [R, G, B]
            color2: [R, G, B]
            
        Returns:
            Distanz (0-441.67)
        """
        r1, g1, b1 = color1[:3]
        r2, g2, b2 = color2[:3]
        
        return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
    
    def _color_distance_lab(self, color1: List[int], color2: List[int]) -> float:
        """
        Berechnet Farbdistanz im LAB-Farbraum (perzeptuell genauer)
        
        Args:
            color1: [R, G, B]
            color2: [R, G, B]
            
        Returns:
            Distanz
        """
        def rgb_to_lab(rgb):
            # RGB -> XYZ
            r, g, b = [x / 255.0 for x in rgb[:3]]
            
            r = ((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92
            g = ((g + 0.055) / 1.055) ** 2.4 if g > 0.04045 else g / 12.92
            b = ((b + 0.055) / 1.055) ** 2.4 if b > 0.04045 else b / 12.92
            
            x = r * 0.4124 + g * 0.3576 + b * 0.1805
            y = r * 0.2126 + g * 0.7152 + b * 0.0722
            z = r * 0.0193 + g * 0.1192 + b * 0.9505
            
            # XYZ -> LAB
            x /= 0.95047
            y /= 1.0
            z /= 1.08883
            
            x = x ** (1/3) if x > 0.008856 else (7.787 * x) + 16/116
            y = y ** (1/3) if y > 0.008856 else (7.787 * y) + 16/116
            z = z ** (1/3) if z > 0.008856 else (7.787 * z) + 16/116
            
            L = (116 * y) - 16
            a = 500 * (x - y)
            b = 200 * (y - z)
            
            return L, a, b
        
        L1, a1, b1 = rgb_to_lab(color1)
        L2, a2, b2 = rgb_to_lab(color2)
        
        return ((L1 - L2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2) ** 0.5
    
    # ========================================================
    # HILFSFUNKTIONEN
    # ========================================================
    
    def update_thresholds(self, face_threshold: float = None, color_threshold: float = None):
        """Aktualisiert Such-Schwellwerte"""
        if face_threshold is not None:
            self.face_threshold = face_threshold
        if color_threshold is not None:
            self.color_threshold = color_threshold
    
    def get_search_stats(self) -> dict:
        """Gibt Such-Statistiken zurück"""
        all_images = self.db.get_all_images()
        
        total_faces = sum(img.get("face_count", 0) for img in all_images)
        total_with_faces = sum(1 for img in all_images if img.get("face_count", 0) > 0)
        total_with_colors = sum(1 for img in all_images if img.get("clothing_colors"))
        
        return {
            "total_images": len(all_images),
            "images_with_faces": total_with_faces,
            "images_with_colors": total_with_colors,
            "total_faces": total_faces,
            "face_threshold": self.face_threshold,
            "color_threshold": self.color_threshold,
            "max_results": self.max_results
        }
    
    def parse_color_from_hex(self, hex_color: str) -> dict:
        """Konvertiert Hex-Farbe zu RGB-dict"""
        hex_color = hex_color.lstrip('#')
        
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        return {"rgb": [r, g, b], "hex": f"#{hex_color}"}