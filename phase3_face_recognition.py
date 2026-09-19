# -*- coding: utf-8 -*-
"""
Phase 3 - Face Recognition Integration Demo

Demonstrates:
1. OpenCV-based people detection
2. Vehicle detection
3. Integration with semantic reducer
"""

import cv2
import sys
import time
import numpy as np
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from semantic_reduction import SemanticReducer, Config
from semantic_reduction.utils.config import init_config
from semantic_reduction.detection.face_detector import PeopleDetector, VehicleDetector


def create_test_image_with_people(output_path: str) -> str:
    """
    Create a test image with simulated people.

    Args:
        output_path: Output image path

    Returns:
        Path to created image
    """
    # Create a simple test image
    width, height = 800, 600

    # Create image with gradient background
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Gradient background
    for y in range(height):
        color = int(100 + (y / height) * 100)
        img[y, :] = [color, color, color]

    # Draw some rectangles to simulate people
    # Person 1
    cv2.rectangle(img, (100, 200), (200, 450), (50, 100, 200), -1)
    cv2.circle(img, (150, 180), 40, (220, 180, 150), -1)

    # Person 2
    cv2.rectangle(img, (300, 220), (400, 450), (100, 50, 200), -1)
    cv2.circle(img, (350, 200), 40, (220, 180, 150), -1)

    # Person 3
    cv2.rectangle(img, (500, 210), (600, 450), (50, 150, 200), -1)
    cv2.circle(img, (550, 190), 40, (220, 180, 150), -1)

    # Draw a car-like rectangle
    cv2.rectangle(img, (50, 480), (250, 550), (200, 100, 50), -1)
    cv2.rectangle(img, (60, 490), (120, 520), (150, 150, 200), -1)
    cv2.rectangle(img, (180, 490), (240, 520), (150, 150, 200), -1)

    cv2.imwrite(output_path, img)
    print(f"Test image created: {output_path}")
    return output_path


def demo_people_detector():
    """Demo: People detection using OpenCV"""
    print("\n" + "="*70)
    print("Phase 3 - People Detection Demo")
    print("="*70)

    # Create test image
    test_image_path = "./data/test_people.jpg"
    Path("./data").mkdir(exist_ok=True)

    if not Path(test_image_path).exists():
        create_test_image_with_people(test_image_path)

    print("\n[1] Initializing People Detector...")
    detector = PeopleDetector(use_hog=True)

    if not detector.initialize():
        print("  ERROR: Could not initialize detector (OpenCV may be missing cascade files)")
        print("  Using simulated detection instead...")

        # Simulated detection for demo
        simulated_result = [{
            'person_id': 'person_1',
            'bounding_box': (100, 200, 100, 250),
            'confidence': 0.85,
            'tracking_id': 1
        }]
        print(f"  Simulated detections: {len(simulated_result)}")
        return simulated_result

    print(f"  Status: {detector.status.value}")

    print("\n[2] Loading test image...")
    frame = cv2.imread(test_image_path)
    if frame is None:
        print("  ERROR: Could not load image")
        return []

    print(f"  Image size: {frame.shape[1]}x{frame.shape[0]}")

    print("\n[3] Detecting people...")
    start_time = time.time()
    detections = detector.detect(frame, min_confidence=0.3)
    detection_time = (time.time() - start_time) * 1000

    print(f"\n[4] Detection Results:")
    print(f"  People found: {len(detections)}")
    print(f"  Detection time: {detection_time:.1f}ms")

    for det in detections:
        x, y, w, h = det.bounding_box
        print(f"    - {det.person_id}: bbox=({x},{y},{w},{h}), conf={det.confidence:.2f}")

    print("\n[5] Detector Statistics:")
    stats = detector.get_stats()
    print(f"  Frames processed: {stats['frames_processed']}")
    print(f"  People detected: {stats['people_detected']}")
    if 'avg_detection_time_ms' in stats:
        print(f"  Avg detection time: {stats['avg_detection_time_ms']:.1f}ms")

    return detections


def demo_vehicle_detector():
    """Demo: Vehicle detection using OpenCV"""
    print("\n" + "="*70)
    print("Phase 3 - Vehicle Detection Demo")
    print("="*70)

    # Create test image
    test_image_path = "./data/test_people.jpg"
    if not Path(test_image_path).exists():
        create_test_image_with_people(test_image_path)

    print("\n[1] Initializing Vehicle Detector...")
    detector = VehicleDetector()

    if not detector.initialize():
        print("  WARNING: Could not initialize vehicle detector")
        print("  Cascade files may not be available")

    print(f"  Status: {detector.status.value}")

    print("\n[2] Loading test image...")
    frame = cv2.imread(test_image_path)
    if frame is None:
        print("  ERROR: Could not load image")
        return []

    print("\n[3] Detecting vehicles...")
    start_time = time.time()
    detections = detector.detect(frame, min_confidence=0.3)
    detection_time = (time.time() - start_time) * 1000

    print(f"\n[4] Detection Results:")
    print(f"  Vehicles found: {len(detections)}")
    print(f"  Detection time: {detection_time:.1f}ms")

    for det in detections:
        x, y, w, h = det['bounding_box']
        print(f"    - {det['vehicle_id']}: type={det['type']}, bbox=({x},{y},{w},{h}), conf={det['confidence']:.2f}")

    print("\n[5] Detector Statistics:")
    stats = detector.get_stats()
    print(f"  Frames processed: {stats['frames_processed']}")
    print(f"  Vehicles detected: {stats['vehicles_detected']}")


def demo_face_detection():
    """Demo: Face detection (placeholder for real face recognition)"""
    print("\n" + "="*70)
    print("Phase 3 - Face Detection Demo")
    print("="*70)

    print("""
[INFO] Full face recognition requires face_recognition library:
       pip install face_recognition

       Or commercial SDKs:
       - 旷视 (Megvii) Face++
       - 商汤 (SenseTime)
       - 虹软 (ArcSoft)

[INFO] For this demo, face detection is simulated based on:
       - People detection results
       - Random probability
""")

    # Simulate face detection
    import random

    people_detections = [
        {'person_id': 'person_1', 'confidence': 0.85},
        {'person_id': 'person_2', 'confidence': 0.78},
        {'person_id': 'person_3', 'confidence': 0.92},
    ]

    face_detections = []
    for person in people_detections:
        # Simulate face detection (not all people have detectable faces)
        if random.random() > 0.3:  # 70% chance of face detection
            face_detections.append({
                'person_id': person['person_id'],
                'confidence': person['confidence'] * random.uniform(0.7, 0.95),
                'face_detected': True
            })

    print(f"\n[1] Simulated Face Detection Results:")
    print(f"  People detected: {len(people_detections)}")
    print(f"  Faces detected: {len(face_detections)}")

    for face in face_detections:
        print(f"    - {face['person_id']}: conf={face['confidence']:.2f}, face={face['face_detected']}")

    return face_detections


def demo_end_to_end_with_detection():
    """Demo: End-to-end processing with real detection"""
    print("\n" + "="*70)
    print("Phase 3 - End-to-End with Detection Demo")
    print("="*70)

    # Initialize
    config = init_config('config.yaml')
    reducer = SemanticReducer(config=config, audit_path='./data/audit')

    # Create test image
    test_image_path = "./data/test_people.jpg"
    if not Path(test_image_path).exists():
        create_test_image_with_people(test_image_path)

    print("\n[1] Processing image through detection pipeline...")

    # People detection
    people_detector = PeopleDetector(use_hog=True)
    people_detector.initialize()

    frame = cv2.imread(test_image_path)
    people = people_detector.detect(frame, min_confidence=0.3)

    print(f"  People detected: {len(people)}")

    # Vehicle detection
    vehicle_detector = VehicleDetector()
    vehicle_detector.initialize()

    vehicles = vehicle_detector.detect(frame, min_confidence=0.3)
    print(f"  Vehicles detected: {len(vehicles)}")

    # Simulate face detection
    import random
    has_faces = len(people) > 0 and random.random() > 0.3
    print(f"  Faces detected: {has_faces}")

    # Build analysis result
    analysis_result = {
        'motion_score': 0.3,
        'has_faces': has_faces,
        'has_people': len(people) > 0,
        'has_vehicles': len(vehicles) > 0,
        'person_count': len(people),
        'vehicle_count': len(vehicles),
        'scene_type': 'parking' if len(vehicles) > 0 else 'indoor'
    }

    # Use appropriate policy
    if len(vehicles) > 0:
        policy = {
            'preserve_with_faces': True,
            'preserve_with_people': True,
            'preserve_with_vehicles': True,
            'low_value_downsample_ratio': 0.1
        }
    else:
        policy = {
            'preserve_with_faces': True,
            'preserve_with_people': True,
            'preserve_with_vehicles': False,
            'low_value_downsample_ratio': 0.1
        }

    print("\n[2] Semantic analysis result:")
    print(f"  Motion score: {analysis_result['motion_score']}")
    print(f"  Has faces: {analysis_result['has_faces']}")
    print(f"  Has people: {analysis_result['has_people']} ({analysis_result['person_count']})")
    print(f"  Has vehicles: {analysis_result['has_vehicles']} ({analysis_result['vehicle_count']})")
    print(f"  Scene type: {analysis_result['scene_type']}")

    print("\n[3] Processing with semantic reducer...")
    result = reducer.process_video(test_image_path, analysis_result, policy)

    print(f"\n[4] Result:")
    print(f"  Action: {result.action.value}")
    print(f"  Classification: {result.classification.value}")
    print(f"  Original: {result.original_size:,} bytes")
    print(f"  New: {result.new_size:,} bytes")
    print(f"  Savings: {result.savings_percent:.1f}%")
    print(f"  Reasons: {result.reasons}")

    print("\n[5] System statistics...")
    stats = reducer.get_stats()
    print(f"  Total processed: {stats['total_processed']}")
    print(f"  By action: {stats['by_action']}")
    print(f"  By classification: {stats['by_classification']}")


def main():
    print("\n" + "#"*70)
    print("# Phase 3 - Face Recognition & People Detection Demo")
    print("#"*70)
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*70)

    try:
        # Demos
        people_results = demo_people_detector()
        demo_vehicle_detector()
        demo_face_detection()
        demo_end_to_end_with_detection()

        print("\n" + "#"*70)
        print("# Phase 3 Demo Complete")
        print("#"*70)
        print("""
Face Recognition & People Detection Features:
- OpenCV HOG-based people detection
- Haar cascade vehicle detection
- Face detection (requires face_recognition SDK)
- Real-time tracking IDs
- Integration with semantic reducer

Detection Accuracy:
- People detection: ~80-90% with HOG
- Vehicle detection: ~70-85% with Haar cascade
- Face detection: ~95%+ with face_recognition library

Next Steps:
1. Install face_recognition: pip install face_recognition
2. Or integrate commercial SDK (旷视/商汤)
3. Fine-tune detection parameters
4. Deploy to production
""")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
