#!/usr/bin/env python3
"""
KineForge Cloud Pipeline - Previews Manifest Manager
Actualiza manifest_previews.json para el reproductor web multidispositivo.
Mantiene el registro de cada historia de forma independiente con sus capítulos (1..5 y full).
"""

import os
import sys
import json
import urllib.request
from datetime import datetime

def update_manifest(info_path, manifest_path="manifest_previews.json", release_tag="previews"):
    # 1. Cargar info del capítulo actual
    with open(info_path, "r", encoding="utf-8") as f:
        info = json.load(f)

    story_id = str(info.get("story_id", "h0"))
    story_title = str(info.get("story_title", "Historia KineForge")).strip()
    chapter = str(info.get("chapter", "1")).strip()
    preview_file = f"preview_{story_id}_cap_{chapter}.mp4"

    # 2. Descargar o cargar manifest existente
    manifest = {"stories": {}, "last_updated": ""}
    
    # Si existe localmente, cargarlo primero
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict) and "stories" in loaded:
                    manifest = loaded
        except Exception as e:
            print(f"Aviso al leer manifest local: {e}")

    # Intentar descargar de GitHub Releases o GitHub Pages para fusionar capítulos
    remote_urls = [
        f"https://github.com/Javy16S/Kineforge-Cloud-Render/releases/download/{release_tag}/manifest_previews.json",
        "https://javy16s.github.io/Kineforge-Cloud-Render/manifest_previews.json"
    ]
    
    for url in remote_urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    remote_manifest = json.loads(resp.read().decode('utf-8'))
                    if isinstance(remote_manifest, dict) and "stories" in remote_manifest:
                        # Fusionar historias remotas con locales
                        for s_id, s_data in remote_manifest["stories"].items():
                            if s_id not in manifest["stories"]:
                                manifest["stories"][s_id] = s_data
                            else:
                                if "chapters" not in manifest["stories"][s_id]:
                                    manifest["stories"][s_id]["chapters"] = {}
                                for c_num, c_data in s_data.get("chapters", {}).items():
                                    manifest["stories"][s_id]["chapters"][c_num] = c_data
                        print(f"Manifest remoto sincronizado desde {url}")
                        break
        except Exception:
            continue

    if "stories" not in manifest or not isinstance(manifest["stories"], dict):
        manifest["stories"] = {}

    # 3. Actualizar la historia actual
    if story_id not in manifest["stories"]:
        manifest["stories"][story_id] = {
            "id": story_id,
            "title": story_title,
            "chapters": {}
        }

    manifest["stories"][story_id]["title"] = story_title
    if "chapters" not in manifest["stories"][story_id]:
        manifest["stories"][story_id]["chapters"] = {}

    manifest["stories"][story_id]["chapters"][chapter] = {
        "file": preview_file,
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }

    manifest["last_story"] = story_id
    manifest["last_chapter"] = chapter
    manifest["last_updated"] = datetime.utcnow().isoformat() + "Z"

    # 4. Guardar archivo local
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    try:
        print(f"[OK] Manifest actualizado para {story_id} [{story_title[:35]}...] - Cap {chapter}")
    except Exception:
        pass
    return manifest

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python update_manifest.py <ruta_a_story_info.json> [ruta_a_manifest.json]")
        sys.exit(1)

    info_file = sys.argv[1]
    out_manifest = sys.argv[2] if len(sys.argv) > 2 else "manifest_previews.json"
    update_manifest(info_file, out_manifest)
