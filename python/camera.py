"""
Sentinel X — video stream (Phase 6)

Wraps frame acquisition behind one interface so the rest of the app never
touches cv2.VideoCapture directly. Two backends:

    VideoStream(source=0)                  # real webcam, index 0
    VideoStream(source="path/to/images/")   # cycles through image files —
                                             # same "fake hardware" pattern
                                             # as fake_esp32.py, for testing
                                             # without a physical camera

Runs frame capture on its own thread so callers always get the latest
frame instantly via get_frame() rather than blocking on I/O.
"""

import glob
import logging
import os
import threading
import time
from typing import Optional, Union

import cv2
import numpy as np

logger = logging.getLogger("sentinelx.camera")

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")


class VideoStream:
    def __init__(self, source: Union[int, str] = 0, fake_frame_interval: float = 1.0):
        """
        source: int camera index for a real webcam, or a directory path
                containing image files to cycle through as fake frames.
        fake_frame_interval: seconds between advancing to the next fake
                image (ignored for real webcams, which just read continuously).
        """
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._is_fake = isinstance(source, str)
        if self._is_fake:
            self._fake_images = sorted(
                p for p in glob.glob(os.path.join(source, "*")) if p.lower().endswith(IMAGE_EXTENSIONS)
            )
            if not self._fake_images:
                raise ValueError(f"No image files found in fake camera directory: {source}")
            logger.info("Using fake camera: %d test images from %s", len(self._fake_images), source)
            self._fake_interval = fake_frame_interval
            self._cap = None
        else:
            self._cap = cv2.VideoCapture(source)
            if not self._cap.isOpened():
                raise RuntimeError(f"Could not open camera at index {source}")
            self._fake_images = []

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap:
            self._cap.release()

    def _loop(self):
        if self._is_fake:
            self._loop_fake()
        else:
            self._loop_real()

    def _loop_real(self):
        while self._running:
            ok, frame = self._cap.read()
            if ok:
                with self._lock:
                    self._latest_frame = frame
            else:
                logger.warning("Failed to read frame from camera")
                time.sleep(0.5)

    def _loop_fake(self):
        idx = 0
        while self._running:
            path = self._fake_images[idx % len(self._fake_images)]
            frame = cv2.imread(path)
            if frame is not None:
                with self._lock:
                    self._latest_frame = frame
            else:
                logger.warning("Could not read fake frame: %s", path)
            idx += 1
            time.sleep(self._fake_interval)

    def get_frame(self) -> Optional[np.ndarray]:
        """Returns the most recent frame (BGR, as OpenCV expects), or None
        if nothing has been captured yet."""
        with self._lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    def capture_to_file(self, path: str) -> bool:
        """Save the current frame to disk. Returns True on success."""
        frame = self.get_frame()
        if frame is None:
            logger.warning("capture_to_file: no frame available yet")
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cv2.imwrite(path, frame)
        return True
