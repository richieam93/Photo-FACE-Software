#!/usr/bin/env python3
"""
Teste DB add_image
"""

from app.config import Config
from app.database import Database

def test_add_image():
    print("Teste add_image...")

    # Config laden
    config = Config()
    config.load()

    # DB erstellen
    db = Database(config)
    db.load()

    # Einfache Test-Daten
    test_data = {
        "filename": "test.jpg",
        "original_path": "/path/test.jpg",
        "processed_path": "",
        "output_path": "/output/test.jpg",
        "timestamp": "2026-01-05T21:41:00",
        "width": 100,
        "height": 100,
        "faces": [],
        "face_count": 0,
        "face_encodings": [],
        "persons": [],
        "person_count": 0,
        "clothing_colors": []
    }

    print(f"Test data: {test_data}")

    # Bild hinzufügen
    try:
        image_id = db.add_image(test_data)
        print(f"✅ Bild hinzugefügt: {image_id}")
    except Exception as e:
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()

    # DB speichern
    db.save()
    print("DB gespeichert")

    # Bilder laden
    images = db.get_all_images()
    print(f"Bilder in DB: {len(images)}")

if __name__ == "__main__":
    test_add_image()
