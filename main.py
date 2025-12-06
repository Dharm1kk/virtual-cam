#!/usr/bin/env python3
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import mss
import numpy as np
from PIL import Image

# ---- CONFIG ----
WIDTH = 1280
HEIGHT = 720
FPS = 30

VIRTUAL_CAM = "/dev/video10"   # v4l2loopback device
WEBCAM_DEV = "/dev/video0"     # your integrated cam
OVERLAY_PATH = "overlay.png"   # optional overlay image

# ---- GLOBAL STATE (controlled by input thread) ----
current_mode = "webcam"   # "webcam", "video", "screen", "pattern"
video_path = None
overlay_enabled = False
running = True


def start_ffmpeg():
    """Start ffmpeg process that accepts raw RGB frames on stdin and writes to v4l2."""
    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-video_size", f"{WIDTH}x{HEIGHT}",
        "-framerate", str(FPS),
        "-i", "-",
        "-vf", "format=yuv420p",
        "-f", "v4l2",
        VIRTUAL_CAM,
    ]
    print("[INFO] Starting ffmpeg:", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    if proc.stdin is None:
        print("[ERROR] Could not open ffmpeg stdin")
        sys.exit(1)
    return proc


def load_overlay():
    """Load overlay image (RGBA) and prepare numpy arrays for blending."""
    path = Path(OVERLAY_PATH)
    if not path.exists():
        print(f"[WARN] Overlay image '{OVERLAY_PATH}' not found. Overlay disabled.")
        return None, None

    img = Image.open(path).convert("RGBA")

    # scale overlay to ~25% of width
    target_w = WIDTH // 4
    scale = target_w / img.width
    target_h = int(img.height * scale)
    img = img.resize((target_w, target_h), Image.LANCZOS)

    overlay_rgba = np.array(img, dtype=np.uint8)
    overlay_rgb = overlay_rgba[:, :, :3]
    alpha = overlay_rgba[:, :, 3:4] / 255.0  # (h, w, 1) in [0,1]

    return overlay_rgb, alpha


def apply_overlay(frame_rgb, overlay_rgb, alpha):
    """Blend overlay into bottom-right corner of frame."""
    if overlay_rgb is None or alpha is None:
        return frame_rgb

    oh, ow, _ = overlay_rgb.shape
    fh, fw, _ = frame_rgb.shape

    if oh > fh or ow > fw:
        return frame_rgb  # overlay too big, skip

    # position: bottom-right
    y1 = fh - oh - 10
    x1 = fw - ow - 10
    y2 = y1 + oh
    x2 = x1 + ow

    roi = frame_rgb[y1:y2, x1:x2, :]
    # alpha blend: out = alpha*overlay + (1-alpha)*background
    blended = (alpha * overlay_rgb + (1.0 - alpha) * roi).astype(np.uint8)
    frame_rgb[y1:y2, x1:x2, :] = blended
    return frame_rgb


def input_thread():
    """Thread to listen for user commands while main loop runs."""
    global current_mode, video_path, overlay_enabled, running

    help_text = (
        "\n=== Controls ===\n"
        "1 : Webcam\n"
        "2 : Video file\n"
        "3 : Screen capture\n"
        "4 : Pattern\n"
        "o : Toggle overlay on/off\n"
        "h : Show this help\n"
        "q : Quit\n"
    )
    print(help_text)

    while running:
        try:
            cmd = input("[CMD] ").strip().lower()
        except EOFError:
            break

        if cmd == "1":
            current_mode = "webcam"
            print("[MODE] Webcam")

        elif cmd == "2":
            path = input("Enter video file path: ").strip()
            if path:
                video_path = path
                current_mode = "video"
                print(f"[MODE] Video: {video_path}")
            else:
                print("[WARN] No path entered.")

        elif cmd == "3":
            current_mode = "screen"
            print("[MODE] Screen capture")

        elif cmd == "4":
            current_mode = "pattern"
            print("[MODE] Pattern")

        elif cmd == "o":
            overlay_enabled = not overlay_enabled
            print(f"[OVERLAY] {'ON' if overlay_enabled else 'OFF'}")

        elif cmd == "h":
            print(help_text)

        elif cmd == "q":
            print("[INFO] Quitting...")
            running = False
            break

        else:
            print("[WARN] Unknown command. Press 'h' for help.")


def main():
    global running

    # Start ffmpeg
    ffmpeg_proc = start_ffmpeg()

    # Setup sources
    cap_webcam = cv2.VideoCapture(WEBCAM_DEV)
    cap_video = None
    sct = mss.mss()

    overlay_rgb, overlay_alpha = load_overlay()

    # Start input thread
    t = threading.Thread(target=input_thread, daemon=True)
    t.start()

    frame_index = 0

    try:
        while running:
            t0 = time.time()
            mode = current_mode

            # --- Get frame from current source ---
            if mode == "webcam":
                ret, frame_bgr = cap_webcam.read()
                if not ret:
                    frame_bgr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

            elif mode == "video":
                if video_path is None:
                    frame_bgr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
                else:
                    # (re)open video if needed
                    if cap_video is None or not cap_video.isOpened():
                        cap_video = cv2.VideoCapture(video_path)
                        if not cap_video.isOpened():
                            print(f"[ERROR] Cannot open video: {video_path}")
                            cap_video = None
                            frame_bgr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
                        else:
                            print(f"[INFO] Playing video: {video_path}")

                    if cap_video is not None and cap_video.isOpened():
                        ret, frame_bgr = cap_video.read()
                        if not ret:
                            # restart video (loop)
                            cap_video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ret, frame_bgr = cap_video.read()
                            if not ret:
                                frame_bgr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
                    else:
                        frame_bgr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

            elif mode == "screen":
                # Capture primary monitor
                monitor = sct.monitors[1]  # 0 is "all", 1 is main
                shot = sct.grab(monitor)
                img = np.array(shot)  # BGRA
                frame_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            elif mode == "pattern":
                frame_bgr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
                frame_bgr[:, :, 0] = (frame_index * 3) % 255
                frame_bgr[:, :, 1] = (frame_index * 7) % 255
                frame_bgr[:, :, 2] = (frame_index * 13) % 255

            else:
                frame_bgr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

            # --- Resize to target resolution ---
            frame_bgr = cv2.resize(frame_bgr, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)

            # --- Convert to RGB for ffmpeg ---
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            # --- Apply overlay if enabled ---
            if overlay_enabled:
                frame_rgb = apply_overlay(frame_rgb, overlay_rgb, overlay_alpha)

            # --- Send to ffmpeg ---
            try:
                ffmpeg_proc.stdin.write(frame_rgb.tobytes())
            except BrokenPipeError:
                print("[ERROR] ffmpeg pipe broken.")
                break

            frame_index += 1

            # --- Maintain FPS ---
            dt = time.time() - t0
            delay = max(0, (1.0 / FPS) - dt)
            time.sleep(delay)

    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C received. Exiting...")

    running = False
    time.sleep(0.2)

    # Cleanup
    try:
        if cap_webcam.isOpened():
            cap_webcam.release()
    except Exception:
        pass

    if cap_video is not None:
        try:
            cap_video.release()
        except Exception:
            pass

    try:
        ffmpeg_proc.stdin.close()
    except Exception:
        pass
    ffmpeg_proc.terminate()
    ffmpeg_proc.wait(timeout=2)
    print("[INFO] Shutdown complete.")


if __name__ == "__main__":
    main()
