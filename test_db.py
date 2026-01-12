#!/usr/bin/env python3
"""
Test script für Datenbank
"""

from app.config import Config
from app.database import Database
import json

def test_db():
    print("Teste Datenbank...")

    # Config laden
    config = Config()
    config.load()
    print(f"Config root_dir: {config.root_dir}")

    # DB erstellen
    db = Database(config)
    print(f"DB settings_path: {db.settings_path}")

    # Laden
    db.load()
    print(f"Geladene settings: {db.settings}")

    # Test data
    test_data = {"model": "cnn", "test": True}
    print(f"Test data: {test_data}")

    # Speichern
    success = db.save_settings("default", "face", test_data)
    print(f"Save success: {success}")
    print(f"Settings nach save: {db.settings}")

    # Datei prüfen
    with open(db.settings_path, 'r', encoding='utf-8-sig') as f:
        content = json.load(f)
    print(f"Datei content: {content}")

if __name__ == "__main__":
    test_db()
