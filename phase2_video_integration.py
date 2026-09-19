# -*- coding: utf-8 -*-
"""
Phase 2 - Video Source Integration Demo

Demonstrates:
1. OpenCV-based video capture
2. Real motion detection
3. Frame analysis
4. Integration with semantic reducer
"""

import cv2
import sys
import time
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from semantic_reduction import SemanticReducer, Config
from semantic_reduction.utils.config import init_config
from semantic_reduction.pipeline.stream_processor import VideoStreamProcessor, StreamProcessorPool
from semantic_reduction.storage.filesystem import FileSystemBackend


def create_test_video(output_path: str, duration_seconds: int = 10, fps: int = 30) -> str:
    """
    Create a test video file using OpenCV.

    Args:
        output_path: Output video file path
        duration_seconds: Video duration
        fps: Frames per second

    Returns:
        Path to created video
    """
    # Video properties
    width, height = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    total_frames = duration_seconds * fps

    print(f"Creating test video: {duration_seconds}s @ {fps}fps ({total_frames} frames)")

    for frame_num in range(total_frames):
        # Create frame with animated content
        frame = bytearray(height * width * 3)

        # Background - changes over time (simulating day/night)
        t = frame_num / total_frames
        base_color = int(50 + 100 * t)

        # Fill with base color
        for i in range(0, len(frame), 3):
            frame[i] = base_color      # B
            frame[i + 1] = base_color  # G
            frame[i + 2] = base_color  # R

        # Add some motion (simulated moving object)
        obj_x = int((frame_num * 5) % width)
        obj_y = height // 2

        # Draw a rectangle (simulated object)
        rect_size = 50
        for y in range(max(0, obj_y - rect_size//2), min(height, obj_y + rect_size//2)):
            for x in range(max(0, obj_x - rect_size//2), min(width, obj_x + rect_size//2)):
                idx = (y * width + x) * 3
                if idx + 2 < len(frame):
                    frame[idx] = 0       # B
                    frame[idx + 1] = 255 # G
                    frame[idx + 2] = 0   # R

        # Convert to numpy array and write
        frame_array = bytes(frame)
        import numpy as np
        img = np.frombuffer(frame_array, dtype=np.uint8).reshape((height, width, 3))
        out.write(img)

        if frame_num % 30 == 0:
            print(f"  Frame {frame_num}/{total_frames}")

    out.release()
    print(f"Video created: {output_path}")

    # Verify video
    cap = cv2.VideoCapture(output_path)
    actual_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    print(f"  Verified: {actual_frames} frames @ {actual_fps:.1f} fps")
    return output_path


def demo_video_file_processing():
    """Demo: Process a video file with OpenCV"""
    print("\n" + "="*70)
    print("Phase 2 - Video File Processing Demo")
    print("="*70)

    # Create test video
    test_video_path = "./data/test_video.mp4"
    Path("./data").mkdir(exist_ok=True)

    if not Path(test_video_path).exists():
        create_test_video(test_video_path, duration_seconds=5)
    else:
        print(f"Using existing test video: {test_video_path}")

    print("\n[1] Opening video file with OpenCV...")
    cap = cv2.VideoCapture(test_video_path)

    if not cap.isOpened():
        print("ERROR: Cannot open video")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"  Video info:")
    print(f"    Frames: {total_frames}")
    print(f"    FPS: {fps:.1f}")
    print(f"    Resolution: {width}x{height}")

    print("\n[2] Processing frames with motion detection...")

    frame_count = 0
    motion_frames = 0
    last_gray = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Motion detection
        if last_gray is not None:
            diff = cv2.absdiff(gray, last_gray)
            motion_score = diff.mean() / 255.0

            if motion_score > 0.05:
                motion_frames += 1
                if frame_count % 30 == 0:
                    print(f"  Frame {frame_count}: motion detected (score: {motion_score:.3f})")

        last_gray = gray.copy()
        frame_count += 1

    cap.release()

    print(f"\n[3] Analysis Results:")
    print(f"  Total frames processed: {frame_count}")
    print(f"  Frames with motion: {motion_frames}")
    print(f"  Motion percentage: {motion_frames/frame_count*100:.1f}%")


def demo_stream_processor():
    """Demo: VideoStreamProcessor with simulated stream"""
    print("\n" + "="*70)
    print("Phase 2 - Stream Processor Demo")
    print("="*70)

    # Create test video for simulated stream
    test_video_path = "./data/test_video.mp4"
    if not Path(test_video_path).exists():
        create_test_video(test_video_path, duration_seconds=5)

    print("\n[1] Creating stream processor...")

    # Use test video as "RTSP" source (in production, use real RTSP URL)
    processor = VideoStreamProcessor(
        camera_id="TEST-CAM-001",
        rtsp_url=test_video_path,  # Using file path as simulation
        buffer_size=30,
        analysis_interval=5
    )

    print(f"  Camera ID: {processor.camera_id}")
    print(f"  Status: {processor.status.value}")

    # Define frame callback
    frame_count = [0]
    motion_events = [0]

    def on_frame(frame):
        frame_count[0] += 1
        if frame.motion_detected:
            motion_events[0] += 1
        if frame_count[0] % 30 == 0:
            print(f"  Frame {frame.frame_index}: motion={frame.motion_detected}, "
                  f"brightness={frame.brightness:.2f}, sharpness={frame.sharpness:.2f}")

    print("\n[2] Starting stream processing...")
    processor.connect()
    processor.start(frame_callback=on_frame)

    # Process for a few seconds
    time.sleep(3)

    processor.stop()
    processor.disconnect()

    print(f"\n[3] Processing Results:")
    print(f"  Frames captured: {processor.get_stats()['frames_captured']}")
    print(f"  Frames analyzed: {processor.get_stats()['frames_analyzed']}")
    print(f"  Motion events: {processor.get_stats()['motion_events']}")


def demo_storage_backend():
    """Demo: FileSystem storage backend"""
    print("\n" + "="*70)
    print("Phase 2 - Storage Backend Demo")
    print("="*70)

    # Initialize storage
    storage = FileSystemBackend("./data/storage")

    print("\n[1] Storing test video...")

    # Store the test video
    test_video = "./data/test_video.mp4"
    if Path(test_video).exists():
        file_info = storage.store(test_video, "videos/test_video.mp4")
        print(f"  Stored: {file_info.file_id}")
        print(f"  Path: {file_info.path}")
        print(f"  Size: {file_info.size:,} bytes")
        print(f"  Checksum: {file_info.checksum[:16]}...")

    print("\n[2] Listing stored files...")
    files = storage.list_files("videos")
    print(f"  Files in 'videos': {len(files)}")
    for f in files:
        print(f"    - {f.path} ({f.size:,} bytes)")

    print("\n[3] Storage usage...")
    usage = storage.get_usage()
    print(f"  Total bytes: {usage['total_bytes']:,}")
    print(f"  Total files: {usage['total_files']}")

    print("\n[4] Statistics...")
    stats = storage.get_stats()
    print(f"  Files stored: {stats['files_stored']}")
    print(f"  Bytes stored: {stats['bytes_stored']:,}")


def demo_end_to_end():
    """Demo: End-to-end processing"""
    print("\n" + "="*70)
    print("Phase 2 - End-to-End Processing Demo")
    print("="*70)

    # Initialize
    config = init_config('config.yaml')
    reducer = SemanticReducer(config=config, audit_path='./data/audit')

    # Create test video
    test_video = "./data/test_video.mp4"
    if not Path(test_video).exists():
        create_test_video(test_video, duration_seconds=5)

    # Simulate video analysis result
    analysis_result = {
        'motion_score': 0.35,
        'has_faces': True,  # Simulated - real detection would find this
        'has_people': True,
        'has_vehicles': False,
        'scene_type': 'indoor',
        'avg_brightness': 0.5,
        'avg_sharpness': 0.7
    }

    policy = {
        'preserve_with_faces': True,
        'preserve_with_people': True,
        'preserve_with_vehicles': True,
        'low_value_downsample_ratio': 0.1
    }

    print("\n[1] Processing video through semantic reducer...")

    result = reducer.process_video(test_video, analysis_result, policy)

    print(f"\n[2] Result:")
    print(f"  Action: {result.action.value}")
    print(f"  Classification: {result.classification.value}")
    print(f"  Original: {result.original_size:,} bytes")
    print(f"  New: {result.new_size:,} bytes")
    print(f"  Savings: {result.savings_percent:.1f}%")
    print(f"  Reasons: {result.reasons}")

    print("\n[3] System statistics...")
    stats = reducer.get_stats()
    print(f"  Total processed: {stats['total_processed']}")
    print(f"  By action: {stats['by_action']}")

    print("\n[4] ROI calculation...")
    roi = reducer.calculate_roi(scale_factor=1000, years=1)
    print(f"  Annual savings: {roi['annual_savings']:,.0f} {roi['currency']}")
    print(f"  ROI: {roi['roi_percent']:.0f}%")


def main():
    print("\n" + "#"*70)
    print("# Phase 2 - Video Source Integration Demo")
    print("#"*70)
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*70)

    try:
        # Demos
        demo_video_file_processing()
        demo_stream_processor()
        demo_storage_backend()
        demo_end_to_end()

        print("\n" + "#"*70)
        print("# Phase 2 Demo Complete")
        print("#"*70)
        print("""
Video Source Integration Features:
- OpenCV-based video capture
- Real-time motion detection
- Frame analysis (brightness, sharpness)
- Storage backend with checksum verification
- End-to-end semantic processing

Next Steps:
1. Connect real RTSP camera (replace test video URL)
2. Integrate face detection SDK
3. Deploy to production
""")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
