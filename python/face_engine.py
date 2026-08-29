"""
Sentinel X — face recognition engine, OpenCV/LBPH backend

Consolidated onto the teammate's original approach (Haar Cascade detection
+ cv2.face.LBPHFaceRecognizer) instead of face_recognition/dlib — see
STATUS_AND_PIVOT.md Section 6 for why. The public interface is unchanged
from the dlib-backed version, so auth_engine.py, dashboard.py, and
enroll_faces.py needed no modifications at all.

Requires opencv-contrib-python (not plain opencv-python) — the base
package doesn't ship cv2.face.

people.txt is the source of truth for whether anyone is enrolled. A
missing people.txt is treated as "nobody enrolled yet" even if an old
face_model.yml is sitting on disk, since a model with no label mapping
is unusable — see STATUS_AND_PIVOT.md Section 5.
"""

import logging
import os
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("sentinelx.face_engine")

DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "face_model.yml")
DEFAULT_PEOPLE_PATH = os.path.join(os.path.dirname(__file__), "people.txt")
DEFAULT_THRESHOLD = 70  # LBPH confidence: LOWER is a better match, matching the teammate's original tuning

CASCADE_DETECT_PARAMS = dict(scaleFactor=1.3, minNeighbors=5, minSize=(60, 60))


class FaceEngine:
    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        people_path: str = DEFAULT_PEOPLE_PATH,
        cascade_path: Optional[str] = None,
        threshold: float = DEFAULT_THRESHOLD,
    ):
        self._model_path = model_path
        self._people_path = people_path
        self._threshold = threshold

        cascade_path = cascade_path or os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        self._cascade = cv2.CascadeClassifier(cascade_path)
        if self._cascade.empty():
            raise RuntimeError(f"Could not load Haar Cascade from {cascade_path}")

        if not hasattr(cv2, "face"):
            raise RuntimeError(
                "cv2.face is not available -- install opencv-contrib-python "
                "(not plain opencv-python, which doesn't include it)"
            )
        self._recognizer = cv2.face.LBPHFaceRecognizer_create()

        self._people: list[str] = []
        self._trained = False
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load(self):
        if not os.path.exists(self._people_path):
            logger.info("No people.txt at %s -- treating as nobody enrolled yet", self._people_path)
            self._people = []
            self._trained = False
            return

        with open(self._people_path) as f:
            self._people = [line.strip() for line in f if line.strip()]

        if os.path.exists(self._model_path) and self._people:
            self._recognizer.read(self._model_path)
            self._trained = True
            logger.info("Loaded model for %d enrolled people: %s", len(self._people), self._people)
        else:
            logger.warning("people.txt exists but face_model.yml is missing -- treating as untrained")
            self._trained = False

    def _save(self):
        self._recognizer.save(self._model_path)
        with open(self._people_path, "w") as f:
            for name in self._people:
                f.write(name + "\n")

    # ------------------------------------------------------------------ #
    # Enrollment
    # ------------------------------------------------------------------ #

    def enroll_from_images(self, name: str, image_paths: list[str]) -> int:
        """
        Detect a face in each image and add it as a training sample for
        `name`. If `name` is already enrolled, new samples are added to
        their existing label via incremental update() rather than
        retraining from scratch. Returns the number of images that had a
        detectable face and were actually used.
        """
        faces = []
        for path in image_paths:
            image = cv2.imread(path)
            if image is None:
                logger.warning("Could not read image: %s", path)
                continue
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            detected = self._cascade.detectMultiScale(gray, **CASCADE_DETECT_PARAMS)
            if len(detected) == 0:
                logger.warning("No face detected in %s -- skipping", path)
                continue
            # Largest detected face wins if there's more than one in frame.
            x, y, w, h = max(detected, key=lambda box: box[2] * box[3])
            faces.append(gray[y:y + h, x:x + w])

        if not faces:
            logger.warning("No usable face samples for '%s' -- nothing enrolled", name)
            return 0

        if name in self._people:
            label = self._people.index(name)
        else:
            label = len(self._people)
            self._people.append(name)

        labels = np.array([label] * len(faces))

        if self._trained:
            self._recognizer.update(faces, labels)
        else:
            self._recognizer.train(faces, labels)
            self._trained = True

        self._save()
        logger.info("Enrolled %d/%d samples for '%s' (label %d)", len(faces), len(image_paths), name, label)
        return len(faces)

    def enrolled_people(self) -> list[str]:
        return list(self._people)

    # ------------------------------------------------------------------ #
    # Recognition
    # ------------------------------------------------------------------ #

    def recognize(self, frame: np.ndarray) -> tuple[Optional[str], Optional[float]]:
        """
        Given a BGR frame, return (name, confidence) for the best match,
        or (None, confidence) if a face was seen but nobody matched
        within tolerance, or (None, None) if no face was detected at all
        or nobody is enrolled yet.

        confidence is LBPH's own score -- lower is a stronger match, same
        "lower is better" convention the rest of the app already expects.
        """
        if not self._trained:
            return None, None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detected = self._cascade.detectMultiScale(gray, **CASCADE_DETECT_PARAMS)
        if len(detected) == 0:
            return None, None

        x, y, w, h = max(detected, key=lambda box: box[2] * box[3])
        face = gray[y:y + h, x:x + w]

        label, confidence = self._recognizer.predict(face)

        if confidence <= self._threshold and 0 <= label < len(self._people):
            return self._people[label], float(confidence)
        return None, float(confidence)
