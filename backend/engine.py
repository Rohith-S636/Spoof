"""Face models: detection (YuNet), liveness (MiniFASNetV2), identity (SFace).

All three run locally on CPU, so the kiosk works without a network.
"""
from __future__ import annotations

import threading

import cv2
import numpy as np
import onnxruntime as ort

from config import MINIFAS, MINIFAS_SE, SFACE, TEXTURE_PAD, YUNET

PAD_SIZE = 80       # both liveness models take 80x80 input
# Two liveness models that look at different amounts of background around the
# face (2.7x and 4x the face box). Averaging them is steadier than either alone.
# Measured 14 Nov: the 4x model scored about 0.9 for phone screens as well as real
# faces, so averaging it in hid every spoof. Only the 2.7x model is used.
PAD_MODELS = [(MINIFAS, 2.7)]


class FaceEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()   # OpenCV detector is not thread-safe
        self.det = cv2.FaceDetectorYN.create(str(YUNET), "", (320, 320), 0.7, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(str(SFACE), "")
        self.pads = [(ort.InferenceSession(str(p), providers=["CPUExecutionProvider"]), s)
                     for p, s in PAD_MODELS if p.exists()]
        # Second opinion: trained separately (CelebA-Spoof), looks closely at skin
        # texture (1.5x crop at 128 px) instead of the surroundings.
        self.tex = (ort.InferenceSession(str(TEXTURE_PAD), providers=["CPUExecutionProvider"])
                    if TEXTURE_PAD.exists() else None)

    # -- individual steps ----------------------------------------------------
    def detect(self, img: np.ndarray) -> np.ndarray:
        """Return faces as rows [x, y, w, h, 10 landmark values, score], largest first."""
        h, w = img.shape[:2]
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(img)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)
        return faces[np.argsort(-(faces[:, 2] * faces[:, 3]))]

    def live_probs(self, img: np.ndarray, face: np.ndarray) -> list[float]:
        """Per model: probability (0..1) that the face is real, not a photo or screen."""
        out = [self._live_one(img, face, sess, scale) for sess, scale in self.pads]
        if self.tex is not None:
            out.append(self._live_texture(img, face))
        return out

    def _live_texture(self, img: np.ndarray, face: np.ndarray) -> float:
        x, y, bw, bh = [float(v) for v in face[:4]]
        size = int(max(bw, bh) * 1.5)
        x0, y0 = int(x + bw / 2 - size / 2), int(y + bh / 2 - size / 2)
        h, w = img.shape[:2]
        crop = img[max(0, y0):min(h, y0 + size), max(0, x0):min(w, x0 + size)]
        if crop.size == 0:
            return 0.0
        crop = cv2.copyMakeBorder(crop, max(0, -y0), max(0, y0 + size - h), max(0, -x0),
                                  max(0, x0 + size - w), cv2.BORDER_REFLECT_101)
        crop = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), (128, 128),
                          interpolation=cv2.INTER_AREA if size > 128 else cv2.INTER_LANCZOS4)
        blob = (crop.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        real, spoof = self.tex.run(None, {self.tex.get_inputs()[0].name: blob})[0][0][:2]
        return float(1.0 / (1.0 + np.exp(-(float(real) - float(spoof)))))

    def _live_one(self, img, face, sess, pad_scale) -> float:
        src_h, src_w = img.shape[:2]
        x, y, bw, bh = [float(v) for v in face[:4]]
        bw, bh = max(bw, 1.0), max(bh, 1.0)
        scale = min((src_h - 1) / bh, (src_w - 1) / bw, pad_scale)
        nw, nh = bw * scale, bh * scale
        cx, cy = x + bw / 2, y + bh / 2
        x1, y1 = max(0, int(cx - nw / 2)), max(0, int(cy - nh / 2))
        x2, y2 = min(src_w - 1, int(cx + nw / 2)), min(src_h - 1, int(cy + nh / 2))
        crop = cv2.resize(img[y1:y2 + 1, x1:x2 + 1], (PAD_SIZE, PAD_SIZE))
        blob = crop.astype(np.float32).transpose(2, 0, 1)[None]   # BGR, 0..255
        logits = sess.run(None, {sess.get_inputs()[0].name: blob})[0][0]
        e = np.exp(logits - logits.max())
        return float((e / e.sum())[1])                             # class 1 = real

    def embed(self, img: np.ndarray, face: np.ndarray) -> np.ndarray:
        """128-number identity vector, unit length."""
        feat = self.rec.feature(self.rec.alignCrop(img, face)).flatten()
        return feat / (np.linalg.norm(feat) + 1e-9)

    def yaw_track(self, frames: list[np.ndarray]) -> list[float | None]:
        """Head-turn measurement for each frame (None where no face was found)."""
        out = []
        with self._lock:
            for img in frames:
                faces = self.detect(img)
                out.append(yaw_ratio(faces[0]) if len(faces) else None)
        return out

    # -- whole pipeline for a burst of frames ---------------------------------
    def analyse(self, frames: list[np.ndarray]) -> dict:
        lives, embs, widths, ratios, extra_faces = [], [], [], [], 0
        with self._lock:
            for img in frames:
                faces = self.detect(img)
                if len(faces) == 0:
                    continue
                main = faces[0]
                # a second face nearly as large as the first is suspicious
                if len(faces) > 1 and faces[1][2] * faces[1][3] > 0.3 * main[2] * main[3]:
                    extra_faces += 1
                lives.append(self.live_probs(img, main))
                ratios.append(float(main[3]) / img.shape[0])
                embs.append(self.embed(img, main))
                widths.append(float(main[2]))
        if not lives:
            return {"faces": 0}
        emb = np.mean(embs, axis=0)
        return {
            "faces": 2 if extra_faces else 1,
            "frames_used": len(lives),
            # "live" is the average of the liveness models over all frames. On our
            # samples the average separated real faces from phone screens; either
            # model alone did not. A very low single model is still a veto (policy).
            "live": float(np.mean(lives)),
            "live_mean": float(np.mean(lives)),
            "live_min": float(np.min(lives)),
            "live_models": [float(v) for v in np.mean(lives, axis=0)],
            "face_ratio": float(np.mean(ratios)),
            "face_px": float(np.mean(widths)),
            "embedding": emb / (np.linalg.norm(emb) + 1e-9),
        }


def yaw_ratio(face: np.ndarray) -> float:
    """How far the nose sits from the midpoint of the eyes, in eye-distances.

    About 0 when facing the camera. Goes negative when the person turns to their
    right, positive to their left. A flat photo or screen cannot change it much.
    """
    right_eye_x, left_eye_x, nose_x = float(face[4]), float(face[6]), float(face[8])
    return (nose_x - (right_eye_x + left_eye_x) / 2) / max(abs(left_eye_x - right_eye_x), 1.0)


def decode(data: bytes) -> np.ndarray | None:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
