# -*- coding: utf-8 -*-
"""
RTSP Video Source Adapter

Connects to RTSP streams from IP cameras.
"""

import time
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Dict, Any
import uuid


class StreamStatus(Enum):
    """Stream connection status"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class Frame:
    """Video frame data"""
    frame_id: str
    timestamp: float
    data: bytes
    width: int = 1920
    height: int = 1080
    fps: float = 30.0

    def __post_init__(self):
        if not self.frame_id:
            self.frame_id = uuid.uuid4().hex


class RTSPAdapter:
    """
    Adapter for connecting to RTSP video streams.

    Features:
    - Connection management with auto-reconnect
    - Frame extraction
    - Stream status monitoring
    - Callback-based frame handling

    Note: This is a simulation. Real implementation requires OpenCV or similar.
    In production, use:
        import cv2
        self.cap = cv2.VideoCapture(rtsp_url)
    """

    def __init__(
        self,
        rtsp_url: str,
        camera_id: str,
        buffer_size: int = 30,
        reconnect_interval: int = 5
    ):
        """
        Initialize RTSP adapter.

        Args:
            rtsp_url: RTSP stream URL
            camera_id: Unique camera identifier
            buffer_size: Number of frames to buffer
            reconnect_interval: Seconds between reconnect attempts
        """
        self.rtsp_url = rtsp_url
        self.camera_id = camera_id
        self.buffer_size = buffer_size
        self.reconnect_interval = reconnect_interval

        self._status = StreamStatus.DISCONNECTED
        self._frames: list = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_callback: Optional[Callable] = None

        # Statistics
        self._stats = {
            'frames_received': 0,
            'frames_dropped': 0,
            'bytes_received': 0,
            'last_frame_time': None,
            'connection_errors': 0
        }

        # Simulated flag (set to True in production with OpenCV)
        self._simulated = True

    @property
    def status(self) -> StreamStatus:
        """Get current stream status"""
        return self._status

    @property
    def is_connected(self) -> bool:
        """Check if stream is connected"""
        return self._status == StreamStatus.CONNECTED

    def connect(self) -> bool:
        """
        Connect to RTSP stream.

        Returns:
            True if connection successful
        """
        if self._status == StreamStatus.CONNECTED:
            return True

        self._status = StreamStatus.CONNECTING

        try:
            if self._simulated:
                # Simulated connection
                self._status = StreamStatus.CONNECTED
                return True

            # Real implementation would be:
            # import cv2
            # self.cap = cv2.VideoCapture(self.rtsp_url)
            # if not self.cap.isOpened():
            #     raise ConnectionError(f"Cannot open stream: {self.rtsp_url}")
            # self._status = StreamStatus.CONNECTED

        except Exception as e:
            self._status = StreamStatus.ERROR
            self._stats['connection_errors'] += 1
            raise ConnectionError(f"Failed to connect to {self.rtsp_url}: {e}")

        return False

    def disconnect(self) -> None:
        """Disconnect from stream"""
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        self._status = StreamStatus.DISCONNECTED

        if not self._simulated:
            pass
            # Real: self.cap.release()

    def start(self, frame_callback: Callable[[Frame], None]) -> None:
        """
        Start processing stream.

        Args:
            frame_callback: Callback function for each frame
        """
        if not self.is_connected:
            self.connect()

        self._frame_callback = frame_callback
        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop processing stream"""
        self._running = False

    def _stream_loop(self) -> None:
        """Main streaming loop"""
        while self._running and self.is_connected:
            try:
                if self._simulated:
                    # Simulate frame capture
                    frame = self._generate_simulated_frame()
                else:
                    # Real implementation:
                    # ret, frame = self.cap.read()
                    # if not ret:
                    #     self._handle_disconnect()
                    #     break
                    pass

                # Process frame
                if self._frame_callback:
                    self._frame_callback(frame)

                # Update stats
                self._stats['frames_received'] += 1
                self._stats['bytes_received'] += len(frame.data)
                self._stats['last_frame_time'] = datetime.now()

                # Simulate real-time frame rate
                time.sleep(1 / 30)  # 30 fps

            except Exception as e:
                self._stats['connection_errors'] += 1
                self._handle_error(e)

    def _generate_simulated_frame(self) -> Frame:
        """Generate simulated frame data"""
        # Simulated frame - in production this would be real frame data
        timestamp = time.time()
        frame_data = b'SIMULATED_FRAME_DATA_' + str(timestamp).encode()

        return Frame(
            frame_id=uuid.uuid4().hex,
            timestamp=timestamp,
            data=frame_data,
            width=1920,
            height=1080,
            fps=30.0
        )

    def _handle_disconnect(self) -> None:
        """Handle stream disconnection"""
        self._status = StreamStatus.DISCONNECTED
        self._stats['frames_dropped'] += 1

    def _handle_error(self, error: Exception) -> None:
        """Handle stream error"""
        self._status = StreamStatus.ERROR
        self._stats['connection_errors'] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get stream statistics"""
        return self._stats.copy()

    def get_info(self) -> Dict[str, Any]:
        """Get stream information"""
        return {
            'camera_id': self.camera_id,
            'rtsp_url': self.rtsp_url,
            'status': self._status.value,
            'is_connected': self.is_connected,
            'simulated': self._simulated,
            'stats': self._stats
        }


class RTSPConnectionPool:
    """
    Pool of RTSP connections for multiple cameras.

    Manages connection lifecycle and resource usage.
    """

    def __init__(self, max_connections: int = 100):
        """
        Initialize connection pool.

        Args:
            max_connections: Maximum number of concurrent connections
        """
        self.max_connections = max_connections
        self._connections: Dict[str, RTSPAdapter] = {}
        self._lock = threading.Lock()

    def add_camera(
        self,
        camera_id: str,
        rtsp_url: str,
        **kwargs
    ) -> RTSPAdapter:
        """
        Add a camera to the pool.

        Args:
            camera_id: Unique camera identifier
            rtsp_url: RTSP stream URL
            **kwargs: Additional arguments for RTSPAdapter

        Returns:
            RTSPAdapter instance
        """
        with self._lock:
            if len(self._connections) >= self.max_connections:
                raise RuntimeError(f"Connection pool full (max: {self.max_connections})")

            if camera_id in self._connections:
                return self._connections[camera_id]

            adapter = RTSPAdapter(rtsp_url, camera_id, **kwargs)
            self._connections[camera_id] = adapter
            return adapter

    def remove_camera(self, camera_id: str) -> None:
        """Remove a camera from the pool"""
        with self._lock:
            if camera_id in self._connections:
                adapter = self._connections[camera_id]
                adapter.disconnect()
                del self._connections[camera_id]

    def get_camera(self, camera_id: str) -> Optional[RTSPAdapter]:
        """Get camera adapter"""
        return self._connections.get(camera_id)

    def connect_all(self) -> Dict[str, bool]:
        """Connect to all cameras"""
        results = {}
        for camera_id, adapter in self._connections.items():
            try:
                results[camera_id] = adapter.connect()
            except Exception as e:
                results[camera_id] = False
        return results

    def disconnect_all(self) -> None:
        """Disconnect all cameras"""
        for adapter in self._connections.values():
            adapter.disconnect()

    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all cameras"""
        return {cid: adapter.get_stats() for cid, adapter in self._connections.items()}

    def __len__(self) -> int:
        """Number of cameras in pool"""
        return len(self._connections)
