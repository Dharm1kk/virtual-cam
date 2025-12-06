#!/usr/bin/env python3
import argparse
import subprocess
import shutil
import sys

TARGET_WIDTH = 1280
TARGET_HEIGHT = 720
FPS = 30
DEFAULT_DEVICE = "/dev/video10"
DEFAULT_WEBCAM = "/dev/video0"

current_proc: subprocess.Popen | None = None


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("[ERROR] ffmpeg not found. Install it with: sudo apt install ffmpeg")
        sys.exit(1)


def stop_current():
    global current_proc
    if current_proc is not None:
        print("[INFO] Stopping current source...")
        try:
            current_proc.terminate()
            current_proc.wait(timeout=3)
        except Exception:
            pass
        current_proc = None
        print("[INFO] Source stopped.")


def start_pattern(device: str):
    global current_proc
    stop_current()

    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-re",
        "-f", "lavfi",
        "-i", f"testsrc=size={TARGET_WIDTH}x{TARGET_HEIGHT}:rate={FPS}",
        "-vf", "format=yuv420p",
        "-f", "v4l2",
        device,
    ]

    print("[INFO] Starting PATTERN source →", device)
    print("[DEBUG]", " ".join(cmd))
    current_proc = subprocess.Popen(cmd)


def start_video(device: str, video_path: str, loop: bool = True):
    global current_proc
    stop_current()

    loop_args = ["-stream_loop", "-1"] if loop else []

    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-re",
        *loop_args,
        "-i", video_path,
        "-vf", f"scale={TARGET_WIDTH}:{TARGET_HEIGHT},format=yuv420p",
        "-f", "v4l2",
        device,
    ]

    print(f"[INFO] Starting VIDEO source '{video_path}' → {device}")
    print("[DEBUG]", " ".join(cmd))
    current_proc = subprocess.Popen(cmd)


def start_webcam(device: str, webcam: str):
    global current_proc
    stop_current()

    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-f", "v4l2",
        "-framerate", str(FPS),
        "-video_size", f"{TARGET_WIDTH}x{TARGET_HEIGHT}",
        "-i", webcam,
        "-vf", "format=yuv420p",
        "-f", "v4l2",
        device,
    ]

    print(f"[INFO] Starting WEBCAM source {webcam} → {device}")
    print("[DEBUG]", " ".join(cmd))
    current_proc = subprocess.Popen(cmd)


def menu_loop(device: str):
    check_ffmpeg()
    print(f"[INFO] Using virtual cam device: {device}")
    print("[INFO] Integrated cam is assumed at /dev/video0 (you can change when asked).")

    try:
        while True:
            print("\n=== Virtual Cam Switcher ===")
            print("1) Pattern (test pattern)")
            print("2) Video file → virtual cam")
            print("3) Integrated webcam → virtual cam")
            print("s) Stop current source")
            print("q) Quit")
            choice = input("Select option: ").strip().lower()

            if choice == "1":
                start_pattern(device)

            elif choice == "2":
                path = input("Enter video file path (e.g. 1.mp4): ").strip()
                if not path:
                    print("[WARN] No path given.")
                    continue
                loop_ans = input("Loop video? [Y/n]: ").strip().lower()
                loop = (loop_ans != "n")
                start_video(device, path, loop=loop)

            elif choice == "3":
                cam = input(f"Enter webcam device [{DEFAULT_WEBCAM}]: ").strip()
                if not cam:
                    cam = DEFAULT_WEBCAM
                start_webcam(device, cam)

            elif choice == "s":
                stop_current()

            elif choice == "q":
                print("[INFO] Exiting...")
                break

            else:
                print("[WARN] Invalid choice.")
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted, exiting...")
    finally:
        stop_current()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Terminal switcher for virtual camera sources (ffmpeg + v4l2loopback)"
    )
    parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help=f"Virtual camera device (default: {DEFAULT_DEVICE})",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    menu_loop(args.device)


if __name__ == "__main__":
    main()
