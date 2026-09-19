# -*- coding: utf-8 -*-
"""
Video Stream Processor

Real-time video stream processing with OpenCV.
"""

import cv2
import hashlib
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any
import uuid


class StreamStatus(Enum):
    """Stream processing status"""
    IDLE = "idle"
    PROCESSING = "processing"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class VideoFrame:
    """Processed video frame with metadata"""
    frame_id: str
    camera_id: str
    timestamp: float
    frame_index: int
    data: Any  # OpenCV numpy array
    width: int
    height: int
    fps: float

    # Analysis results
    motion_detected: bool = False
    motion_score: float = 0.0
    brightness: float = 0.0
    sharpness: float = 0.0

    # Object detection
    has_faces: bool = False
    face_count: int = 0
    has_people: bool = False
    person_count: int = 0
    has_vehicles: bool = False
    vehicle_count: int = 0

    # Scene info
    scene_type: str = "unknown"

    def __post_init__(self):
        if not self.frame_id:
            self.frame_id = uuid.uuid4().hex


class VideoStreamProcessor:
    """
    Real-time video stream processor.

    Features:
    - OpenCV-based frame capture
    - Motion detection
    - Brightness/sharpness analysis
    - Frame differencing
    - Configurable processing pipeline
    """

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        buffer_size: int = 30,
        analysis_interval: int = 1  # Analyze every N frames
    ):
        """
        Initialize stream processor.

        Args:
            camera_id: Unique camera identifier
            rtsp_url: RTSP stream URL
            buffer_size: Frame buffer size
            analysis_interval: Process analysis every N frames
        """
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.buffer_size = buffer_size
        self.analysis_interval = analysis_interval

        # OpenCV video capture
        self._cap: Optional[cv2.VideoCapture] = None

        # State
        self._status = StreamStatus.IDLE
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None

        # Callbacks
        self._frame_callback: Optional[Callable[[VideoFrame], None]] = None
        self._analysis_callback: Optional[Callable[[VideoFrame], None]] = None

        # Frame buffer
        self._frame_buffer: List[VideoFrame] = []
        self._last_frame: Optional[Any] = None
        self._last_gray: Optional[Any] = None

        # Statistics
        self._stats = {
            'frames_captured': 0,
            'frames_processed': 0,
            'frames_analyzed': 0,
            'motion_events': 0,
            'last_capture_time': None,
            'capture_errors': 0
        }

        # Motion detection threshold
        self.motion_threshold = 0.05

    @property
    def status(self) -> StreamStatus:
        """Get current status"""
        return self._status

    @property
    def is_running(self) -> bool:
        """Check if processor is running"""
        return self._running

    def connect(self) -> bool:
        """
        Connect to RTSP stream.

        Returns:
            True if connection successful
        """
        try:
            self._cap = cv2.VideoCapture(self.rtsp_url)

            if not self._cap.isOpened():
                raise ConnectionError(f"Cannot open stream: {self.rtsp_url}")

            # Get stream properties
            self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._fps = self._cap.get(cv2.CAP_PROP_FPS)

            self._status = StreamStatus.IDLE
            return True

        except Exception as e:
            self._status = StreamStatus.ERROR
            raise ConnectionError(f"Failed to connect to {self.rtsp_url}: {e}")

    def disconnect(self) -> None:
        """Disconnect from stream"""
        self.stop()

        if self._cap:
            self._cap.release()
            self._cap = None

        self._status = StreamStatus.IDLE

    def start(
        self,
        frame_callback: Callable[[VideoFrame], None],
        analysis_callback: Optional[Callable[[VideoFrame], None]] = None
    ) -> None:
        """
        Start processing stream.

        Args:
            frame_callback: Callback for each captured frame
            analysis_callback: Callback for analysis results (less frequent)
        """
        if not self._cap or not self._cap.isOpened():
            if not self.connect():
                raise RuntimeError("Cannot connect to stream")

        self._frame_callback = frame_callback
        self._analysis_callback = analysis_callback
        self._running = True
        self._status = StreamStatus.PROCESSING

        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop processing"""
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        self._status = StreamStatus.IDLE

    def pause(self) -> None:
        """Pause processing"""
        self._paused = True
        self._status = StreamStatus.PAUSED

    def resume(self) -> None:
        """Resume processing"""
        self._paused = False
        self._status = StreamStatus.PROCESSING

    def _process_loop(self) -> None:
        """Main processing loop"""
        frame_index = 0

        while self._running:
            if self._paused:
                time.sleep(0.1)
                continue

            try:
                ret, frame = self._cap.read()

                if not ret:
                    # Stream ended or error
                    self._handle_stream_error()
                    break

                self._stats['frames_captured'] += 1
                self._stats['last_capture_time'] = datetime.now()

                # Create VideoFrame object
                video_frame = VideoFrame(
                    frame_id=uuid.uuid4().hex,
                    camera_id=self.camera_id,
                    timestamp=time.time(),
                    frame_index=frame_index,
                    data=frame,
                    width=self._width,
                    height=self._height,
                    fps=self._fps
                )

                # Analyze frame periodically
                if frame_index % self.analysis_interval == 0:
                    self._analyze_frame(video_frame)
                    if self._analysis_callback:
                        self._analysis_callback(video_frame)

                # Send frame to callback
                if self._frame_callback:
                    self._frame_callback(video_frame)

                # Store for motion detection
                self._last_frame = frame.copy()
                if self._last_gray is None:
                    self._last_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                frame_index += 1

            except Exception as e:
                self._stats['capture_errors'] += 1
                self._handle_stream_error()
                break

    def _analyze_frame(self, video_frame: VideoFrame) -> None:
        """Analyze frame for motion, brightness, etc."""
        frame = video_frame.data

        # Convert to grayscale for analysis
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Motion detection using frame differencing
        if self._last_gray is not None:
            diff = cv2.absdiff(gray, self._last_gray)
            motion_pixels = cv2.countNonZero(diff)
            total_pixels = diff.shape[0] * diff.shape[1]
            motion_score = motion_pixels / total_pixels

            video_frame.motion_score = motion_score
            video_frame.motion_detected = motion_score > self.motion_threshold

            if video_frame.motion_detected:
                self._stats['motion_events'] += 1

        # Brightness analysis
        video_frame.brightness = gray.mean() / 255.0

        # Sharpness analysis (Laplacian variance)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        video_frame.sharpness = laplacian.var() / 1000.0  # Normalize

        self._stats['frames_analyzed'] += 1

        # Update last gray for next comparison
        self._last_gray = gray.copy()

    def _handle_stream_error(self) -> None:
        """Handle stream error"""
        self._stats['capture_errors'] += 1
        self._running = False
        self._status = StreamStatus.ERROR

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return self._stats.copy()

    def get_stream_info(self) -> Dict[str, Any]:
        """Get stream information"""
        if not self._cap:
            return {}

        return {
            'camera_id': self.camera_id,
            'rtsp_url': self.rtsp_url,
            'status': self._status.value,
            'width': self._width,
            'height': self._height,
            'fps': self._fps,
            'motion_threshold': self.motion_threshold,
            'stats': self._stats
        }


class StreamProcessorPool:
    """
    Pool of video stream processors.

    Manages multiple camera streams efficiently.
    """

    def __init__(self, max_streams: int = 100):
        """
        Initialize stream pool.

        Args:
            max_streams: Maximum concurrent streams
        """
        self.max_streams = max_streams
        self._processors: Dict[str, VideoStreamProcessor] = {}
        self._lock = threading.Lock()

    def add_stream(
        self,
        camera_id: str,
        rtsp_url: str,
        **kwargs
    ) -> VideoStreamProcessor:
        """
        Add a stream to the pool.

        Args:
            camera_id: Unique camera identifier
            rtsp_url: RTSP stream URL
            **kwargs: Additional arguments for VideoStreamProcessor

        Returns:
            VideoStreamProcessor instance
        """
        with self._lock:
            if len(self._processors) >= self.max_streams:
                raise RuntimeError(f"Stream pool full (max: {self.max_streams})")

            if camera_id in self._processors:
                return self._processors[camera_id]

            processor = VideoStreamProcessor(camera_id, rtsp_url, **kwargs)
            self._processors[camera_id] = processor
            return processor

    def remove_stream(self, camera_id: str) -> None:
        """Remove a stream from the pool"""
        with self._lock:
            if camera_id in self._processors:
                self._processors[camera_id].disconnect()
                del self._processors[camera_id]

    def get_stream(self, camera_id: str) -> Optional[VideoStreamProcessor]:
        """Get stream processor"""
        return self._processors.get(camera_id)

    def start_all(
        self,
        frame_callback: Callable[[VideoFrame], None],
        analysis_callback: Optional[Callable[[VideoFrame], None]] = None
    ) -> None:
        """Start all streams"""
        for processor in self._processors.values():
            processor.start(frame_callback, analysis_callback)

    def stop_all(self) -> None:
        """Stop all streams"""
        for processor in self._processors.values():
            processor.stop()

    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all streams"""
        return {cid: p.get_stats() for cid, p in self._processors.items()}

    def __len__(self) -> int:
        """Number of streams in pool"""
        return len(self._processors)
