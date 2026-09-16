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

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

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

def prepare_base_canvas(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """
    Escala la imagen manteniendo relación de aspecto y recortando el sobrante centrado
    (equivalente perfecto a force_original_aspect_ratio=increase, crop=w:h).
    """
    img_h, img_w = img.shape[:2]
    scale = max(target_w / img_w, target_h / img_h)
    new_w = max(target_w, int(round(img_w * scale)))
    new_h = max(target_h, int(round(img_h * scale)))
    
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    resized = cv2.resize(img, (new_w, new_h), interpolation=interp)
    
    start_x = max(0, (new_w - target_w) // 2)
    start_y = max(0, (new_h - target_h) // 2)
    canvas = resized[start_y:start_y + target_h, start_x:start_x + target_w]
    
    if canvas.shape[1] != target_w or canvas.shape[0] != target_h:
        canvas = cv2.resize(canvas, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        
    return canvas

def render_segment_opencv(
    full_asset_path: str,
    zoom: Dict[str, Any],
    dur_frames: int,
    width: int,
    height: int,
    fps: int,
    out_ts: str,
    ffmpeg_bin: str = "ffmpeg"
) -> bool:
    """
    Renderiza Ken Burns con precisión subpíxel flotante mediante OpenCV warpAffine.
    Elimina al 100% el temblor, escalonado y micro-saltos de FFmpeg zoompan.
    """
    try:
        with open(full_asset_path, "rb") as f:
            file_bytes = np.frombuffer(f.read(), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return False

        base_canvas = prepare_base_canvas(img, width, height)

        start = zoom.get("start", {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0})
        end = zoom.get("end", {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0})

        start_w = max(0.01, float(start.get("w", 1.0)))
        end_w = max(0.01, float(end.get("w", 1.0)))
        start_x = float(start.get("x", 0.0))
        end_x = float(end.get("x", 0.0))
        start_y = float(start.get("y", 0.0))
        end_y = float(end.get("y", 0.0))

        ffmpeg_cmd = [
            ffmpeg_bin, "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-frames:v", str(dur_frames),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-f", "mpegts",
            out_ts
        ]

        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        dst_pts = np.float32([[0.0, 0.0], [float(width), 0.0], [0.0, float(height)]])

        for i in range(dur_frames):
            t = i / max(1, dur_frames - 1)
            # Smoothstep easing para un movimiento de cámara suave y cinematográfico
            ease = t * t * (3.0 - 2.0 * t)

            cur_w = start_w + (end_w - start_w) * ease
            cur_x = start_x + (end_x - start_x) * ease
            cur_y = start_y + (end_y - start_y) * ease

            crop_w = cur_w * width
            crop_h = cur_w * height
            crop_x = np.clip(cur_x * width, 0.0, max(0.0, width - crop_w))
            crop_y = np.clip(cur_y * height, 0.0, max(0.0, height - crop_h))

            src_pts = np.float32([
                [crop_x, crop_y],
                [crop_x + crop_w, crop_y],
                [crop_x, crop_y + crop_h]
            ])

            M = cv2.getAffineTransform(src_pts, dst_pts)
            frame = cv2.warpAffine(
                base_canvas,
                M,
                (width, height),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )
            proc.stdin.write(frame.tobytes())

        proc.stdin.close()
        proc.wait()
        return proc.returncode == 0 and os.path.exists(out_ts) and os.path.getsize(out_ts) > 100
    except Exception:
        return False

def build_zoompan_filter(clip: Dict[str, Any], width: int, height: int, fps: int = 30) -> Tuple[str, int]:
    """
    Filtro de respaldo con FFmpeg zoompan en caso de no disponer de OpenCV.
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

    internal_w = width * 2
    internal_h = height * 2

    pre_scale = f"scale={internal_w}:{internal_h}:force_original_aspect_ratio=increase,crop={internal_w}:{internal_h},setsar=1/1"
    zoom_part = f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={dur_frames}:s={internal_w}x{internal_h}:fps={fps}"
    down_scale = f"scale={width}:{height}:flags=lanczos"
    
    vf = f"{pre_scale},{zoom_part},{down_scale},setsar=1/1,format=yuv420p"
    return vf, dur_frames

def render_single_segment(item):
    task_type = item[0]
    if task_type == "opencv":
        _, full_asset_path, zoom, dur_frames, width, height, fps, out_ts, ffmpeg_bin, fallback_cmd = item
        if render_segment_opencv(full_asset_path, zoom, dur_frames, width, height, fps, out_ts, ffmpeg_bin):
            return True
        # Fallback a FFmpeg si falla OpenCV en esta imagen específica
        res = subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0 and os.path.exists(out_ts) and os.path.getsize(out_ts) > 100
    elif task_type == "ffmpeg":
        _, cmd, out_ts = item
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0 and os.path.exists(out_ts) and os.path.getsize(out_ts) > 100
    return False

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
            segment_tasks.append(("ffmpeg", gap_cmd, gap_ts))
            segment_files.append(gap_ts)
            gap_counter += 1

        seg_ts = os.path.join(seg_dir, f"seg_{idx:04d}.ts")
        dur_frames = max(1, int(round(clip_dur * fps)))
        clip_zoom = clip.get("zoom", {})

        zoom_vf, _ = build_zoompan_filter({"duration": clip_dur, "zoom": clip_zoom}, width, height, fps)
        fallback_cmd = [
            ffmpeg_bin, "-y",
            "-i", full_asset_path,
            "-vf", zoom_vf,
            "-frames:v", str(dur_frames),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-f", "mpegts", seg_ts
        ]

        is_video = full_asset_path.lower().endswith((".mp4", ".mov", ".mkv", ".webm"))
        if HAS_OPENCV and not is_video:
            segment_tasks.append(("opencv", full_asset_path, clip_zoom, dur_frames, width, height, fps, seg_ts, ffmpeg_bin, fallback_cmd))
        else:
            segment_tasks.append(("ffmpeg", fallback_cmd, seg_ts))

        segment_files.append(seg_ts)
        current_timeline_time = clip_end

    engine_desc = "OpenCV Subpixel Continuous Precision (Butter-Smooth)" if HAS_OPENCV else "FFmpeg zoompan (Fallback)"
    print(f"\n🎬 Renderizando {len(segment_tasks)} segmentos de vídeo en paralelo ({engine_desc})...")
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
            final_inputs.extend(["-i", full_music])
            audio_inputs.append(f"[{input_idx}:a]")
            input_idx += 1

    filter_graph = ""
    if len(audio_inputs) > 1:
        # audio_inputs[0] = voz maestra TTS
        # audio_inputs[1] = musica de fondo
        music_vol = float(manifest.get("musicVolume", 0.20))
        filter_graph = (
            f"{audio_inputs[0]}volume=1.0[v_voice];"
            f"{audio_inputs[1]}volume={music_vol:.3f}[v_music];"
            f"[v_voice][v_music]amix=inputs=2:duration=first:dropout_transition=2[a_out]"
        )
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
