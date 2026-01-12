#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Photo Software - Hauptstartskript
Startet die FastAPI Anwendung mit allen notwendigen Initialisierungen
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Pfad zum App-Verzeichnis zum Python-Path hinzufügen
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# ========================================
# LOGGING KONFIGURATION
# ========================================

def setup_logging(log_level='INFO'):
    """Konfiguriert Logging"""
    log_dir = ROOT_DIR / 'data' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / 'app.log'
    
    # Format
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # File Handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Farbiges Logging für Console (optional)
    try:
        import colorlog
        console_handler.setFormatter(colorlog.ColoredFormatter(
            '%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s',
            datefmt=date_format,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        ))
    except ImportError:
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # Root Logger konfigurieren
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[file_handler, console_handler]
    )
    
    # Externe Logger leiser stellen
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('watchdog').setLevel(logging.WARNING)


# ========================================
# SYSTEM-PRÜFUNGEN
# ========================================

def check_python_version():
    """Prüft Python Version"""
    required_version = (3, 8)
    current_version = sys.version_info[:2]
    
    if current_version < required_version:
        print("[FEHLER] Python {}.{}+ erforderlich".format(required_version[0], required_version[1]))
        print("   Aktuelle Version: {}.{}".format(current_version[0], current_version[1]))
        sys.exit(1)
    
    print("[OK] Python {}.{}".format(current_version[0], current_version[1]))


def check_dependencies():
    """Prüft ob alle Abhängigkeiten installiert sind"""
    required_packages = {
        'fastapi': 'FastAPI',
        'uvicorn': 'Uvicorn',
        'face_recognition': 'Face Recognition',
        'cv2': 'OpenCV',
        'PIL': 'Pillow',
        'ultralytics': 'Ultralytics (YOLO)',
        'sklearn': 'scikit-learn',
        'numpy': 'NumPy',
        'watchdog': 'Watchdog'
    }
    
    missing = []
    
    for package, name in required_packages.items():
        try:
            __import__(package)
            print("[OK] {}".format(name))
        except ImportError:
            print("[FEHLER] {} nicht installiert".format(name))
            missing.append(name)
    
    if missing:
        print("\n[WARNUNG] Fehlende Pakete: {}".format(', '.join(missing)))
        print("   Installiere mit: pip install -r requirements.txt")
        return False
    
    return True


def check_gpu():
    """Prüft GPU-Verfügbarkeit für YOLO/PyTorch"""
    try:
        import torch
        
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print("[OK] GPU verfügbar: {}".format(gpu_name))
            return True
        else:
            print("[INFO] Keine GPU - CPU wird verwendet")
            return False
    except ImportError:
        print("[INFO] PyTorch nicht installiert - GPU-Check übersprungen")
        return False


# ========================================
# ORDNER-STRUKTUR
# ========================================

def create_directory_structure():
    """Erstellt alle benötigten Ordner"""
    directories = [
        'data',
        'data/logs',
        'data/settings',
        'photos',
        'photos/input',
        'photos/temp',
        'photos/processed',
        'photos/output',
        'models'
    ]
    
    print("\n[ORDNER] Erstelle Ordnerstruktur...")
    
    for directory in directories:
        path = ROOT_DIR / directory
        path.mkdir(parents=True, exist_ok=True)
        print("   [OK] {}".format(directory))


# ========================================
# DATENBANK INITIALISIERUNG
# ========================================

def initialize_database():
    """Initialisiert JSON-Datenbanken"""
    from app.config import Config
    from app.database import Database
    
    print("\n[DATENBANK] Initialisiere Datenbank...")
    
    config = Config()
    config.load()
    
    db = Database(config)
    db.load()
    
    print("   [OK] {} Bilder in Datenbank".format(db.count_images()))
    
    return config, db


# ========================================
# YOLO MODEL DOWNLOAD
# ========================================

def download_yolo_model(model_size='n'):
    """Lädt YOLO Model herunter falls nicht vorhanden"""
    try:
        from ultralytics import YOLO
        
        model_path = ROOT_DIR / 'models' / 'yolov8{}.pt'.format(model_size)
        
        if not model_path.exists():
            print("\n[DOWNLOAD] Lade YOLO Model (yolov8{})...".format(model_size))
            model = YOLO('yolov8{}.pt'.format(model_size))
            
            # Model verschieben
            import shutil
            src = Path.home() / '.ultralytics' / 'weights' / 'yolov8{}.pt'.format(model_size)
            if src.exists():
                shutil.copy(src, model_path)
                print("   [OK] Model gespeichert: {}".format(model_path))
        else:
            print("   [OK] YOLO Model bereits vorhanden")
        
        return True
    except Exception as e:
        print("   [WARNUNG] YOLO Model Download fehlgeschlagen: {}".format(e))
        return False


# ========================================
# SERVER STARTEN
# ========================================

def start_server(host='0.0.0.0', port=8000, reload=False, workers=1):
    """Startet den FastAPI Server"""
    import uvicorn
    import threading
    import time

    print("\n" + "="*60)
    print("PHOTO SOFTWARE WIRD GESTARTET")
    print("="*60)

    config_kwargs = {
        'app': 'app.main:app',
        'host': host,
        'port': port,
        'reload': reload,
        'log_level': 'info',
        'access_log': True
    }

    # Workers nur ohne Reload
    if not reload and workers > 1:
        config_kwargs['workers'] = workers

    print("\n[SERVER] Server läuft auf: http://{}:{}".format(host, port))
    print("[ADMIN] Admin-Panel:     http://{}:{}/admin/".format(host, port))
    print("[KUNDE] Kundenbereich:   http://{}:{}/customer/".format(host, port))
    print("[GALERIE] Galerie:       http://{}:{}/gallery/".format(host, port))
    print("\n[INFO] Zum Beenden: CTRL+C\n")
    print("="*60 + "\n")

    # Auto-Start Watcher prüfen
    try:
        from app.config import Config
        config = Config()
        config.load()

        auto_start_watcher = config.get('processing.auto_start_watcher', False)

        if auto_start_watcher:
            def delayed_watcher_start():
                """Startet den Watcher nach 1 Minute Verzögerung"""
                time.sleep(60)  # 1 Minute warten

                try:
                    # Watcher über API starten
                    import requests
                    response = requests.post('http://localhost:{}/admin/api/watcher/toggle'.format(port))

                    if response.status_code == 200:
                        print("[WATCHER] Überwachung automatisch gestartet (1 Min. Verzögerung)")
                    else:
                        print("[WATCHER] Automatischer Start fehlgeschlagen")
                except Exception as e:
                    print("[WATCHER] Fehler beim automatischen Start: {}".format(e))

            # Watcher in separatem Thread starten
            watcher_thread = threading.Thread(target=delayed_watcher_start, daemon=True)
            watcher_thread.start()
            print("[WATCHER] Automatischer Start in 1 Minute geplant...")

    except Exception as e:
        print("[WATCHER] Konfiguration für Auto-Start konnte nicht geladen werden: {}".format(e))

    try:
        uvicorn.run(**config_kwargs)
    except KeyboardInterrupt:
        print("\n\n[STOP] Server wird beendet...")
        print("[BYE] Auf Wiedersehen!\n")


# ========================================
# HAUPTFUNKTION
# ========================================

def main():
    """Hauptfunktion"""
    
    # Argument Parser
    parser = argparse.ArgumentParser(
        description='Photo Software - Foto-Analyse mit Gesichtserkennung',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python run.py                          # Standard-Start
  python run.py --host 127.0.0.1         # Nur localhost
  python run.py --port 8080              # Anderer Port
  python run.py --reload                 # Mit Auto-Reload (Development)
  python run.py --workers 4              # Mit 4 Worker-Prozessen
  python run.py --skip-checks            # Ohne System-Checks
        """
    )
    
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Server Host (default: 0.0.0.0)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Server Port (default: 8000)'
    )
    
    parser.add_argument(
        '--reload',
        action='store_true',
        help='Auto-Reload aktivieren (Development Mode)'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='Anzahl Worker-Prozesse (default: 1)'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Log-Level (default: INFO)'
    )
    
    parser.add_argument(
        '--skip-checks',
        action='store_true',
        help='System-Checks überspringen'
    )
    
    parser.add_argument(
        '--download-models',
        action='store_true',
        help='Nur YOLO Models herunterladen und beenden'
    )
    
    args = parser.parse_args()
    
    # ASCII Art Banner
    print("\n" + "="*60)
    print("""
    ____  __  ______  __________     ______ ____  ____________
   / __ \/ / / / __ \/_  __/ __ \   / ___// __ \/ ____/_  __/
  / /_/ / /_/ / / / / / / / / / /   \__ \/ / / / /_    / /   
 / ____/ __  / /_/ / / / / /_/ /   ___/ / /_/ / __/   / /    
/_/   /_/ /_/\____/ /_/  \____/   /____/\____/_/     /_/     
                                                              
    Photo Recognition & Search Software v1.0.0
    """)
    print("="*60 + "\n")
    
    # Logging einrichten
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    logger.info("Startzeit: {}".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    # Nur Model-Download
    if args.download_models:
        print("[DOWNLOAD] Lade YOLO Models...")
        for size in ['n', 's', 'm']:
            download_yolo_model(size)
        print("\n[OK] Download abgeschlossen")
        return
    
    # System-Checks
    if not args.skip_checks:
        print("[CHECK] System-Checks...\n")
        
        check_python_version()
        
        if not check_dependencies():
            print("\n[FEHLER] Abhängigkeiten fehlen. Installation erforderlich.")
            print("   Führe aus: pip install -r requirements.txt\n")
            sys.exit(1)
        
        check_gpu()
    
    # Ordnerstruktur
    create_directory_structure()
    
    # Datenbank initialisieren
    try:
        config, db = initialize_database()
        logger.info("Datenbank initialisiert")
    except Exception as e:
        logger.error("Datenbank-Initialisierung fehlgeschlagen: {}".format(e))
        print("\n[FEHLER] Fehler bei Datenbank-Initialisierung: {}".format(e))
        sys.exit(1)
    
    # YOLO Model prüfen/herunterladen
    if not args.skip_checks:
        model_size = config.get('person.model_size', 'n')
        download_yolo_model(model_size)
    
    # Server starten
    try:
        start_server(
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers
        )
    except Exception as e:
        logger.error("Server-Start fehlgeschlagen: {}".format(e))
        print("\n[FEHLER] Server konnte nicht gestartet werden: {}".format(e))
        sys.exit(1)


# ========================================
# ENTRY POINT
# ========================================

if __name__ == '__main__':
    main()
