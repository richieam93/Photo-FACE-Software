#!/usr/bin/env python3
"""
Migriere crop-Einstellungen aus app/data/settings.json in die DB
"""

import json
from pathlib import Path
from app.config import Config
from app.database import Database

def migrate_crop_settings():
    print("Migriere crop-Einstellungen...")

    # Config laden
    config = Config()
    config.load()

    # DB erstellen
    db = Database(config)
    db.load()

    # Einstellungen aus app/data/settings.json laden
    app_settings_path = Path("app/data/settings.json")
    if app_settings_path.exists():
        with open(app_settings_path, 'r', encoding='utf-8-sig') as f:
            app_settings = json.load(f)

        # Stationen finden (Keys die mit _crop enden oder default_crop)
        for key, settings in app_settings.items():
            if key.endswith('_crop') or key == 'default_crop':
                # Station extrahieren
                if key == 'default_crop':
                    station = 'default'
                    settings_type = 'crop'
                else:
                    station = key.replace('_crop', '')
                    settings_type = 'crop'

                print(f"Migriere {station}/{settings_type}: {settings}")

                # In DB speichern
                db.save_settings(station, settings_type, settings)

        print("Migration abgeschlossen!")

        # DB speichern
        db.save()

        # Datei prüfen
        with open(db.settings_path, 'r', encoding='utf-8-sig') as f:
            db_content = json.load(f)
        print(f"DB content: {db_content}")

    else:
        print("app/data/settings.json nicht gefunden")

if __name__ == "__main__":
    migrate_crop_settings()
