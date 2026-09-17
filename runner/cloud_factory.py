#!/usr/bin/env python3
"""
KineForge Cloud Pipeline - Autonomous End-to-End Cloud Factory
Ejecuta la producción 100% autónoma en la nube (Zero-PC):
1. Descarga guion de Google Sheets
2. Genera TTS con Edge-TTS (con voces de personajes)
3. Monta timeline dinámico (cortes de 4s, Ken Burns KineForge y música)
4. Renderiza MP4 con FFmpeg
5. Sube a YouTube con subtítulos y miniatura
"""

import os
import sys
import json
import re
import csv
import io
import time
import shutil
import asyncio
import argparse
import subprocess
import urllib.request
import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from render import render_project
from upload_youtube import get_authenticated_service, upload_video_resumable

try:
    from voice_director import resolve_character_voice, CHARACTER_REGISTRY, FISH_CATALOG
except ImportError:
    try:
        from runner.voice_director import resolve_character_voice, CHARACTER_REGISTRY, FISH_CATALOG
    except ImportError:
        resolve_character_voice = None
        CHARACTER_REGISTRY = {}
        FISH_CATALOG = {}

SHEETS_CSV_URL = "https://docs.google.com/spreadsheets/d/14G4pyQLz6jGe8AW1yyU8KV4JHy1LmpF78-w1Riq3i2E/export?format=csv"

VOICE_MAP = {
    "Narrador": {"voice": "es-ES-AlvaroNeural", "rate": "-2%", "pitch": "-6Hz"},
    "Goku": {"voice": "es-MX-JorgeNeural", "rate": "+2%", "pitch": "-1Hz"},
    "Vegeta": {"voice": "es-MX-JorgeNeural", "rate": "-1%", "pitch": "-7Hz"},
    "Gohan": {"voice": "es-MX-JorgeNeural", "rate": "+1%", "pitch": "+1Hz"},
    "Piccolo": {"voice": "es-ES-AlvaroNeural", "rate": "-3%", "pitch": "-12Hz"},
    "Broly": {"voice": "es-ES-AlvaroNeural", "rate": "-4%", "pitch": "-14Hz"},
    "Trunks": {"voice": "es-MX-JorgeNeural", "rate": "+0%", "pitch": "+0Hz"},
    "Freezer": {"voice": "es-ES-AlvaroNeural", "rate": "-2%", "pitch": "+7Hz"},
    "Cell": {"voice": "es-ES-AlvaroNeural", "rate": "-2%", "pitch": "-8Hz"},
    "Majin_Buu": {"voice": "es-MX-JorgeNeural", "rate": "+6%", "pitch": "+12Hz"},
    "Bills_Beerus": {"voice": "es-ES-AlvaroNeural", "rate": "-4%", "pitch": "-4Hz"},
    "Whis": {"voice": "es-ES-AlvaroNeural", "rate": "+0%", "pitch": "+10Hz"},
    "Krilin": {"voice": "es-MX-JorgeNeural", "rate": "+4%", "pitch": "+6Hz"},
    "Muten_Roshi": {"voice": "es-ES-AlvaroNeural", "rate": "-6%", "pitch": "-8Hz"},
    "Mr_Satan": {"voice": "es-MX-JorgeNeural", "rate": "+5%", "pitch": "-2Hz"},
    "Bulma": {"voice": "es-MX-DaliaNeural", "rate": "+2%", "pitch": "+2Hz"},
    "Androide_18": {"voice": "es-MX-DaliaNeural", "rate": "-2%", "pitch": "-3Hz"},
    "Androide_17": {"voice": "es-ES-AlvaroNeural", "rate": "+0%", "pitch": "+0Hz"},
    "Dende": {"voice": "es-ES-AlvaroNeural", "rate": "+4%", "pitch": "+6Hz"},
    "Mister Popo": {"voice": "es-ES-AlvaroNeural", "rate": "-6%", "pitch": "-10Hz"},
    "Luffy": {"voice": "es-MX-JorgeNeural", "rate": "+3%", "pitch": "+2Hz"},
    "Zoro": {"voice": "es-ES-AlvaroNeural", "rate": "-2%", "pitch": "-8Hz"},
    "Sanji": {"voice": "es-ES-AlvaroNeural", "rate": "+1%", "pitch": "-1Hz"},
    "Nami": {"voice": "es-MX-DaliaNeural", "rate": "+2%", "pitch": "+3Hz"},
    "Robin": {"voice": "es-MX-DaliaNeural", "rate": "-2%", "pitch": "-2Hz"},
    "Usopp": {"voice": "es-MX-JorgeNeural", "rate": "+5%", "pitch": "+5Hz"},
    "Chopper": {"voice": "es-MX-DaliaNeural", "rate": "+8%", "pitch": "+10Hz"},
    "Shanks": {"voice": "es-ES-AlvaroNeural", "rate": "-3%", "pitch": "-6Hz"},
    "Imu_Sama": {"voice": "es-ES-AlvaroNeural", "rate": "-4%", "pitch": "-10Hz"},
    "Garp": {"voice": "es-MX-JorgeNeural", "rate": "-2%", "pitch": "-5Hz"},
    "Roger": {"voice": "es-MX-JorgeNeural", "rate": "-1%", "pitch": "-4Hz"}
}

def get_voice_for_char(char_name):
    c_norm = char_name.strip().replace(" ", "_")
    if c_norm in VOICE_MAP:
        return VOICE_MAP[c_norm]
    # Comprobar variantes
    for k, v in VOICE_MAP.items():
        if k.lower() in c_norm.lower() or c_norm.lower() in k.lower():
            return v
    # Si parece femenino
    if any(f in c_norm.lower() for f in ["bulma", "videl", "milk", "chichi", "18", "androide_18", "nami", "robin", "yamato", "hancock"]):
        return {"voice": "es-MX-DaliaNeural", "rate": "+0%", "pitch": "+0Hz"}
    # Por defecto
    return VOICE_MAP.get("Narrador")

# Mapeo de personajes a IDs de modelos de Fish Audio (ej: 32 caracteres hexadecimales de fish.audio/m/<ID>)
FISH_VOICE_MAP = {}

def get_fish_model_id(char_name, default_model=None):
    if resolve_character_voice:
        fid, mode, rvc_m, pitch, role = resolve_character_voice(char_name)
        if fid:
            return fid, mode, rvc_m, pitch, role

    c_norm = char_name.strip().replace(" ", "_")
    if c_norm in FISH_VOICE_MAP:
        return FISH_VOICE_MAP[c_norm], "direct", None, 0, "Personalizado"
    for k, v in FISH_VOICE_MAP.items():
        if k.lower() in c_norm.lower() or c_norm.lower() in k.lower():
            return v, "direct", None, 0, "Personalizado"
    return default_model, "direct", None, 0, "Default"

KEN_BURNS_PRESETS = [
    {"start": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}, "end": {"x": 0.04, "y": 0.04, "w": 0.92, "h": 0.92}},
    {"start": {"x": 0.04, "y": 0.04, "w": 0.92, "h": 0.92}, "end": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}},
    {"start": {"x": 0.06, "y": 0.02, "w": 0.94, "h": 0.94}, "end": {"x": 0.0, "y": 0.02, "w": 0.94, "h": 0.94}},
    {"start": {"x": 0.0, "y": 0.02, "w": 0.94, "h": 0.94}, "end": {"x": 0.06, "y": 0.02, "w": 0.94, "h": 0.94}},
    {"start": {"x": 0.02, "y": 0.02, "w": 0.96, "h": 0.96}, "end": {"x": 0.05, "y": 0.05, "w": 0.90, "h": 0.90}}
]

def parse_args():
    parser = argparse.ArgumentParser(description="KineForge Autonomous Cloud Factory")
    parser.add_argument("--history-index", type=int, default=0, help="Índice de la historia en Google Sheets (0 = primera)")
    parser.add_argument("--chapter-num", type=int, default=1, help="Número de capítulo a producir (1..5)")
    parser.add_argument("--work-dir", default="/tmp/kineforge_factory", help="Directorio temporal de trabajo")
    parser.add_argument("--output-video", default="/tmp/final_video.mp4", help="Ruta del video final")
    parser.add_argument("--dry-run", action="store_true", help="Simular subida a YouTube sin consumir cuota")
    parser.add_argument("--music-volume", type=float, default=0.20, help="Volumen de la música de fondo (default: 0.20 = presencia destacada para banda sonora anime)")
    parser.add_argument("--assets-dir", default=None, help="Ruta a imágenes/assets (ej: E:\\Dataset_Dragon_Ball\\Ordered Images)")
    parser.add_argument("--music-dir", default=None, help="Ruta a carpeta de música (ej: E:\\Dataset_Dragon_Ball\\Music)")
    parser.add_argument("--fish-api-key", default=None, help="API Key de Fish Audio (o variable FISH_API_KEY)")
    parser.add_argument("--fish-default-model-id", default=None, help="ID de modelo por defecto de Fish Audio (o variable FISH_DEFAULT_MODEL_ID)")
    return parser.parse_args()

def split_text_into_dynamic_cuts(text, target_words=10):
    clauses = [c.strip() for c in re.split(r'[,;.!?]+\s*', text) if c.strip()]
    segments = []
    curr = []
    for c in clauses:
        curr.append(c)
        count = sum(len(x.split()) for x in curr)
        if count >= target_words:
            segments.append(', '.join(curr) + '.')
            curr = []
    if curr:
        if segments and sum(len(x.split()) for x in curr) < 5:
            segments[-1] = segments[-1][:-1] + ', ' + ', '.join(curr) + '.'
        else:
            segments.append(', '.join(curr) + '.')
    return segments

def parse_script_with_dynamic_pacing(guion_text):
    paragraphs = [p.strip() for p in guion_text.split("\n") if p.strip()]
    atomic_cuts = []
    
    # Expresión regular: Soporta "Personaje (Fase, Emoción): texto", "Personaje (Emoción): texto", "Narrador [Escenario]: texto", "Narrador: texto"
    pat = re.compile(r'^(?:[-—]\s*)?([A-Za-z0-9_ñÑáéíóúÁÉÍÓÚ\s]+?)(?:\s*\(([^)]+)\))?(?:\s*\[([^\]]+)\])?\s*:\s*(.+)$')
    
    for p in paragraphs:
        m = pat.match(p)
        if m:
            char_raw = m.group(1).strip()
            meta_paren = m.group(2).strip() if m.group(2) else None
            meta_bracket = m.group(3).strip() if m.group(3) else None
            speech = m.group(4).strip()
            is_dialogue = (char_raw.lower() != "narrador")
            char = "Narrador" if not is_dialogue else char_raw
            sub_cuts = split_text_into_dynamic_cuts(speech, target_words=10)
            for s in sub_cuts:
                atomic_cuts.append({
                    "character": char,
                    "text": s,
                    "meta_paren": meta_paren,
                    "meta_bracket": meta_bracket,
                    "is_dialogue": is_dialogue
                })
        else:
            p_clean = p.lstrip("—- ").strip()
            sub_cuts = split_text_into_dynamic_cuts(p_clean, target_words=10)
            for s in sub_cuts:
                atomic_cuts.append({
                    "character": "Narrador",
                    "text": s,
                    "meta_paren": None,
                    "meta_bracket": None,
                    "is_dialogue": False
                })
    return atomic_cuts

def get_audio_duration(file_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except:
        return 0.0

async def main():
    args = parse_args()
    print("==================================================")
    print("🌟 KINEFORGE AUTONOMOUS CLOUD FACTORY v1.0")
    print(f"Capítulo: {args.chapter_num} | WorkDir: {args.work_dir}")
    print("==================================================")

    os.makedirs(args.work_dir, exist_ok=True)
    assets_dir = os.path.join(args.work_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    tts_dir = os.path.join(args.work_dir, "tts")
    os.makedirs(tts_dir, exist_ok=True)

    # 1. Descargar Google Sheets
    print("\n📥 Descargando guion en vivo desde Google Sheets...")
    req = urllib.request.Request(SHEETS_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
    csv_content = urllib.request.urlopen(req).read().decode('utf-8')
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)

    if args.history_index >= len(rows):
        raise IndexError(f"Índice de historia {args.history_index} fuera de rango (total {len(rows)})")

    story_row = rows[args.history_index]
    sheet_title = story_row.get('TÍTULO DEL VIDEO', 'Goku Encerrado Mil Años')
    
    chapter_arg = str(args.chapter_num).strip().lower()
    if chapter_arg in ["full", "completo", "0", "pelicula"]:
        is_full_movie = True
        cap_parts = []
        for c_idx in range(1, 6):
            p_txt = story_row.get(f'CAPÍTULO {c_idx}', '').strip()
            if p_txt:
                cap_parts.append(p_txt)
        cap_text = "\n\n".join(cap_parts)
        display_title = f"{sheet_title} | PELÍCULA COMPLETA (Capítulos 1 al 5)"
    else:
        is_full_movie = False
        cap_text = story_row.get(f'CAPÍTULO {args.chapter_num}', '').strip()
        display_title = f"{sheet_title} | Capítulo {args.chapter_num}"

    if not cap_text:
        raise ValueError(f"No se encontró texto para el CAPÍTULO {args.chapter_num} en la fila seleccionada.")

    print(f"📖 Título: {display_title}")
    print(f"   Palabras: {len(cap_text.split()):,} | Caracteres: {len(cap_text):,}")

    # 2. Parsear en cortes dinámicos (3-5 segundos)
    atomic_cuts = parse_script_with_dynamic_pacing(cap_text)
    print(f"✂️ Cortes atómicos generados: {len(atomic_cuts)} frases individuales")

    # 3. Generación de Voces Cinemáticas (Fish Audio SOTA con fallback garantizado a Edge-TTS)
    fish_api_key = (args.fish_api_key or os.environ.get("FISH_API_KEY") or "").strip()
    fish_default_model = (args.fish_default_model_id or os.environ.get("FISH_DEFAULT_MODEL_ID") or "").strip() or None

    # Cargar mapa de voces personalizado si existe fish_voices.json
    for possible_json in ["fish_voices.json", os.path.join(os.path.dirname(__file__), "fish_voices.json")]:
        if os.path.exists(possible_json):
            try:
                with open(possible_json, "r", encoding="utf-8") as fv_f:
                    custom_fish = json.load(fv_f)
                    FISH_VOICE_MAP.update(custom_fish)
                    print(f"🐟 Cargadas {len(custom_fish)} voces personalizadas de Fish Audio desde {possible_json}")
            except Exception as e:
                print(f"⚠️ Error leyendo {possible_json}: {e}")

    # Inicializar cliente Fish Audio si hay clave
    fish_session = None
    if fish_api_key:
        try:
            from fish_audio_sdk import Session, TTSRequest
            fish_session = Session(fish_api_key)
            print("🐟 Fish Audio SOTA activado (Emoción, respiración y entonación humana natural)")
            if fish_default_model:
                print(f"   Modelo por defecto: {fish_default_model}")
            if FISH_VOICE_MAP:
                print(f"   Modelos mapeados: {list(FISH_VOICE_MAP.keys())}")
        except Exception as e:
            print(f"⚠️ No se pudo inicializar fish_audio_sdk: {e}. Se usará Edge-TTS.")
            fish_session = None
    else:
        print("\n🎙️ Generando locuciones con Edge-TTS (Configura FISH_API_KEY en Secrets para calidad Cine)...")

    import edge_tts
    sem = asyncio.Semaphore(5)
    fish_backend = (os.environ.get("FISH_BACKEND") or "s2.1-pro-free").strip()

    def _synthesize_fish_sync(session, req, out_path, api_key=None, ref_id=None):
        """Sintetiza usando el backend gratuito s2.1-pro-free (sin cuota de pago)"""
        try:
            with open(out_path, "wb") as f:
                for chunk in session.tts(req, backend=fish_backend):
                    f.write(chunk)
            if os.path.exists(out_path) and os.path.getsize(out_path) >= 200:
                return
        except Exception as err:
            # Si el SDK falla o da 402 Payment Required, usar llamada directa HTTP con cabecera model: s2.1-pro-free
            if api_key:
                try:
                    import requests as http_req
                    payload = {
                        "text": req.text,
                        "format": "mp3",
                        "sample_rate": 44100
                    }
                    if ref_id:
                        payload["reference_id"] = ref_id
                    
                    resp = http_req.post(
                        "https://api.fish.audio/v1/tts",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "model": "s2.1-pro-free"
                        },
                        json=payload,
                        timeout=30
                    )
                    if resp.status_code == 200 and len(resp.content) >= 200:
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        return
                    else:
                        raise Exception(f"HTTP {resp.status_code}: {resp.text[:100]}")
                except Exception as http_err:
                    raise Exception(f"SDK err: {err} | HTTP err: {http_err}")
            raise err

    def _apply_rvc_if_available(audio_path, rvc_model_name, pitch_shift=0):
        """Aplica RVC al audio sintetizado si el modelo .pth está disponible localmente o en la nube"""
        if not rvc_model_name:
            return False
        
        # Buscar modelo .pth en posibles rutas
        model_candidates = [
            f"resources/models/rvc/{rvc_model_name}.pth",
            f"models/rvc/{rvc_model_name}.pth",
            f"rvc_models/{rvc_model_name}.pth",
            os.path.join(os.path.dirname(__file__), "..", "resources", "models", "rvc", f"{rvc_model_name}.pth")
        ]
        model_path = None
        for cand in model_candidates:
            if os.path.exists(cand):
                model_path = os.path.abspath(cand)
                break
                
        if not model_path:
            return False
            
        try:
            import torch
            from rvc_python.infer import RVCInference
            device = "cuda" if torch.cuda.is_available() else "cpu"
            rvc_engine = RVCInference(device=device)
            temp_rvc_out = audio_path.replace(".mp3", "_rvc.wav")
            rvc_engine.infer_file(
                input_path=audio_path,
                model_path=model_path,
                output_path=temp_rvc_out,
                f0_up_key=pitch_shift
            )
            if os.path.exists(temp_rvc_out) and os.path.getsize(temp_rvc_out) > 200:
                # Convertir de vuelta a MP3 48kHz
                subprocess.run(["ffmpeg", "-y", "-i", temp_rvc_out, "-ar", "48000", "-b:a", "192k", audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try: os.remove(temp_rvc_out)
                except: pass
                return True
        except Exception as e:
            print(f"    ⚠️ RVC post-processing no disponible ({e}). Se mantiene audio Fish Audio original.")
        return False

    async def gen_cut(idx, cut):
        async with sem:
            char = cut["character"]
            text = cut["text"]
            out_file = os.path.join(tts_dir, f"cut_{idx:04d}_{char}.mp3")
            
            if not os.path.exists(out_file) or os.path.getsize(out_file) < 200:
                generated = False
                ref_id, mode, rvc_model, pitch, role = get_fish_model_id(char, default_model=fish_default_model)

                # Intentar primero con Fish Audio si está disponible y hay un modelo asignado
                if fish_session and ref_id:
                    try:
                        req = TTSRequest(
                            text=text,
                            reference_id=ref_id,
                            format="mp3",
                            sample_rate=44100,
                            latency="balanced"
                        )
                        await asyncio.to_thread(_synthesize_fish_sync, fish_session, req, out_file, api_key=fish_api_key, ref_id=ref_id)
                        if os.path.exists(out_file) and os.path.getsize(out_file) >= 200:
                            generated = True
                            
                            # Si el personaje está configurado para RVC, intentar aplicar el timbre del actor
                            applied_rvc = False
                            if mode == "rvc" and rvc_model:
                                applied_rvc = await asyncio.to_thread(_apply_rvc_if_available, out_file, rvc_model, pitch)
                                
                            if applied_rvc:
                                print(f"  🎭 [Fish Audio + RVC: {rvc_model}] ({char} - {role}): {text[:35]}...")
                            else:
                                print(f"  ✨ [Fish Audio Directo] ({char} - {role}): {text[:35]}...")
                    except Exception as e:
                        print(f"  ⚠️ [Fish Audio falló para {char}: {e}]. Conmutando a Edge-TTS...")
                        if os.path.exists(out_file):
                            try:
                                os.remove(out_file)
                            except:
                                pass

                # Fallback garantizado a Edge-TTS
                if not generated:
                    cfg = get_voice_for_char(char)
                    comm = edge_tts.Communicate(text, cfg["voice"], rate=cfg["rate"], pitch=cfg["pitch"])
                    await comm.save(out_file)
                    print(f"  🎙️ [Edge-TTS] ({char}): {text[:35]}...")

            dur = get_audio_duration(out_file)
            return {"idx": idx, "character": char, "text": text, "file": out_file, "duration": dur}

    tasks = [gen_cut(i, c) for i, c in enumerate(atomic_cuts)]
    audio_segments = await asyncio.gather(*tasks)
    audio_segments = sorted(audio_segments, key=lambda x: x["idx"])
    print(f"✅ {len(audio_segments)} audios generados.")

    # 4. Master Audio con 4.0s de intro Zorojin y 3.0s de Outro suave
    silence_4s = os.path.join(tts_dir, "silence_4s.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "4.0", silence_4s], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    silence_4s_esc = os.path.abspath(silence_4s).replace("\\", "/")

    silence_3s_outro = os.path.join(tts_dir, "silence_3s_outro.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "3.0", silence_3s_outro], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    silence_3s_outro_esc = os.path.abspath(silence_3s_outro).replace("\\", "/")

    concat_audio_txt = os.path.join(tts_dir, "concat_audio.txt")
    with open(concat_audio_txt, "w", encoding="utf-8") as af_txt:
        af_txt.write(f"file '{silence_4s_esc}'\n")
        for item in audio_segments:
            f_esc = os.path.abspath(item['file']).replace("\\", "/")
            af_txt.write(f"file '{f_esc}'\n")
        af_txt.write(f"file '{silence_3s_outro_esc}'\n")

    master_audio = os.path.join(assets_dir, "audio_master.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_audio_txt, "-ar", "48000", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", master_audio], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    total_duration = get_audio_duration(master_audio)
    print(f"🎧 Master Audio compilado (48kHz Estéreo con Intro y Outro): {total_duration:.2f}s (~{total_duration/60:.1f} min)")

    # 5. Detección Inteligente de Assets y Música (Dataset E:\Dataset_Dragon_Ball o assets_library)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 5.1 Resolver Directorio de Imágenes / Assets
    candidate_assets = [
        args.assets_dir,
        r"E:\Dataset_Dragon_Ball\Ordered Images",
        r"E:\Dataset_Dragon_Ball",
        os.path.join(repo_root, "assets_library"),
        os.path.join(repo_root, "Ordered Images")
    ]
    assets_lib = None
    for cand in candidate_assets:
        if cand and os.path.exists(cand):
            assets_lib = os.path.abspath(cand)
            break
    if not assets_lib:
        assets_lib = os.path.join(repo_root, "assets_library")
    print(f"📁 Directorio de assets: {assets_lib}")

    # 5.2 Resolver Directorio de Música
    candidate_music = [
        args.music_dir,
        r"E:\Dataset_Dragon_Ball\Music",
        os.path.join(assets_lib, "music"),
        os.path.join(assets_lib, "Music"),
        os.path.join(repo_root, "music"),
        os.path.join(repo_root, "Music")
    ]
    music_lib = None
    for cand in candidate_music:
        if cand and os.path.exists(cand):
            music_lib = os.path.abspath(cand)
            break
    if not music_lib:
        music_lib = os.path.join(assets_lib, "music")
    print(f"🎵 Directorio de música: {music_lib}")

    music_files = []
    if os.path.exists(music_lib) and os.path.isdir(music_lib):
        music_files = sorted([os.path.join(music_lib, f) for f in os.listdir(music_lib) if f.lower().endswith(('.mp3', '.wav'))])
    print(f"   {len(music_files)} pistas de música encontradas.")

    # Asegurar que la música cubra la duración total repitiendo o mezclando
    music_playlist = []
    if music_files:
        import random
        rng = random.Random(args.chapter_num + args.history_index * 100)
        shuffled = list(music_files)
        rng.shuffle(shuffled)
        while len(music_playlist) < max(len(shuffled) * 3, 25):
            music_playlist.extend(shuffled)

    music_4s_silence = os.path.join(tts_dir, "music_silence_4s.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "4.0", music_4s_silence], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    music_4s_silence_esc = os.path.abspath(music_4s_silence).replace("\\", "/")
    
    music_concat_txt = os.path.join(tts_dir, "music_concat.txt")
    with open(music_concat_txt, "w", encoding="utf-8") as mf_txt:
        mf_txt.write(f"file '{music_4s_silence_esc}'\n")
        for m in music_playlist:
            m_esc = os.path.abspath(m).replace("\\", "/")
            mf_txt.write(f"file '{m_esc}'\n")

    dest_music_bg = os.path.join(assets_dir, "music_bg.mp3")
    if music_playlist:
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", music_concat_txt, "-t", str(total_duration), "-c:a", "libmp3lame", "-b:a", "192k", dest_music_bg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Silencio de fondo si no hay música
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(total_duration), dest_music_bg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 6. Motor de Dirección Inteligente Basado en Dataset Estructurado (Characters/{Char}/{Phase}/{Emotion} y Scenarios/{Scenario})
    class StatefulDirector:
        def __init__(self, assets_lib_dir):
            self.assets_lib = assets_lib_dir
            
            # Localizar carpetas Characters y Scenarios
            if os.path.exists(os.path.join(assets_lib_dir, "Characters")):
                self.chars_dir = os.path.join(assets_lib_dir, "Characters")
            elif os.path.exists(os.path.join(assets_lib_dir, "characters")):
                self.chars_dir = os.path.join(assets_lib_dir, "characters")
            elif os.path.exists(os.path.join(assets_lib_dir, "Ordered Images", "Characters")):
                self.chars_dir = os.path.join(assets_lib_dir, "Ordered Images", "Characters")
            else:
                self.chars_dir = assets_lib_dir

            if os.path.exists(os.path.join(assets_lib_dir, "Scenarios")):
                self.scens_dir = os.path.join(assets_lib_dir, "Scenarios")
            elif os.path.exists(os.path.join(assets_lib_dir, "scenarios")):
                self.scens_dir = os.path.join(assets_lib_dir, "scenarios")
            elif os.path.exists(os.path.join(assets_lib_dir, "Ordered Images", "Scenarios")):
                self.scens_dir = os.path.join(assets_lib_dir, "Ordered Images", "Scenarios")
            else:
                self.scens_dir = assets_lib_dir
            
            self.pools = {}
            self.current_scenario = "Habitación del Tiempo"
            self.current_char = "Goku"
            self.current_phase = "Base"

            # Indexación dinámica de carpetas de personajes
            self.char_map = {}
            if os.path.exists(self.chars_dir) and os.path.isdir(self.chars_dir):
                for folder in os.listdir(self.chars_dir):
                    f_full = os.path.join(self.chars_dir, folder)
                    if os.path.isdir(f_full):
                        clean_key = self._clean_str(folder)
                        self.char_map[clean_key] = folder

            # Indexación dinámica de carpetas de escenarios
            self.scen_map = {}
            if os.path.exists(self.scens_dir) and os.path.isdir(self.scens_dir):
                for folder in os.listdir(self.scens_dir):
                    f_full = os.path.join(self.scens_dir, folder)
                    if os.path.isdir(f_full):
                        clean_key = self._clean_str(folder)
                        self.scen_map[clean_key] = folder

            # Mapeo de alias comunes
            self.char_aliases = {
                "bills": "billsbeerus",
                "beerus": "billsbeerus",
                "billsbeerus": "billsbeerus",
                "roshi": "mutenroshi",
                "mutenroshi": "mutenroshi",
                "maestroroshi": "mutenroshi",
                "buu": "majinbuu",
                "majinbuu": "majinbuu",
                "mrbuu": "majinbuu",
                "ginyu": "capitanginyu",
                "capitanginyu": "capitanginyu",
                "satan": "mrsatan",
                "mrsatan": "mrsatan",
                "milk": "milkchichi",
                "chichi": "milkchichi",
                "milkchichi": "milkchichi",
                "trunksfuturo": "trunksdelfuturo",
                "trunksdelfuturo": "trunksdelfuturo",
                "a17": "androide17",
                "n17": "androide17",
                "numero17": "androide17",
                "androide17": "androide17",
                "a18": "androide18",
                "n18": "androide18",
                "numero18": "androide18",
                "androide18": "androide18",
                "frieza": "freezer",
                "vegetta": "vegeta"
            }

            self.phase_aliases = {
                "base": "Base",
                "normal": "Base",
                "ssj": "SSJ1",
                "ssj1": "SSJ1",
                "supersaiyan": "SSJ1",
                "supersaiyajin": "SSJ1",
                "ssj2": "SSJ1",
                "ssj3": "SSJ3",
                "god": "SSJGOD",
                "ssjgod": "SSJGOD",
                "dios": "SSJGOD",
                "ssjdios": "SSJGOD",
                "blue": "SSJBLUE",
                "ssjblue": "SSJBLUE",
                "ultrainstinto": "ULTRAINSTINTO",
                "ui": "ULTRAINSTINTO",
                "migattenogokui": "ULTRAINSTINTO"
            }

            self.emotion_aliases = {
                "alegre": "Alegre",
                "feliz": "Alegre",
                "riendo": "Alegre",
                "sonriendo": "Alegre",
                "contento": "Alegre",
                "enfadado": "Enfadado",
                "enojado": "Enfadado",
                "furioso": "Enfadado",
                "furia": "Enfadado",
                "gritando": "Enfadado",
                "agresivo": "Enfadado",
                "triste": "Triste",
                "herido": "Triste",
                "derrotado": "Triste",
                "llorando": "Triste",
                "preocupado": "Triste",
                "neutral": "Neutral",
                "serio": "Neutral",
                "normal": "Neutral",
                "pensativo": "Neutral",
                "calmado": "Neutral"
            }

            self.scen_aliases = {
                "namek": "planetanamek",
                "namekusei": "planetanamek",
                "tierra": "planetatierra",
                "kamehouse": "planetatierra",
                "habitacion": "habitaciondeltiempo",
                "saladeltiempo": "habitaciondeltiempo",
                "espacio": "espacio",
                "universo": "espacio",
                "bills": "planetabills",
                "beerus": "planetabills",
                "zeno": "templozenosama",
                "zenosama": "templozenosama",
                "vegeta": "planetavegetta",
                "vegetta": "planetavegetta",
                "kaioshin": "planetakaioshin",
                "combate": "extras",
                "torneo": "extras",
                "pelea": "extras"
            }

        @staticmethod
        def _clean_str(text):
            import unicodedata
            t = unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8')
            return re.sub(r'[^a-z0-9]', '', t.lower())

        def _get_files(self, dir_path):
            if dir_path not in self.pools:
                files = []
                if os.path.exists(dir_path) and os.path.isdir(dir_path):
                    files = [os.path.join(dir_path, f) for f in sorted(os.listdir(dir_path)) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
                self.pools[dir_path] = {"files": files, "idx": 0}
            return self.pools[dir_path]["files"]

        def _next_image(self, dir_path):
            files = self._get_files(dir_path)
            if not files:
                return None
            pool = self.pools[dir_path]
            img = pool["files"][pool["idx"] % len(pool["files"])]
            pool["idx"] += 1
            return img

        def resolve_character_dir(self, char_raw):
            clean_name = self._clean_str(char_raw)
            # 1. Búsqueda por alias
            if clean_name in self.char_aliases:
                clean_name = self.char_aliases[clean_name]
            # 2. Búsqueda en mapa de carpetas reales
            if clean_name in self.char_map:
                return self.char_map[clean_name]
            # 3. Búsqueda parcial
            for k, folder in self.char_map.items():
                if k in clean_name or clean_name in k:
                    return folder
            return "Goku"

        def get_character_image(self, character, phase="Base", emotion="Neutral"):
            folder_name = self.resolve_character_dir(character)
            
            # Normalizar fase
            clean_phase = self._clean_str(phase)
            mapped_phase = self.phase_aliases.get(clean_phase, phase)
            
            # Normalizar emoción
            clean_emo = self._clean_str(emotion)
            mapped_emo = self.emotion_aliases.get(clean_emo, "Neutral")

            # 1. Búsqueda exacta: Characters/{char}/{phase}/{emotion}/
            exact_dir = os.path.join(self.chars_dir, folder_name, mapped_phase, mapped_emo)
            img = self._next_image(exact_dir)
            if img: return img

            # 2. Fallback a Neutral en misma fase
            fb_neutral = os.path.join(self.chars_dir, folder_name, mapped_phase, "Neutral")
            img = self._next_image(fb_neutral)
            if img: return img

            # 3. Fallback a Base/{emotion}
            fb_base_emo = os.path.join(self.chars_dir, folder_name, "Base", mapped_emo)
            img = self._next_image(fb_base_emo)
            if img: return img

            # 4. Fallback a Base/Neutral
            fb_base_neutral = os.path.join(self.chars_dir, folder_name, "Base", "Neutral")
            img = self._next_image(fb_base_neutral)
            if img: return img

            # 5. Fallback a cualquier imagen dentro de la carpeta del personaje
            char_root = os.path.join(self.chars_dir, folder_name)
            if os.path.exists(char_root):
                all_imgs = [os.path.join(r, f) for r, _, fs in os.walk(char_root) for f in fs if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
                if all_imgs:
                    pool = self.pools.setdefault(char_root, {"files": sorted(all_imgs), "idx": 0})
                    res = pool["files"][pool["idx"] % len(pool["files"])]
                    pool["idx"] += 1
                    return res

            # 6. Fallback de emergencia a Goku Base Neutral
            goku_fb = os.path.join(self.chars_dir, "Goku", "Base", "Neutral")
            img = self._next_image(goku_fb)
            if img: return img
            
            # 7. Si no hay nada, primera imagen que exista en la librería
            for r, _, fs in os.walk(self.assets_lib):
                for f in fs:
                    if f.lower().endswith(('.jpg', '.png')):
                        return os.path.join(r, f)
            return None

        def resolve_scenario_dir(self, scenario_raw):
            clean_scen = self._clean_str(scenario_raw)
            if clean_scen in self.scen_aliases:
                clean_scen = self.scen_aliases[clean_scen]
            if clean_scen in self.scen_map:
                return self.scen_map[clean_scen]
            for k, folder in self.scen_map.items():
                if k in clean_scen or clean_scen in k:
                    return folder
            return "Habitación del Tiempo"

        def get_scenario_image(self, scenario_name=None):
            target = scenario_name or self.current_scenario
            folder_name = self.resolve_scenario_dir(target)
            matched_dir = os.path.join(self.scens_dir, folder_name)

            if os.path.exists(matched_dir):
                img = self._next_image(matched_dir)
                if img:
                    self.current_scenario = folder_name
                    return img

            for fb in ["Planeta Tierra", "Habitación del Tiempo", "Extras"]:
                fb_folder = self.resolve_scenario_dir(fb)
                fb_p = os.path.join(self.scens_dir, fb_folder)
                img = self._next_image(fb_p)
                if img: return img

            return self.get_character_image("Goku", "Base", "Neutral")

        def select_image(self, cut_item, cut_index):
            char = cut_item.get("character", "Narrador")
            meta_tag = cut_item.get("meta_tag") or cut_item.get("meta_paren") or cut_item.get("meta_bracket")
            text = cut_item.get("text", "").lower()

            # Diccionario de detección de personajes en el texto
            char_keywords = {
                "Goku": ["son goku", "goku", "kakarotto", "kakaroto", "sayayin goku", "saiyajin goku"],
                "Vegeta": ["vegeta", "vegetta", "príncipe de los saiyajin", "principe saiyajin", "orgulloso príncipe"],
                "Gohan": ["gohan", "son gohan"],
                "Piccolo": ["piccolo", "piccoro", "namekiano"],
                "Freezer": ["freezer", "frieza", "emperador del mal"],
                "Cell": ["cell", "célula", "celula", "androide perfecto", "bioandroide"],
                "Majin_Buu": ["majin buu", "buu", "majin boo", "monstruo buu"],
                "Bills_Beerus": ["bills", "beerus", "dios de la destrucción", "dios destructor"],
                "Whis": ["whis", "ángel whis", "angel whis"],
                "Krilin": ["krilin", "krillin"],
                "Trunks_del_Futuro": ["trunks del futuro", "trunks joven", "trunks"],
                "Broly": ["broly", "saiyajin legendario"],
                "Dende": ["dende", "kamisama dende"],
                "Bulma": ["bulma"],
                "Androide_17": ["androide 17", "número 17", "numero 17", "a17", "n17"],
                "Androide_18": ["androide 18", "número 18", "numero 18", "a18", "n18"],
                "Muten_Roshi": ["muten roshi", "maestro roshi", "roshi"],
                "Yamcha": ["yamcha"],
                "Tenshinhan": ["tenshinhan", "ten shin han", "tien"],
                "Mr_Satan": ["mr satan", "mr. satan", "míster satan", "mister satan", "satan"],
                "Jiren": ["jiren", "el gris"],
                "Toppo": ["toppo"],
                "Hit": ["hit", "asesino legendario"],
                "Raditz": ["raditz"],
                # One Piece
                "Luffy": ["luffy", "monkey d. luffy", "sombrero de paja", "mugiwara", "nika", "joy boy"],
                "Zoro": ["zoro", "roronoa", "espadachín", "espadachin", "cazador de piratas"],
                "Sanji": ["sanji", "pierna negra", "vinsmoke", "cocinero"],
                "Nami": ["nami", "gata ladrona", "navegante"],
                "Usopp": ["usopp", "sogeking", "god usopp", "tirador"],
                "Chopper": ["chopper", "tony tony", "médico", "medico"],
                "Robin": ["robin", "nico robin", "niña demonio", "arqueóloga", "arqueologa"],
                "Shanks": ["shanks", "el pelirrojo", "akagami"],
                "Imu_Sama": ["imu-sama", "imu sama", "imu", "soberano del mundo", "rey del mundo"],
                "Garp": ["garp", "héroe de la marina", "heroe de la marina", "el puño", "el puno"],
                "Roger": ["roger", "gol d. roger", "rey de los piratas"],
                "Kobe": ["kobe", "koby"],
                "Fujitora": ["fujitora", "issho"],
                "Yamato": ["yamato", "hijo de kaido"]
            }

            # Diccionario de detección de emociones por acciones y gestos
            emotion_keywords = {
                "Enfadado": [
                    "ceño", "frunció", "fruncio", "puño", "puños", "ira", "rabia", "enfado", "furio", "furia", 
                    "grit", "rugi", "apretó", "apreto", "diente", "ataqu", "golp", "arremeti", "fiero", "odio", 
                    "tensión", "tension", "asesin", "estall", "furor", "rabios", "amenaz", "violento"
                ],
                "Alegre": [
                    "sonri", "risa", "sonrisa", "confiad", "burl", "alegr", "feliz", "satisf", "arrogant", 
                    "orgullos", "carcajad", "tranquil", "optimis", "victoria", "celebr"
                ],
                "Triste": [
                    "herid", "dolor", "derrot", "cayó", "cayo", "caer", "jade", "exhaust", "sangr", "lágrim", 
                    "lagrim", "llor", "miedo", "tembl", "aterr", "impotent", "desesper", "preocup", "agoní", 
                    "agonia", "grave", "debilitad", "suelo", "inconsciente", "temor"
                ],
                "Neutral": [
                    "observ", "mir", "analiz", "pensat", "seri", "silenci", "calm", "cruzó los brazos", "cruzo los brazos", 
                    "explic", "sabía", "sabia", "inmóvil", "inmovil", "parado", "quieto", "esper", "atento"
                ]
            }

            # Diccionario de detección de fase por mención visual
            phase_keywords = {
                "GEAR5": ["gear 5", "gear fifth", "marcha 5", "nika", "blanco", "reír", "reir", "tambores de la liberación"],
                "GEAR4": ["gear 4", "gear fourth", "boundman", "snakeman"],
                "GEAR2": ["gear 2", "gear second"],
                "ULTRAINSTINTO": ["ultra instinto", "ultrainstinto", "ui", "platead", "doctrina egoísta", "doctrina egoista"],
                "SSJBLUE": ["ssj blue", "ssjblue", "super saiyajin blue", "azul", "dios azul", "aura azul"],
                "SSJGOD": ["ssj god", "ssjgod", "super saiyajin dios", "dios rojo", "aura roja", "rojiz"],
                "SSJ3": ["ssj 3", "ssj3", "super saiyajin 3", "cabello largo", "melena dorada"],
                "SSJ1": ["super saiyajin", "super saiyan", "ssj 1", "ssj1", "ssj", "dorad", "rubi", "guerrero dorado", "aura dorada"],
                "Base": ["base", "estado base", "cabello negro", "normal"]
            }

            if char == "Narrador":
                # 1. Detectar si el texto menciona explícitamente a un personaje
                detected_char = None
                for ch_name, kws in char_keywords.items():
                    if any(kw in text for kw in kws):
                        detected_char = ch_name
                        break

                # Si no hay mención nominal pero hay pronombres de continuación del personaje activo
                if not detected_char and any(p in text for p in [" su ", " sus ", "él ", "el saiyajin", "el guerrero", "su cuerpo", "su rostro", "sus ojos", "su mirada", "su ki", "su poder", "el pirata", "el capitán", "el capitan", "el espadachín", "el espadachin", "el muchacho", "el joven"]):
                    detected_char = self.current_char

                # 2. Si hay personaje involucrado en la acción descrita:
                if detected_char:
                    # Detectar emoción por acciones y gestos
                    detected_emo = "Neutral"
                    for emo, kws in emotion_keywords.items():
                        if any(kw in text for kw in kws):
                            detected_emo = emo
                            break

                    # Detectar fase por texto o mantener la actual
                    detected_phase = self.current_phase if detected_char == self.current_char else "Base"
                    for ph, kws in phase_keywords.items():
                        if any(kw in text for kw in kws):
                            detected_phase = ph
                            break

                    self.current_char = detected_char
                    self.current_phase = detected_phase
                    return self.get_character_image(detected_char, phase=detected_phase, emotion=detected_emo)

                # 3. Si no hay personaje, comprobar si es escena de combate / explosión / choque
                clash_keywords = ["choque", "colisi", "explosi", "combate", "pelea", "resquebraj", "cráter", "crater", "destrucci", "ondas de choque", "ráfaga", "rafaga", "ki explot", "destello"]
                if any(kw in text for kw in clash_keywords):
                    return self.get_scenario_image("Extras")

                # 4. Si es descripción de entorno / escenario:
                if meta_tag:
                    return self.get_scenario_image(meta_tag)

                # 5. Búsqueda semántica de escenario en texto
                scen_keywords = {
                    "Habitación del Tiempo": ["habitación del tiempo", "puerta", "vacío", "vacio", "blanco", "reloj", "gravedad", "dimensión blanca"],
                    "Planeta Namek": ["namek", "namekusei", "cielo verde", "agua verde", "esferas del dragón"],
                    "Planeta Tierra": ["tierra", "kame house", "montañas", "ciudad", "isla", "cielo azul", "bosque"],
                    "Espacio": ["espacio", "universo", "galaxias", "estrellas", "nave", "vacío cósmico"],
                    "Planeta Bills": ["bills", "árbol", "arbol", "pirámide", "piramide", "whis", "templo de bills"],
                    "Templo Zeno Sama": ["zeno", "zeno sama", "templo zeno", "palacio de zeno"],
                    "Planeta Vegetta": ["planeta vegeta", "planeta vegetta", "reino saiyajin"],
                    "Planeta Kaioshin": ["kaioshin", "mundo supremo", "árbol sagrado", "tierra sagrada"],
                    "Extras": ["destrucción", "combate", "pelea", "explosión", "cráter", "ring", "torneo"]
                }
                for scen, kws in scen_keywords.items():
                    if any(k in text for k in kws):
                        return self.get_scenario_image(scen)

                return self.get_scenario_image()

            else:
                # Es un diálogo directo de personaje
                phase = "Base"
                emotion = "Neutral"
                if meta_tag:
                    parts = [p.strip() for p in meta_tag.split(",")]
                    if len(parts) == 1:
                        p0 = parts[0]
                        clean_p0 = self._clean_str(p0)
                        if clean_p0 in self.emotion_aliases:
                            emotion = self.emotion_aliases[clean_p0]
                        elif clean_p0 in self.phase_aliases:
                            phase = self.phase_aliases[clean_p0]
                        else:
                            emotion = p0
                    elif len(parts) >= 2:
                        phase = parts[0]
                        emotion = parts[1]
                
                # Revisar si en el texto del diálogo hay un fuerte indicio emocional
                if emotion == "Neutral":
                    for emo, kws in emotion_keywords.items():
                        if any(kw in text for kw in kws):
                            emotion = emo
                            break

                self.current_char = char
                self.current_phase = phase
                return self.get_character_image(char, phase=phase, emotion=emotion)

    # 7. Resolución Inteligente de Imagen de Intro Zorojin
    intro_img = None
    intro_candidates = [
        os.path.join(assets_lib, "intro", "Zorojin_Intro.jpg"),
        os.path.join(assets_lib, "intro", "intro.jpg"),
        r"D:\Descargas\Javier\Elementos\Zorojin_Intro.jpg",
        os.path.join(os.path.dirname(assets_lib), "reference_images", "Goku_Base.jpg")
    ]
    for c in intro_candidates:
        if c and os.path.exists(c):
            intro_img = c
            break

    if not intro_img:
        for r, _, fs in os.walk(assets_lib):
            for f in fs:
                if f.lower().endswith(('.jpg', '.png')):
                    intro_img = os.path.join(r, f)
                    break
            if intro_img: break

    director = StatefulDirector(assets_lib)

    manifest_clips = []
    shutil.copy2(intro_img, os.path.join(assets_dir, "img_0000.jpg"))
    manifest_clips.append({
        "id": "intro_zorojin_4s",
        "asset": "img_0000.jpg",
        "audioIn": 0.0,
        "audioOut": 4.0,
        "zoom": {"start": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}, "end": {"x": 0.015, "y": 0.015, "w": 0.97, "h": 0.97}}
    })

    current_t = 4.0
    asset_map = {}
    asset_counter = 1

    for idx, seg in enumerate(audio_segments):
        start_t = current_t
        end_t = current_t + seg["duration"]
        current_t = end_t
        orig_img = director.select_image(seg, idx)
        if orig_img not in asset_map:
            ext = os.path.splitext(orig_img)[1]
            img_name = f"img_{asset_counter:04d}{ext}"
            asset_counter += 1
            shutil.copy2(orig_img, os.path.join(assets_dir, img_name))
            asset_map[orig_img] = img_name
        else:
            img_name = asset_map[orig_img]

        manifest_clips.append({
            "id": f"clip_{idx:04d}",
            "asset": img_name,
            "audioIn": round(start_t, 3),
            "audioOut": round(end_t, 3),
            "zoom": KEN_BURNS_PRESETS[idx % len(KEN_BURNS_PRESETS)]
        })

    # Asegurar que el último clip cubra los 3.0s de outro musical y fundido a negro
    if manifest_clips:
        manifest_clips[-1]["audioOut"] = round(total_duration, 3)

    # Subtítulos SRT
    srt_path = os.path.join(assets_dir, "subtitles.srt")
    def format_srt_time(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(srt_path, "w", encoding="utf-8") as srt_f:
        for idx, clip in enumerate(manifest_clips[1:]):
            srt_f.write(f"{idx+1}\n")
            srt_f.write(f"{format_srt_time(clip['audioIn'])} --> {format_srt_time(clip['audioOut'])}\n")
            srt_f.write(f"{audio_segments[idx]['text']}\n\n")

    manifest = {
        "version": "1.0",
        "aspectRatio": "16:9",
        "duration": total_duration,
        "fps": 30,
        "audioFile": "audio_master.mp3",
        "musicFile": "music_bg.mp3",
        "musicVolume": args.music_volume,
        "clips": manifest_clips
    }
    manifest_file = os.path.join(args.work_dir, "manifest.json")
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    metadata = {
        "title": display_title,
        "description": f"{display_title} producido y renderizado en la nube.\n\n#DragonBall #Goku #AnimeFanfic #Zorojin",
        "tags": ["Dragon Ball", "Goku", "Zorojin", "Habitacion del Tiempo", "Anime Fanfic", "Super Saiyajin", "Pelicula Completa"],
        "categoryId": "1",
        "privacyStatus": "unlisted",
        "madeForKids": False,
        "dryRun": args.dry_run,
        "subtitles": srt_path
    }
    metadata_file = os.path.join(args.work_dir, "metadata.json")
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # 7. Renderizar Video con FFmpeg
    print(f"\n🎬 Renderizando vídeo MP4 final con motor v3.0 ({len(manifest_clips)} clips)...")
    render_project(manifest_file, assets_dir, args.output_video, ffmpeg_bin="ffmpeg")

    # 8. Subir a YouTube
    print("\n🚀 Subiendo a YouTube con subtítulos sincronizados...")
    if args.dry_run:
        print("ℹ️ Modo Dry-Run activo: No se subirá a YouTube.")
    else:
        try:
            youtube = get_authenticated_service()
            upload_video_resumable(youtube, args.output_video, metadata)
        except Exception as e:
            err_msg = str(e)
            if "quotaExceeded" in err_msg or "quota" in err_msg.lower():
                print(f"\n⚠️ [AVISO DE CUOTA] Límite diario de la API de YouTube superado: {e}")
                print("ℹ️ El vídeo se ha renderizado íntegramente y estará disponible en el reproductor Web / Móvil y en Artifacts.")
            else:
                print(f"\n⚠️ [AVISO YOUTUBE] Error en subida a YouTube: {e}")
                print("ℹ️ Continuando con la generación de preview y guardado de artefactos.")

    print("\n🎉 ¡PRODUCCIÓN 100% COMPLETADA CON ÉXITO EN LA NUBE!")

if __name__ == "__main__":
    asyncio.run(main())
