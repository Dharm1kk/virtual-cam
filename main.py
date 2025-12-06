#!/usr/bin/env python3
import argparse
import av
import numpy as np
import pyvirtualcam

TARGET_WIDTH = 1280
TARGET_HEIGHT = 720
FPS = 30
DEFAULT_DEVICE = "/dev/video10"


def run_pattern(device: str):
    """Send animated color pattern to the virtual camera."""
    with pyvirtualcam.Camera(
        width=TARGET_WIDTH,
        height=TARGET_HEIGHT,
        fps=FPS,
        device=device
    ) as cam:
        print(f"[INFO] Virtual camera started on {cam.device}")
        print("[INFO] Mode: animated pattern (Ctrl+C to stop)")

        t = 0
        try:
            while True:
                frame = np.zeros((TARGET_HEIGHT, TARGET_WIDTH, 3), dtype=np.uint8)
                frame[:, :, 0] = (t * 2) % 255     # B
                frame[:, :, 1] = (t * 5) % 255     # G
                frame[:, :, 2] = (t * 10) % 255    # R

                cam.send(frame)
                cam.sleep_until_next_frame()
                t += 1

        except KeyboardInterrupt:
            print("\n[INFO] Pattern mode stopped.")


def run_video(device: str, video_path: str, loop: bool):
    """Stream a video file into the virtual camera."""
    print(f"[INFO] Opening video: {video_path}")

    with pyvirtualcam.Camera(
        width=TARGET_WIDTH,
        height=TARGET_HEIGHT,
        fps=FPS,
        device=device
    ) as cam:
        print(f"[INFO] Virtual camera started on {cam.device}")
        print("[INFO] Mode: video file → virtual cam (Ctrl+C to stop)")

        while True:
            try:
                container = av.open(video_path)
            except av.AVError as e:
                print(f"[ERROR] Could not open video: {e}")
                return

            video_stream = container.streams.video[0]
            video_stream.thread_type = "AUTO"

            try:
                for frame in container.decode(video_stream):
                    frame_resized = frame.reformat(
                        width=TARGET_WIDTH,
                        height=TARGET_HEIGHT
                    )
                    img = frame_resized.to_ndarray(format="rgb24")

                    cam.send(img)
                    cam.sleep_until_next_frame()

            except KeyboardInterrupt:
                print("\n[INFO] Video mode stopped.")
                return

            if not loop:
                print("[INFO] Video finished (no loop).")
                return

            print("[INFO] Video finished — looping again...")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Mini OBS-like virtual camera (Linux + v4l2loopback)"
    )

    parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help=f"Virtual cam device path (default: {DEFAULT_DEVICE})"
    )

    subparsers = parser.add_subparsers(dest="mode")

    subparsers.add_parser("pattern", help="Send animated pattern to virtual cam")

    video_parser = subparsers.add_parser("video", help="Stream a video file")
    video_parser.add_argument("path", help="Video file path")
    video_parser.add_argument("--loop", action="store_true", help="Loop video")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.mode == "video":
        run_video(args.device, args.path, args.loop)
    else:
        run_pattern(args.device)


if __name__ == "__main__":
    main()
