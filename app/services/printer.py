"""
Drucker-Manager - Windows Freigabe-Drucker
Verwendet win32print für direkten Zugriff auf Windows-Drucker
"""

import os
import win32print
import win32api
import win32ui
import win32con
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass
import tempfile
import logging

# PIL für Bildverarbeitung
from PIL import Image, ImageWin


# ============================================================
# DATENKLASSEN
# ============================================================

@dataclass
class PrinterConfig:
    """Drucker-Konfiguration"""
    name: str  # Windows Freigabename (z.B. \\DESKTOP-GNK1K6H\Hanspeter)
    display_name: str  # Anzeigename
    price: float  # Preis in CHF
    enabled: bool = True
    paper_size: str = "A6"  # A6, A5, A4, etc.

    # Layout-Einstellungen
    page_orientation: str = "Vertical"  # Vertical/Horizontal
    photo_width: float = 175.0  # Foto-Breite in mm
    photo_height: float = 119.0  # Foto-Höhe in mm
    left_margin_photo: float = 2.6  # Linker Rand Foto in mm
    top_margin_photo: float = 7.4  # Oberer Rand Foto in mm

    # Text-Einstellungen
    left_margin_text: float = 139.0  # Linker Rand Text in mm
    top_margin_text: float = 120.6  # Oberer Rand Text in mm
    text_rotation_angle: float = 0.0  # Text-Rotationswinkel in Grad
    text_font_name: str = "Arial"  # Schriftart
    text_size: float = 11.0  # Schriftgröße in mm
    text_color: str = "#000000"  # Textfarbe (#rrggbb)
    enable_print_date: bool = True  # Datum drucken ja/nein


@dataclass
class PrintJob:
    """Druckauftrag"""
    id: str
    image_path: str
    printer_type: str  # 'small' oder 'big'
    printer_name: str
    price: float
    status: str  # 'pending', 'printing', 'completed', 'failed'
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


# ============================================================
# PRINTER MANAGER
# ============================================================

class PrinterManager:
    """Verwaltet Druckaufträge für Windows Freigabe-Drucker"""

    def __init__(self, config, database):
        """
        Args:
            config: Config-Instanz
            database: Database-Instanz
        """
        self.config = config
        self.db = database
        self.logger = logging.getLogger(__name__)

        # Drucker laden (später können mehr hinzugefügt werden)
        self.printers = {
            "small": PrinterConfig(
                name=config.get("printers.small.name", r"\\DESKTOP-GNK1K6H\Hanspeter"),  # Testdrucker
                display_name="Small (Foto)",
                price=config.get("printers.small.price", 5.00),
                enabled=config.get("printers.small.enabled", True),
                paper_size=config.get("printers.small.paper_size", "A6"),

                # Layout-Einstellungen
                page_orientation=config.get("printers.small.page_orientation", "Vertical"),
                photo_width=config.get("printers.small.photo_width", 175.0),
                photo_height=config.get("printers.small.photo_height", 119.0),
                left_margin_photo=config.get("printers.small.left_margin_photo", 2.6),
                top_margin_photo=config.get("printers.small.top_margin_photo", 7.4),

                # Text-Einstellungen
                left_margin_text=config.get("printers.small.left_margin_text", 139.0),
                top_margin_text=config.get("printers.small.top_margin_text", 120.6),
                text_rotation_angle=config.get("printers.small.text_rotation_angle", 0.0),
                text_font_name=config.get("printers.small.text_font_name", "Arial"),
                text_size=config.get("printers.small.text_size", 11.0),
                text_color=config.get("printers.small.text_color", "#000000"),
                enable_print_date=config.get("printers.small.enable_print_date", True)
            ),
            "big": PrinterConfig(
                name=config.get("printers.big.name", ""),  # Später hinzufügen
                display_name="Big (Poster)",
                price=config.get("printers.big.price", 8.00),
                enabled=config.get("printers.big.enabled", True),
                paper_size=config.get("printers.big.paper_size", "A5"),

                # Layout-Einstellungen
                page_orientation=config.get("printers.big.page_orientation", "Vertical"),
                photo_width=config.get("printers.big.photo_width", 175.0),
                photo_height=config.get("printers.big.photo_height", 119.0),
                left_margin_photo=config.get("printers.big.left_margin_photo", 2.6),
                top_margin_photo=config.get("printers.big.top_margin_photo", 7.4),

                # Text-Einstellungen
                left_margin_text=config.get("printers.big.left_margin_text", 139.0),
                top_margin_text=config.get("printers.big.top_margin_text", 120.6),
                text_rotation_angle=config.get("printers.big.text_rotation_angle", 0.0),
                text_font_name=config.get("printers.big.text_font_name", "Arial"),
                text_size=config.get("printers.big.text_size", 11.0),
                text_color=config.get("printers.big.text_color", "#000000"),
                enable_print_date=config.get("printers.big.enable_print_date", True)
            )
        }

        # Drucken global aktiviert?
        self.enabled = config.get("printers.enabled", True)

    # ========================================================
    # DRUCKEN
    # ========================================================

    def print_image(
        self,
        image_path: str,
        printer_type: str = "small",
        copies: int = 1
    ) -> dict:
        """
        Druckt ein Bild über Windows Freigabe

        Args:
            image_path: Pfad zum Bild
            printer_type: 'small' oder 'big'
            copies: Anzahl Kopien

        Returns:
            dict mit Ergebnis
        """
        self.logger.info(f"Druckauftrag gestartet: {Path(image_path).name} -> {printer_type} (Kopien: {copies})")

        # Prüfungen
        if not self.enabled:
            self.logger.error("Drucken ist deaktiviert")
            return {"success": False, "error": "Drucken ist deaktiviert"}

        if printer_type not in self.printers:
            self.logger.error(f"Unbekannter Drucker-Typ: {printer_type}")
            return {"success": False, "error": f"Unbekannter Drucker-Typ: {printer_type}"}

        printer = self.printers[printer_type]

        if not printer.enabled:
            self.logger.error(f"Drucker '{printer.display_name}' ist deaktiviert")
            return {"success": False, "error": f"Drucker '{printer.display_name}' ist deaktiviert"}

        if not printer.name:
            self.logger.error("Kein Drucker konfiguriert")
            return {"success": False, "error": "Kein Drucker konfiguriert"}

        path = Path(image_path)
        if not path.exists():
            self.logger.error(f"Bilddatei nicht gefunden: {path}")
            return {"success": False, "error": "Bilddatei nicht gefunden"}

        self.logger.info(f"Bild gefunden: {path}, Größe: {path.stat().st_size} bytes")

        # Druckauftrag erstellen
        try:
            job_id = self.db.add_print_job({
                "image_id": path.stem,
                "image_filename": path.name,
                "printer_type": printer_type,
                "printer_name": printer.name,
                "price": printer.price * copies
            })
            self.logger.info(f"Druckauftrag erstellt: {job_id}")
        except Exception as e:
            self.logger.error(f"Fehler beim Erstellen des Druckauftrags: {e}")
            return {"success": False, "error": f"Druckauftrag konnte nicht erstellt werden: {e}"}

        try:
            # Bild für Druck vorbereiten (Größenanpassung)
            self.logger.info(f"Bereite Bild vor für Papierformat: {printer.paper_size}")
            print_path = self._prepare_image_for_print(path, printer.paper_size)
            self.logger.info(f"Vorbereitetes Bild: {print_path}, Größe: {print_path.stat().st_size} bytes")

            # An Windows-Drucker senden
            self.logger.info(f"Sende an Drucker: {printer.name}")
            success = self._send_to_printer(print_path, printer.name, copies)

            if success:
                self.logger.info(f"✅ Druckauftrag erfolgreich: {path.name} -> {printer.display_name}")
                print(f"✅ Druckauftrag gesendet: {path.name} -> {printer.display_name}")
                return {
                    "success": True,
                    "job_id": job_id,
                    "printer": printer.display_name,
                    "price": printer.price * copies,
                    "copies": copies
                }
            else:
                self.logger.error(f"❌ Druckbefehl fehlgeschlagen: {path.name}")
                return {"success": False, "error": "Druckbefehl fehlgeschlagen"}

        except Exception as e:
            self.logger.error(f"❌ Druckfehler: {e}")
            print(f"❌ Druckfehler: {e}")
            return {"success": False, "error": str(e)}

    def _prepare_image_for_print(self, image_path: Path, paper_size: str) -> Path:
        """
        Bereitet Bild für Druck vor (ohne Größenanpassung - Drucker übernimmt Skalierung)

        Args:
            image_path: Pfad zum Bild
            paper_size: Papiergröße (wird nicht verwendet)

        Returns:
            Pfad zum vorbereiteten Bild
        """
        # Bild öffnen und als JPEG speichern (für Kompatibilität mit Druckern)
        image = Image.open(image_path)

        # Temporäre Datei erstellen
        temp_dir = Path(tempfile.gettempdir()) / "photo_software"
        temp_dir.mkdir(exist_ok=True)

        temp_path = temp_dir / f"print_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        image.save(temp_path, "JPEG", quality=95)

        return temp_path

    def _send_to_printer(self, image_path: Path, printer_name: str, copies: int = 1) -> bool:
        """
        Sendet Bild an Windows-Drucker über GDI mit benutzerdefinierten Layout-Einstellungen

        Args:
            image_path: Pfad zum Bild
            printer_name: Windows Freigabename
            copies: Anzahl Kopien

        Returns:
            True bei Erfolg
        """
        try:
            self.logger.info(f"Drucke {image_path} auf {printer_name} mit GDI")

            # Bild laden
            img = Image.open(image_path)
            self.logger.info(f"Bild geladen: {img.size}, Mode: {img.mode}")

            for copy_num in range(copies):
                self.logger.info(f"Drucke Kopie {copy_num + 1}/{copies}")

                # Device Context für Drucker erstellen
                hdc = win32ui.CreateDC()
                hdc.CreatePrinterDC(printer_name)
                self.logger.info("Printer DC erstellt")

                try:
                    # Dokument starten
                    hdc.StartDoc(str(image_path))
                    hdc.StartPage()
                    self.logger.info("Dokument und Seite gestartet")

                    # Druckbereich ermitteln (in Pixel)
                    printable_width = hdc.GetDeviceCaps(win32con.HORZRES)
                    printable_height = hdc.GetDeviceCaps(win32con.VERTRES)

                    # DPI ermitteln für mm zu Pixel Konvertierung
                    dpi_x = hdc.GetDeviceCaps(win32con.LOGPIXELSX)
                    dpi_y = hdc.GetDeviceCaps(win32con.LOGPIXELSY)
                    self.logger.info(f"Druckbereich: {printable_width}x{printable_height} Pixel bei {dpi_x}x{dpi_y} DPI")

                    # Welcher Drucker wird verwendet? (bestimmen aus printer_name)
                    printer_config = None
                    for printer_type, config in self.printers.items():
                        if config.name == printer_name:
                            printer_config = config
                            break

                    if not printer_config:
                        # Fallback auf small printer
                        printer_config = self.printers["small"]
                        self.logger.warning(f"Drucker-Konfiguration nicht gefunden für {printer_name}, verwende small")

                    # Layout-Einstellungen anwenden
                    photo_width_mm = printer_config.photo_width  # mm
                    photo_height_mm = printer_config.photo_height  # mm
                    left_margin_mm = printer_config.left_margin_photo  # mm
                    top_margin_mm = printer_config.top_margin_photo  # mm

                    # mm zu Pixel konvertieren
                    photo_width_px = int((photo_width_mm * dpi_x) / 25.4)  # 25.4 mm = 1 inch
                    photo_height_px = int((photo_height_mm * dpi_y) / 25.4)
                    left_margin_px = int((left_margin_mm * dpi_x) / 25.4)
                    top_margin_px = int((top_margin_mm * dpi_y) / 25.4)

                    self.logger.info(f"Layout: Foto {photo_width_px}x{photo_height_px} Pixel bei ({left_margin_px}, {top_margin_px})")

                    # Bild skalieren und positionieren
                    img_width, img_height = img.size

                    # Skalierung basierend auf Layout-Größe
                    scale_x = photo_width_px / img_width
                    scale_y = photo_height_px / img_height
                    scale = min(scale_x, scale_y)  # Seitenverhältnis beibehalten

                    new_width = int(img_width * scale)
                    new_height = int(img_height * scale)

                    # Zentrieren innerhalb des Layout-Bereichs
                    x = left_margin_px + (photo_width_px - new_width) // 2
                    y = top_margin_px + (photo_height_px - new_height) // 2

                    self.logger.info(f"Bild-Skalierung: {img_width}x{img_height} -> {new_width}x{new_height} bei ({x},{y})")

                    # Bild zeichnen
                    dib = ImageWin.Dib(img)
                    dib.draw(hdc.GetHandleOutput(), (x, y, x + new_width, y + new_height))
                    self.logger.info("Bild gezeichnet")

                    # Text hinzufügen falls aktiviert
                    if printer_config.enable_print_date:
                        self._draw_text_on_printer(hdc, printer_config, dpi_x, dpi_y)
                        self.logger.info("Datum hinzugefügt")

                    # Seite beenden
                    hdc.EndPage()
                    hdc.EndDoc()
                    self.logger.info("Seite und Dokument beendet")

                finally:
                    hdc.DeleteDC()
                    self.logger.info("DC gelöscht")

            return True

        except Exception as e:
            self.logger.error(f"❌ GDI Druckfehler: {e}")
            print(f"❌ GDI Druckfehler: {e}")
            return False

    def _draw_text_on_printer(self, hdc, printer_config, dpi_x: int, dpi_y: int) -> None:
        """
        Zeichnet Text (z.B. Datum) auf den Drucker

        Args:
            hdc: Device Context
            printer_config: Drucker-Konfiguration
            dpi_x, dpi_y: DPI-Werte
        """
        try:
            from datetime import datetime

            # Text-Einstellungen
            text = datetime.now().strftime("%d.%m.%Y")
            font_name = printer_config.text_font_name
            font_size_mm = printer_config.text_size  # mm
            text_color = printer_config.text_color  # #rrggbb
            rotation = printer_config.text_rotation_angle  # Grad

            # Position in mm zu Pixel konvertieren
            left_margin_px = int((printer_config.left_margin_text * dpi_x) / 25.4)
            top_margin_px = int((printer_config.top_margin_text * dpi_y) / 25.4)

            # Schriftgröße in mm zu Pixel konvertieren (ungefähr)
            font_size_px = int((font_size_mm * dpi_y) / 25.4)

            # Farbe parsen (#rrggbb -> RGB)
            r = int(text_color[1:3], 16)
            g = int(text_color[3:5], 16)
            b = int(text_color[5:7], 16)

            # Font erstellen
            font = win32ui.CreateFont({
                "name": font_name,
                "height": font_size_px,
                "weight": 400,  # Normal
            })

            # Alte Font speichern
            old_font = hdc.SelectObject(font)

            # Textfarbe setzen
            hdc.SetTextColor(win32api.RGB(r, g, b))
            hdc.SetBkMode(win32con.TRANSPARENT)

            # Rotation anwenden falls nötig
            if rotation != 0:
                # Für Rotation müssten wir komplexere GDI-Operationen verwenden
                # Vereinfacht: Rotation ignorieren für jetzt
                pass

            # Text zeichnen
            hdc.TextOut(left_margin_px, top_margin_px, text)

            # Font zurücksetzen
            hdc.SelectObject(old_font)
            font.DeleteObject()

        except Exception as e:
            self.logger.error(f"Fehler beim Zeichnen des Textes: {e}")

    # ========================================================
    # DRUCKER-VERWALTUNG
    # ========================================================

    def get_printer_info(self, printer_type: str) -> Optional[dict]:
        """Gibt Drucker-Informationen zurück"""
        if printer_type not in self.printers:
            return None

        printer = self.printers[printer_type]

        return {
            "type": printer_type,
            "name": printer.name,
            "display_name": printer.display_name,
            "price": printer.price,
            "enabled": printer.enabled,
            "paper_size": printer.paper_size,

            # Layout-Einstellungen
            "page_orientation": printer.page_orientation,
            "photo_width": printer.photo_width,
            "photo_height": printer.photo_height,
            "left_margin_photo": printer.left_margin_photo,
            "top_margin_photo": printer.top_margin_photo,

            # Text-Einstellungen
            "left_margin_text": printer.left_margin_text,
            "top_margin_text": printer.top_margin_text,
            "text_rotation_angle": printer.text_rotation_angle,
            "text_font_name": printer.text_font_name,
            "text_size": printer.text_size,
            "text_color": printer.text_color,
            "enable_print_date": printer.enable_print_date
        }

    def get_all_printers(self) -> List[dict]:
        """Gibt alle Drucker zurück"""
        return [
            self.get_printer_info(pt)
            for pt in self.printers.keys()
        ]

    def update_printer(
        self,
        printer_type: str,
        name: str = None,
        price: float = None,
        enabled: bool = None,
        paper_size: str = None,
        page_orientation: str = None,
        photo_width: float = None,
        photo_height: float = None,
        left_margin_photo: float = None,
        top_margin_photo: float = None,
        left_margin_text: float = None,
        top_margin_text: float = None,
        text_rotation_angle: float = None,
        text_font_name: str = None,
        text_size: float = None,
        text_color: str = None,
        enable_print_date: bool = None
    ) -> bool:
        """Aktualisiert Drucker-Einstellungen"""
        if printer_type not in self.printers:
            return False

        printer = self.printers[printer_type]

        # Grundlegende Einstellungen
        if name is not None:
            printer.name = name
            self.config.set(f"printers.{printer_type}.name", name)

        if price is not None:
            printer.price = price
            self.config.set(f"printers.{printer_type}.price", price)

        if enabled is not None:
            printer.enabled = enabled
            self.config.set(f"printers.{printer_type}.enabled", enabled)

        if paper_size is not None:
            printer.paper_size = paper_size
            self.config.set(f"printers.{printer_type}.paper_size", paper_size)

        # Layout-Einstellungen
        if page_orientation is not None:
            printer.page_orientation = page_orientation
            self.config.set(f"printers.{printer_type}.page_orientation", page_orientation)

        if photo_width is not None:
            printer.photo_width = photo_width
            self.config.set(f"printers.{printer_type}.photo_width", photo_width)

        if photo_height is not None:
            printer.photo_height = photo_height
            self.config.set(f"printers.{printer_type}.photo_height", photo_height)

        if left_margin_photo is not None:
            printer.left_margin_photo = left_margin_photo
            self.config.set(f"printers.{printer_type}.left_margin_photo", left_margin_photo)

        if top_margin_photo is not None:
            printer.top_margin_photo = top_margin_photo
            self.config.set(f"printers.{printer_type}.top_margin_photo", top_margin_photo)

        # Text-Einstellungen
        if left_margin_text is not None:
            printer.left_margin_text = left_margin_text
            self.config.set(f"printers.{printer_type}.left_margin_text", left_margin_text)

        if top_margin_text is not None:
            printer.top_margin_text = top_margin_text
            self.config.set(f"printers.{printer_type}.top_margin_text", top_margin_text)

        if text_rotation_angle is not None:
            printer.text_rotation_angle = text_rotation_angle
            self.config.set(f"printers.{printer_type}.text_rotation_angle", text_rotation_angle)

        if text_font_name is not None:
            printer.text_font_name = text_font_name
            self.config.set(f"printers.{printer_type}.text_font_name", text_font_name)

        if text_size is not None:
            printer.text_size = text_size
            self.config.set(f"printers.{printer_type}.text_size", text_size)

        if text_color is not None:
            printer.text_color = text_color
            self.config.set(f"printers.{printer_type}.text_color", text_color)

        if enable_print_date is not None:
            printer.enable_print_date = enable_print_date
            self.config.set(f"printers.{printer_type}.enable_print_date", enable_print_date)

        self.config.save()
        return True

    def set_enabled(self, enabled: bool) -> None:
        """Aktiviert/Deaktiviert Drucken global"""
        self.enabled = enabled
        self.config.set("printers.enabled", enabled)
        self.config.save()

    # ========================================================
    # STATISTIKEN
    # ========================================================

    def get_stats(self) -> dict:
        """Gibt Druck-Statistiken zurück"""
        return self.db.get_print_stats()

    def get_price(self, printer_type: str, copies: int = 1) -> float:
        """Berechnet Preis für Druckauftrag"""
        if printer_type not in self.printers:
            return 0.0

        return self.printers[printer_type].price * copies

    # ========================================================
    # WINDOWS DRUCKER AUFLISTEN
    # ========================================================

    @staticmethod
    def list_windows_printers() -> List[str]:
        """
        Listet alle installierten Windows-Drucker auf

        Returns:
            Liste der Druckernamen
        """
        try:
            printers = []
            for printer_info in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS):
                printers.append(printer_info[2])  # pPrinterName

            return printers

        except Exception as e:
            print(f"❌ Fehler beim Auflisten der Drucker: {e}")
            return []

    @staticmethod
    def test_printer(printer_name: str) -> dict:
        """
        Testet ob Drucker erreichbar ist

        Args:
            printer_name: Druckername

        Returns:
            dict mit Testergebnis
        """
        try:
            # Liste aller verfügbaren Drucker
            available_printers = PrinterManager.list_windows_printers()

            # Prüfe ob der Druckername in der Liste ist
            if printer_name in available_printers:
                return {"success": True, "message": "Drucker erreichbar"}
            else:
                return {
                    "success": False,
                    "message": f"Drucker '{printer_name}' nicht in der Liste verfügbarer Drucker gefunden. Verfügbare Drucker: {', '.join(available_printers[:5])}..."
                }

        except Exception as e:
            return {"success": False, "message": str(e)}
