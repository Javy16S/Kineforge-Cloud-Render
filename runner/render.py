#!/usr/bin/env python3
"""
KineForge Cloud Pipeline - Industrial Chunked FFmpeg Renderer
Renderiza proyectos KineForge a video MP4 (H.264 / AAC) con arquitectura segmentada ultra rápida,
inmune a límites de memoria RAM (cero OOM) y con paralelismo nativo en CPU.
"""

import os
import sys
import json
import argparse
import subprocess
import time
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

RESOLUTION_MAP = {
    '16:9': {'width': 1920, 'height': 1080},
    '9:16': {'width': 1080, 'height': 1920},
}

def parse_args():
    parser = argparse.ArgumentParser(description="KineForge Industrial Cloud FFmpeg Renderer")
    parser.add_argument("--manifest", required=True, help="Ruta al archivo manifest.json del proyecto")
    parser.add_argument("--assets", required=True, help="Ruta al directorio de assets")
    parser.add_argument("--output", required=True, help="Ruta del archivo MP4 de salida")
    parser.add_argument("--ffmpeg-bin", default="ffmpeg", help="Binario de FFmpeg a usar")
    return parser.parse_args()

def build_zoompan_filter(clip: Dict[str, Any], width: int, height: int, fps: int = 30) -> Tuple[str, int]:
    """
    Construye el filtro Ken Burns con la fórmula oficial de KineForge:
    1. Pre-escalado inteligente a 16:9 (force_original_aspect_ratio=increase,crop)
    2. Clamp estricto max(0, min(iw-iw/zoom, ...)) para evitar bordes cortados
    3. Interpolación suave de zoom y encuadre
    """
    dur_frames = max(1, int(float(clip.get("duration", 5.0)) * fps))
    zoom = clip.get("zoom", {})
    start = zoom.get("start", {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0})
    end = zoom.get("end", {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0})

    start_w = max(0.01, float(start.get("w", 1.0)))
    end_w = max(0.01, float(end.get("w", 1.0)))
    start_x = float(start.get("x", 0.0))
    end_x = float(end.get("x", 0.0))
    start_y = float(start.get("y", 0.0))
    end_y = float(end.get("y", 0.0))

    progress = f"(on/{dur_frames})"
    w_expr = f"({start_w:.4f}+({end_w - start_w:.4f})*{progress})"
    z_expr = f"(1/max(0.01\\,{w_expr}))"

    x_offset = f"({start_x:.4f}+({end_x - start_x:.4f})*{progress})"
    y_offset = f"({start_y:.4f}+({end_y - start_y:.4f})*{progress})"

    x_expr = f"max(0\\,min(iw-iw/zoom\\,{x_offset}*iw))"
    y_expr = f"max(0\\,min(ih-ih/zoom\\,{y_offset}*ih))"

    # Pre-scale a 16:9 exacto para que zoompan nunca distorsione ni corte
    pre_scale = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1/1"
    zoom_part = f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={dur_frames}:s={width}x{height}:fps={fps}"
    
    vf = f"{pre_scale},{zoom_part},setsar=1/1,format=yuv420p"
    return vf, dur_frames

def render_single_segment(item):
    cmd, out_ts = item
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and os.path.exists(out_ts) and os.path.getsize(out_ts) > 100

def render_project(manifest_path: str, assets_dir: str, output_path: str, ffmpeg_bin: str = "ffmpeg"):
    start_time = time.time()
    print("==================================================")
    print("🚀 KineForge Cloud Industrial Renderer v3.0")
    print(f"Manifest: {manifest_path}")
    print(f"Assets:   {assets_dir}")
    print(f"Output:   {output_path}")
    print("==================================================")

    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"No se encontró el manifest en {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    aspect_ratio = manifest.get("aspectRatio", "16:9")
    res = RESOLUTION_MAP.get(aspect_ratio, RESOLUTION_MAP["16:9"])
    width = res["width"]
    height = res["height"]
    fps = manifest.get("fps", 30)

    clips = sorted(manifest.get("clips", []), key=lambda c: float(c.get("audioIn", 0.0)))
    audio_path = manifest.get("audioFile")
    music_path = manifest.get("musicFile")
    subtitle_file = manifest.get("subtitleFile")

    total_duration = manifest.get("duration", 0.0)
    if total_duration <= 0 and clips:
        total_duration = max(float(c.get("audioOut", c.get("timeEnd", 0))) for c in clips)

    print(f"📊 Duración total: {total_duration:.2f}s | Resolución: {width}x{height} ({aspect_ratio}) @ {fps}fps")

    out_dir = os.path.dirname(os.path.abspath(output_path))
    seg_dir = os.path.join(out_dir, f"render_segments_{int(time.time())}")
    if os.path.exists(seg_dir):
        shutil.rmtree(seg_dir)
    os.makedirs(seg_dir, exist_ok=True)

    segment_tasks = []
    segment_files = []

    current_timeline_time = 0.0
    gap_counter = 0

    for idx, clip in enumerate(clips):
        filename = clip.get("asset") or clip.get("resource")
        if not filename:
            continue
        full_asset_path = os.path.join(assets_dir, os.path.basename(filename))
        if not os.path.exists(full_asset_path):
            print(f"⚠️ Aviso: Asset no encontrado: {full_asset_path}. Omitiendo clip {idx}.")
            continue

        clip_start = float(clip.get("audioIn", clip.get("timeStart", 0.0)))
        clip_end = float(clip.get("audioOut", clip.get("timeEnd", clip_start + 5.0)))
        clip_dur = max(0.1, clip_end - clip_start)

        # Gap de negro si hay salto
        if clip_start > current_timeline_time + 0.05:
            gap_dur = clip_start - current_timeline_time
            gap_frames = max(1, int(gap_dur * fps))
            gap_ts = os.path.join(seg_dir, f"gap_{gap_counter:04d}.ts")
            gap_cmd = [
                ffmpeg_bin, "-y",
                "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}",
                "-vf", "setsar=1/1,format=yuv420p",
                "-frames:v", str(gap_frames),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                "-f", "mpegts", gap_ts
            ]
            segment_tasks.append((gap_cmd, gap_ts))
            segment_files.append(gap_ts)
            gap_counter += 1

        seg_ts = os.path.join(seg_dir, f"seg_{idx:04d}.ts")
        zoom_vf, dur_frames = build_zoompan_filter({"duration": clip_dur, "zoom": clip.get("zoom", {})}, width, height, fps)
        cmd = [
            ffmpeg_bin, "-y",
            "-i", full_asset_path,
            "-vf", zoom_vf,
            "-frames:v", str(dur_frames),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-f", "mpegts", seg_ts
        ]
        segment_tasks.append((cmd, seg_ts))
        segment_files.append(seg_ts)

        current_timeline_time = clip_end

    print(f"\n🎬 Renderizando {len(segment_tasks)} segmentos de vídeo en paralelo (2 hilos CPU)...")
    t0 = time.time()
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(render_single_segment, segment_tasks))

    failed_count = len(results) - sum(results)
    if failed_count > 0:
        print(f"⚠️ Atención: {failed_count} segmentos no se pudieron renderizar.")
    else:
        print(f"✅ Todos los segmentos renderizados con éxito en {time.time() - t0:.2f}s")

    # Crear lista concat con rutas absolutas
    concat_list_file = os.path.join(seg_dir, "concat_list.txt")
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for sf in segment_files:
            abs_p = os.path.abspath(sf).replace("\\", "/")
            f.write(f"file '{abs_p}'\n")

    # Mux final de video concatenado + audio + música
    print("\n🎧 Mezclando audio y ensamblando vídeo final MP4...")
    
    final_inputs = [
        ffmpeg_bin, "-y",
        "-f", "concat", "-safe", "0", "-i", concat_list_file
    ]
    input_idx = 1
    audio_inputs = []

    if audio_path:
        full_audio = os.path.join(assets_dir, os.path.basename(audio_path))
        if os.path.exists(full_audio):
            final_inputs.extend(["-i", full_audio])
            audio_inputs.append(f"[{input_idx}:a]")
            input_idx += 1

    if music_path:
        full_music = os.path.join(assets_dir, os.path.basename(music_path))
        if os.path.exists(full_music):
            music_vol = manifest.get("musicVolume", 0.12)
            final_inputs.extend(["-i", full_music])
            audio_inputs.append(f"[{input_idx}:a]")
            input_idx += 1

    filter_graph = ""
    if len(audio_inputs) > 1:
        mix = "".join(audio_inputs)
        filter_graph = f"{mix}amix=inputs={len(audio_inputs)}:duration=longest:dropout_transition=2[a_out]"
        audio_map = "[a_out]"
    elif len(audio_inputs) == 1:
        audio_map = audio_inputs[0]
    else:
        final_inputs.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"])
        audio_map = f"[{input_idx}:a]"

    final_cmd = final_inputs
    if filter_graph:
        final_cmd.extend(["-filter_complex", filter_graph])
        final_cmd.extend(["-map", "0:v", "-map", audio_map])
    else:
        final_cmd.extend(["-map", "0:v", "-map", audio_map])

    final_cmd.extend([
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ])

    res = subprocess.run(final_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    
    # Limpiar temporales
    try:
        shutil.rmtree(seg_dir)
    except:
        pass

    total_time = time.time() - start_time
    if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"\n🎉 ¡VÍDEO COMPLETO RENDERIZADO EN {total_time:.2f}s ({total_time/60:.1f} min)!")
        print(f"📦 Archivo final: {output_path} ({file_size_mb:.2f} MB)")
        return True
    else:
        print(f"❌ Error durante el ensamblado final MP4:")
        print(res.stderr[-2000:] if res.stderr else "Error desconocido")
        sys.exit(1)

if __name__ == "__main__":
    args = parse_args()
    render_project(args.manifest, args.assets, args.output, args.ffmpeg_bin)
