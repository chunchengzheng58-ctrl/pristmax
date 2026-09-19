# -*- coding: utf-8 -*-
"""
People Detection Module

Detects people in video frames using computer vision.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import time


class DetectionStatus(Enum):
    """Detection operation status"""
    IDLE = "idle"
    PROCESSING = "processing"
    ERROR = "error"


@dataclass
class PersonDetection:
    """Person detection result"""
    person_id: str
    bounding_box: Tuple[int, int, int, int]  # x, y, width, height
    confidence: float
    tracking_id: Optional[int] = None
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PeopleDetector:
    """
    People detector for video frames.

    Uses OpenCV's HOG (Histogram of Oriented Gradients) or
    Haar Cascade classifiers for people detection.

    Note: For better accuracy, consider using:
    - YOLO (Ultralytics)
    - SSD (Single Shot Detector)
    - Commercial SDKs (旷视/商汤)
    """

    def __init__(self, use_hog: bool = True):
        """
        Initialize people detector.

        Args:
            use_hog: Use HOG detector (True) or Haar cascade (False)
        """
        self.use_hog = use_hog
        self._status = DetectionStatus.IDLE
        self._initialized = False
        self._detector = None

        # OpenCV import
        try:
            import cv2
            self.cv2 = cv2
            self._available = True
        except ImportError:
            self._available = False
            self._status = DetectionStatus.ERROR
            return

        # Statistics
        self._stats = {
            'frames_processed': 0,
            'people_detected': 0,
            'detection_time_ms': 0,
            'errors': 0
        }

        # Tracking
        self._next_tracking_id = 1

    @property
    def status(self) -> DetectionStatus:
        """Get detector status"""
        return self._status

    def initialize(self) -> bool:
        """
        Initialize the detector.

        Returns:
            True if initialization successful
        """
        if not self._available:
            return False

        try:
            if self.use_hog:
                # HOG + SVM for people detection
                self._detector = self.cv2.HOGDescriptor(
                    (64, 128),
                    (16, 16),
                    (8, 8),
                    (8, 8),
                    9
                )
                # Use default people detector SVM model
                self._detector.setSVMDetector(self.cv2.HOGDescriptor_getDefaultPeopleDetector())
            else:
                # Haar cascade for full body
                cascade_path = self.cv2.data.haarcascades + 'haarcascade_fullbody.xml'
                self._detector = self.cv2.CascadeClassifier(cascade_path)

            self._initialized = True
            return True

        except Exception as e:
            self._status = DetectionStatus.ERROR
            return False

    def detect(
        self,
        frame_data,
        min_confidence: float = 0.3
    ) -> List[PersonDetection]:
        """
        Detect people in a frame.

        Args:
            frame_data: OpenCV image (numpy array) or frame data
            min_confidence: Minimum confidence threshold

        Returns:
            List of PersonDetection objects
        """
        if not self._available:
            return []

        if not self._initialized:
            if not self.initialize():
                return []

        self._status = DetectionStatus.PROCESSING
        start_time = time.time()

        try:
            # Handle frame_data - could be bytes or numpy array
            if isinstance(frame_data, bytes):
                import numpy as np
                frame = self.cv2.imdecode(
                    np.frombuffer(frame_data, dtype=np.uint8),
                    self.cv2.IMREAD_COLOR
                )
            else:
                frame = frame_data

            if frame is None:
                return []

            # Resize for better detection
            frame_resized = self.cv2.resize(frame, (640, 480))
            gray = self.cv2.cvtColor(frame_resized, self.cv2.COLOR_BGR2GRAY)

            detections = []

            if self.use_hog:
                # HOG detection
                boxes, weights = self._detector.detectMultiScale(
                    gray,
                    winStride=(8, 8),
                    padding=(16, 16),
                    scale=1.05
                )

                for i, (x, y, w, h) in enumerate(boxes):
                    confidence = float(weights[i]) if weights is not None else 0.5

                    if confidence >= min_confidence:
                        # Scale back to original frame size
                        scale_x = frame.shape[1] / 640
                        scale_y = frame.shape[0] / 480

                        detection = PersonDetection(
                            person_id=f"person_{self._next_tracking_id}",
                            bounding_box=(
                                int(x * scale_x),
                                int(y * scale_y),
                                int(w * scale_x),
                                int(h * scale_y)
                            ),
                            confidence=confidence,
                            tracking_id=self._next_tracking_id
                        )
                        detections.append(detection)
                        self._next_tracking_id += 1

            else:
                # Haar cascade detection
                bodies = self._detector.detectMultiScale3(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    outputRejectLevels=True
                )

                if len(bodies) >= 2:
                    boxes = bodies[0]
                    weights = bodies[1] if len(bodies) > 1 else None

                    for i, (x, y, w, h) in enumerate(boxes):
                        confidence = float(weights[i]) if weights is not None and i < len(weights) else 0.5

                        if confidence >= min_confidence:
                            scale_x = frame.shape[1] / 640
                            scale_y = frame.shape[0] / 480

                            detection = PersonDetection(
                                person_id=f"person_{self._next_tracking_id}",
                                bounding_box=(
                                    int(x * scale_x),
                                    int(y * scale_y),
                                    int(w * scale_x),
                                    int(h * scale_y)
                                ),
                                confidence=confidence,
                                tracking_id=self._next_tracking_id
                            )
                            detections.append(detection)
                            self._next_tracking_id += 1

            # Update stats
            self._stats['frames_processed'] += 1
            self._stats['people_detected'] += len(detections)
            self._stats['detection_time_ms'] += (time.time() - start_time) * 1000

            self._status = DetectionStatus.IDLE
            return detections

        except Exception as e:
            self._stats['errors'] += 1
            self._status = DetectionStatus.ERROR
            return []

    def get_stats(self) -> Dict:
        """Get detector statistics"""
        stats = self._stats.copy()
        if stats['frames_processed'] > 0:
            stats['avg_detection_time_ms'] = (
                stats['detection_time_ms'] / stats['frames_processed']
            )
            stats['detection_rate'] = (
                stats['people_detected'] / stats['frames_processed']
            )
        return stats

    def reset_stats(self) -> None:
        """Reset statistics"""
        self._stats = {
            'frames_processed': 0,
            'people_detected': 0,
            'detection_time_ms': 0,
            'errors': 0
        }
        self._next_tracking_id = 1


class VehicleDetector:
    """
    Vehicle detector for video frames.

    Uses OpenCV's vehicle detection capabilities.
    """

    def __init__(self):
        self._status = DetectionStatus.IDLE
        self._initialized = False

        try:
            import cv2
            self.cv2 = cv2
            self._available = True
        except ImportError:
            self._available = False
            self._status = DetectionStatus.ERROR

        self._stats = {
            'frames_processed': 0,
            'vehicles_detected': 0,
            'detection_time_ms': 0,
            'errors': 0
        }

    @property
    def status(self) -> DetectionStatus:
        return self._status

    def initialize(self) -> bool:
        """Initialize vehicle detector"""
        if not self._available:
            return False

        try:
            # Use car cascade for vehicle detection
            cascade_path = self.cv2.data.haarcascades + 'haarcascade_car.xml'
            self._detector = self.cv2.CascadeClassifier(cascade_path)

            if self._detector.empty():
                # Fallback - no specific vehicle cascade
                self._detector = None

            self._initialized = True
            return True

        except Exception:
            self._status = DetectionStatus.ERROR
            return False

    def detect(
        self,
        frame_data,
        min_confidence: float = 0.3
    ) -> List[Dict]:
        """
        Detect vehicles in a frame.

        Args:
            frame_data: OpenCV image (numpy array) or frame data
            min_confidence: Minimum confidence threshold

        Returns:
            List of vehicle detection dicts with bounding_box and confidence
        """
        if not self._available:
            return []

        if not self._initialized:
            if not self.initialize():
                return []

        self._status = DetectionStatus.PROCESSING
        start_time = time.time()

        try:
            if isinstance(frame_data, bytes):
                import numpy as np
                frame = self.cv2.imdecode(
                    np.frombuffer(frame_data, dtype=np.uint8),
                    self.cv2.IMREAD_COLOR
                )
            else:
                frame = frame_data

            if frame is None:
                return []

            vehicles = []
            scale = 1.1

            if self._detector:
                gray = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2GRAY)
                cars = self._detector.detectMultiScale3(
                    gray,
                    scaleFactor=scale,
                    minNeighbors=3,
                    outputRejectLevels=True
                )

                if len(cars) >= 2:
                    boxes = cars[0]
                    weights = cars[1] if len(cars) > 1 else None

                    for i, (x, y, w, h) in enumerate(boxes):
                        confidence = float(weights[i]) if weights is not None and i < len(weights) else 0.5

                        if confidence >= min_confidence:
                            vehicles.append({
                                'vehicle_id': f"vehicle_{i}",
                                'bounding_box': (x, y, w, h),
                                'confidence': confidence,
                                'type': 'car'  # Simplified
                            })

            # Update stats
            self._stats['frames_processed'] += 1
            self._stats['vehicles_detected'] += len(vehicles)
            self._stats['detection_time_ms'] += (time.time() - start_time) * 1000

            self._status = DetectionStatus.IDLE
            return vehicles

        except Exception as e:
            self._stats['errors'] += 1
            self._status = DetectionStatus.ERROR
            return []

    def get_stats(self) -> Dict:
        """Get detector statistics"""
        return self._stats.copy()
