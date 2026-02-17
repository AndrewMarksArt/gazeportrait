"""
Advanced sprite-sheet builder — one command, video → atlas.

Uses MediaPipe face detection + OpenCV head-pose estimation to sort frames
into a yaw×pitch grid. Sharpest frame wins each cell; empty cells are
filled by inverse-distance blending of neighbors.

Requires: pip install -r requirements-advanced.txt

Usage:
  python build-sprite-sheet.py input.mp4 --out atlas.jpg

The model file is downloaded automatically on first run.
"""

import argparse
import cv2
import numpy as np
import mediapipe as mp
import time
import os
import urllib.request

# ── Defaults ─────────────────────────────────────────────────────────────
GRID_SIZE = 7
CELL_SIZE = 256
JPEG_QUALITY = 92
PERCENTILE_LO = 2
PERCENTILE_HI = 98
CROP_SCALE = 2.5
SMOOTH_ALPHA = 0.70

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
MODEL_PATH = "/tmp/face_landmarker_v2_with_blendshapes.task"

# 3D model points for solvePnP
MODEL_POINTS = np.array([
    (0.0, 0.0, 0.0),           # Nose tip
    (0.0, -330.0, -65.0),      # Chin
    (-225.0, 170.0, -135.0),   # Left eye outer
    (225.0, 170.0, -135.0),    # Right eye outer
    (-150.0, -150.0, -125.0),  # Left mouth corner
    (150.0, -150.0, -125.0),   # Right mouth corner
], dtype=np.float64)

LANDMARK_IDS = [1, 152, 263, 33, 287, 57]


def ensure_model():
    if os.path.exists(MODEL_PATH):
        return
    print(f"Downloading face landmarker model to {MODEL_PATH}...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Done.")


def build(video_path, output_path, grid_size, cell_size, quality):
    ensure_model()

    BaseOptions = mp.tasks.BaseOptions
    FaceLandmarker = mp.tasks.vision.FaceLandmarker
    FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=VisionRunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=0.3,
        min_face_presence_confidence=0.3,
        min_tracking_confidence=0.3,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=True,
    )

    landmarker = FaceLandmarker.create_from_options(options)

    # ── Pass 1: extract face data ────────────────────────────────────────
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"Video: {width}x{height}, {total_frames} frames @ {fps:.1f}fps")
    print(f"Target: {grid_size}x{grid_size} grid, {cell_size}px cells")

    focal_length = width
    camera_matrix = np.array([
        [focal_length, 0, width / 2],
        [0, focal_length, height / 2],
        [0, 0, 1],
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1))

    frame_data = []
    t0 = time.time()
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int(frame_idx * 1000 / fps)
        result = landmarker.detect_for_video(mp_image, timestamp_ms)

        if result.face_landmarks and len(result.face_landmarks) > 0:
            landmarks = result.face_landmarks[0]
            image_points = np.array([
                (landmarks[i].x * width, landmarks[i].y * height)
                for i in LANDMARK_IDS
            ], dtype=np.float64)

            success, rvec, tvec = cv2.solvePnP(
                MODEL_POINTS, image_points, camera_matrix, dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE
            )

            if success:
                rmat, _ = cv2.Rodrigues(rvec)
                angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)

                nose = landmarks[1]
                face_cx = nose.x * width
                face_cy = nose.y * height

                xs = [l.x * width for l in landmarks]
                ys = [l.y * height for l in landmarks]
                face_size = max(max(xs) - min(xs), max(ys) - min(ys))

                fx1 = max(0, int(face_cx - face_size / 2))
                fy1 = max(0, int(face_cy - face_size / 2))
                fx2 = min(width, int(face_cx + face_size / 2))
                fy2 = min(height, int(face_cy + face_size / 2))
                face_roi = cv2.cvtColor(frame[fy1:fy2, fx1:fx2], cv2.COLOR_BGR2GRAY)
                sharpness = cv2.Laplacian(face_roi, cv2.CV_64F).var() if face_roi.size > 0 else 0.0

                frame_data.append({
                    'frame_idx': frame_idx,
                    'yaw': angles[1],
                    'pitch': angles[0],
                    'sharpness': sharpness,
                    'face_cx': face_cx,
                    'face_cy': face_cy,
                    'face_size': face_size,
                })

        frame_idx += 1
        if frame_idx % 100 == 0:
            elapsed = time.time() - t0
            print(f"  Pass 1: {frame_idx}/{total_frames} ({elapsed:.0f}s, {len(frame_data)} faces)")

    cap.release()
    print(f"Pass 1: {len(frame_data)} faces from {total_frames} frames in {time.time()-t0:.1f}s")

    if len(frame_data) == 0:
        print("\nNo faces detected. This script requires a human face.")
        print("For non-human subjects, use the simple pipeline instead:")
        print("  ./scripts/extract-frames.sh video.mp4")
        print("  python scripts/build-atlas.py frames/ --start 0 --count 49 --cols 7")
        return

    # ── Grid mapping ─────────────────────────────────────────────────────
    yaws = np.array([d['yaw'] for d in frame_data])
    pitches = np.array([d['pitch'] for d in frame_data])

    yaw_lo, yaw_hi = np.percentile(yaws, PERCENTILE_LO), np.percentile(yaws, PERCENTILE_HI)
    pitch_lo, pitch_hi = np.percentile(pitches, PERCENTILE_LO), np.percentile(pitches, PERCENTILE_HI)

    median_cx = np.median([d['face_cx'] for d in frame_data])
    median_cy = np.median([d['face_cy'] for d in frame_data])
    median_size = np.median([d['face_size'] for d in frame_data])

    grid = {}
    for d in frame_data:
        yn = (d['yaw'] - yaw_lo) / (yaw_hi - yaw_lo) if yaw_hi != yaw_lo else 0.5
        pn = (d['pitch'] - pitch_lo) / (pitch_hi - pitch_lo) if pitch_hi != pitch_lo else 0.5
        yn = max(0.0, min(1.0, yn))
        pn = max(0.0, min(1.0, pn))

        col = max(0, min(grid_size - 1, int(yn * (grid_size - 1))))
        row = max(0, min(grid_size - 1, int((1.0 - pn) * (grid_size - 1))))

        key = (col, row)
        if key not in grid or d['sharpness'] > grid[key]['sharpness']:
            grid[key] = d

    total_cells = grid_size * grid_size
    print(f"Coverage: {len(grid)}/{total_cells} cells ({100*len(grid)/total_cells:.1f}%)")

    # ── Pass 2: crop and place ───────────────────────────────────────────
    needed = {d['frame_idx'] for d in grid.values()}
    cap = cv2.VideoCapture(video_path)
    frame_images = {}
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx in needed:
            frame_images[frame_idx] = frame.copy()
        frame_idx += 1

    cap.release()

    atlas = np.zeros((grid_size * cell_size, grid_size * cell_size, 3), dtype=np.uint8)
    cell_images = {}

    for (col, row), d in grid.items():
        frame = frame_images[d['frame_idx']]
        cx = SMOOTH_ALPHA * d['face_cx'] + (1 - SMOOTH_ALPHA) * median_cx
        cy = SMOOTH_ALPHA * d['face_cy'] + (1 - SMOOTH_ALPHA) * median_cy
        fsize = SMOOTH_ALPHA * d['face_size'] + (1 - SMOOTH_ALPHA) * median_size

        crop_half = int(fsize * CROP_SCALE / 2)
        cy_shifted = cy + fsize * 0.15

        x1, y1 = int(cx - crop_half), int(cy_shifted - crop_half)
        x2, y2 = x1 + 2 * crop_half, y1 + 2 * crop_half

        pad = [max(0, -y1), max(0, y2 - height), max(0, -x1), max(0, x2 - width)]
        crop = frame[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]

        if any(p > 0 for p in pad):
            crop = cv2.copyMakeBorder(crop, *pad, cv2.BORDER_REFLECT_101)

        cell = cv2.resize(crop, (cell_size, cell_size), interpolation=cv2.INTER_AREA)
        cell_images[(col, row)] = cell
        atlas[row*cell_size:(row+1)*cell_size, col*cell_size:(col+1)*cell_size] = cell

    # ── Fill empty cells ─────────────────────────────────────────────────
    filled_positions = list(cell_images.keys())
    filled_cols = np.array([p[0] for p in filled_positions])
    filled_rows = np.array([p[1] for p in filled_positions])
    empty_count = 0

    for row in range(grid_size):
        for col in range(grid_size):
            if (col, row) in cell_images:
                continue
            empty_count += 1
            dists = np.sqrt((filled_cols - col) ** 2 + (filled_rows - row) ** 2)
            k = min(4, len(filled_positions))
            nearest = np.argsort(dists)[:k]
            weights = 1.0 / (dists[nearest] + 1e-6)
            weights /= weights.sum()

            blended = np.zeros((cell_size, cell_size, 3), dtype=np.float64)
            for i, idx in enumerate(nearest):
                blended += weights[i] * cell_images[filled_positions[idx]].astype(np.float64)

            atlas[row*cell_size:(row+1)*cell_size, col*cell_size:(col+1)*cell_size] = np.clip(blended, 0, 255).astype(np.uint8)

    if empty_count:
        print(f"Filled {empty_count} empty cells via neighbor blending")

    # ── Save ─────────────────────────────────────────────────────────────
    cv2.imwrite(output_path, atlas, [cv2.IMWRITE_JPEG_QUALITY, quality])
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\nSaved {output_path} ({size_mb:.1f} MB)")
    print(f"Grid: {grid_size}x{grid_size}, cell: {cell_size}px, yaw: [{yaw_lo:.1f}, {yaw_hi:.1f}]°")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a gaze-tracking sprite atlas from video")
    parser.add_argument("video", help="input video file")
    parser.add_argument("--out", default="atlas.jpg", help="output atlas path")
    parser.add_argument("--grid", type=int, default=GRID_SIZE, help=f"grid size NxN (default {GRID_SIZE})")
    parser.add_argument("--cell", type=int, default=CELL_SIZE, help=f"cell size in px (default {CELL_SIZE})")
    parser.add_argument("--quality", type=int, default=JPEG_QUALITY, help=f"JPEG quality (default {JPEG_QUALITY})")
    args = parser.parse_args()
    build(args.video, args.out, args.grid, args.cell, args.quality)
