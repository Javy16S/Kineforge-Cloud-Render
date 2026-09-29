#!/usr/bin/env python3
"""
KineForge Cloud Pipeline - YouTube Scheduler Manager
Calcula y persiste las fechas de publicación para YouTube.
Programa los vídeos para publicarse cada 2 días a las 20:30 (horario España - Madrid).
"""

import os
import sys
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

SCHEDULE_FILE = "publish_schedule.json"
REMOTE_SCHEDULE_URL = "https://raw.githubusercontent.com/Javy16S/Kineforge-Cloud-Render/main/publish_schedule.json"

def get_madrid_timezone():
    return ZoneInfo("Europe/Madrid")

def load_schedule_registry(schedule_path=SCHEDULE_FILE):
    """Carga el registro de programación local o remoto."""
    registry = {
        "version": "1.0",
        "timezone": "Europe/Madrid",
        "target_time": "20:30",
        "days_gap": 2,
        "last_scheduled_iso": None,
        "last_scheduled_local": None,
        "scheduled_videos": []
    }

    if os.path.exists(schedule_path):
        try:
            with open(schedule_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    registry.update(loaded)
                    return registry
        except Exception as e:
            print(f"[AVISO] Error al leer {schedule_path} local: {e}")

    # Fallback: intentar descargar desde GitHub main si estamos en runner limpio
    try:
        req = urllib.request.Request(REMOTE_SCHEDULE_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                loaded = json.loads(resp.read().decode('utf-8'))
                if isinstance(loaded, dict):
                    registry.update(loaded)
    except Exception:
        pass

    return registry

def calculate_next_publish_date(registry=None, days_gap=2, target_hour=20, target_minute=30, custom_publish_at=None):
    """
    Calcula la próxima fecha de publicación a +days_gap días a las 20:30 hora peninsular de España.
    Retorna tupla: (publish_at_utc_iso, publish_at_local_str)
    """
    madrid_tz = get_madrid_timezone()
    now_madrid = datetime.now(madrid_tz)

    # 1. Si el usuario especificó una fecha manual en el webhook / CLI
    if custom_publish_at:
        try:
            if "T" in custom_publish_at:
                dt = datetime.fromisoformat(custom_publish_at.replace("Z", "+00:00"))
                dt_madrid = dt.astimezone(madrid_tz)
                dt_utc = dt.astimezone(timezone.utc)
                return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), dt_madrid.strftime("%d/%m/%Y a las %H:%M (%Z)")
        except Exception as e:
            print(f"[AVISO] No se pudo parsear custom_publish_at '{custom_publish_at}': {e}. Usando cálculo automático.")

    if registry is None:
        registry = load_schedule_registry()

    last_iso = registry.get("last_scheduled_iso")
    base_date = None

    if last_iso:
        try:
            last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
            last_madrid = last_dt.astimezone(madrid_tz)
            # Solo sumar sobre la última si todavía está en el futuro
            if last_madrid > now_madrid:
                base_date = last_madrid.date()
        except Exception as e:
            print(f"[AVISO] Error al parsear last_scheduled_iso ({last_iso}): {e}")

    # Si no hay fecha previa futura o es el primer vídeo, empezamos desde hoy + days_gap
    if base_date is None:
        base_date = (now_madrid + timedelta(days=days_gap)).date()
    else:
        base_date = base_date + timedelta(days=days_gap)

    next_madrid = datetime(
        base_date.year, base_date.month, base_date.day,
        target_hour, target_minute, 0,
        tzinfo=madrid_tz
    )
    next_utc = next_madrid.astimezone(timezone.utc)

    utc_iso = next_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    local_str = next_madrid.strftime("%d/%m/%Y a las %H:%M (%Z)")

    return utc_iso, local_str

def record_scheduled_video(video_id, title, story_id, chapter, publish_at_utc, publish_at_local, schedule_path=SCHEDULE_FILE):
    """Guarda en publish_schedule.json el vídeo recién programado para que el siguiente vídeo calcule a partir de este."""
    registry = load_schedule_registry(schedule_path)
    registry["last_scheduled_iso"] = publish_at_utc
    registry["last_scheduled_local"] = publish_at_local

    if "scheduled_videos" not in registry or not isinstance(registry["scheduled_videos"], list):
        registry["scheduled_videos"] = []

    registry["scheduled_videos"].append({
        "story_id": str(story_id),
        "chapter": str(chapter),
        "title": str(title),
        "video_id": str(video_id),
        "publish_at_utc": publish_at_utc,
        "publish_at_local": publish_at_local,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    })

    with open(schedule_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

    try:
        print(f"[OK] Programación registrada en {schedule_path}: {publish_at_local}")
    except Exception:
        pass
    return registry

if __name__ == "__main__":
    reg = load_schedule_registry()
    utc_val, loc_val = calculate_next_publish_date(reg)
    print("Próxima publicación calculada:")
    print("  Local (España):", loc_val)
    print("  UTC (YouTube): ", utc_val)
