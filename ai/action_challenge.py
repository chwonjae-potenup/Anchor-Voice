"""
Vision challenge generator and checker using MediaPipe FaceLandmarker.
"""
from __future__ import annotations

import logging
import os
import random
import urllib.request

import numpy as np

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

logger = logging.getLogger(__name__)

# Challenge actions.
ACTION_POOL = [
    {"id": "head_right", "text": "오른쪽으로 고개를 돌리세요"},
    {"id": "head_left", "text": "왼쪽으로 고개를 돌리세요"},
    {"id": "head_up", "text": "위를 올려보세요"},
    {"id": "head_down", "text": "아래를 내려보세요"},
    {"id": "head_tilt_left", "text": "고개를 왼쪽으로 기울여 보세요"},
    {"id": "head_tilt_right", "text": "고개를 오른쪽으로 기울여 보세요"},
    {"id": "head_center_hold", "text": "정면을 보고 잠시 유지해 주세요"},
    {"id": "blink_right", "text": "오른쪽 눈을 깜빡이세요"},
    {"id": "blink_left", "text": "왼쪽 눈을 깜빡이세요"},
    {"id": "double_blink_right", "text": "오른쪽 눈을 두 번 깜빡이세요"},
    {"id": "double_blink_left", "text": "왼쪽 눈을 두 번 깜빡이세요"},
    {"id": "mouth_open", "text": "입을 크게 벌리세요"},
    {"id": "mouth_close_after_open", "text": "입을 벌렸다가 다시 다무세요"},
]

LEFT_EYE_IDX = [362, 385, 387, 263, 373, 380]
RIGHT_EYE_IDX = [33, 160, 158, 133, 153, 144]
NOSE_TIP = 1
LEFT_CHEEK = 234
RIGHT_CHEEK = 454
MOUTH_TOP = 13
MOUTH_BOTTOM = 14

MODEL_ASSET_PATH = "face_landmarker.task"
_landmarker_detector = None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _sample_frames(frames: list[bytes]) -> list[bytes]:
    """
    Downsample long clips to keep detection latency stable.
    """
    max_frames = max(6, _env_int("FACE_SEQUENCE_MAX_FRAMES", 18))
    if len(frames) <= max_frames:
        return frames

    last_index = len(frames) - 1
    sampled_indices = {
        int(round(i * last_index / (max_frames - 1)))
        for i in range(max_frames)
    }
    sampled = [frames[i] for i in sorted(sampled_indices)]
    return sampled if len(sampled) >= 6 else frames[:max_frames]


def generate_challenge() -> dict:
    selected = random.sample(ACTION_POOL, 2)
    combined = f"{selected[0]['text']} 이어서, {selected[1]['text']}."
    return {
        "actions": selected,
        "combined_text": combined,
        "tts_text": combined,
    }


def _ensure_model_exists() -> None:
    if os.path.exists(MODEL_ASSET_PATH):
        return
    logger.info("Downloading %s ...", MODEL_ASSET_PATH)
    try:
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
            MODEL_ASSET_PATH,
        )
    except Exception as e:
        logger.error("FaceLandmarker model download failed: %s", e)


def _get_landmarker():
    global _landmarker_detector
    if _landmarker_detector is not None:
        return _landmarker_detector

    try:
        import mediapipe as mp  # noqa: F401
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        _ensure_model_exists()
        base_options = python.BaseOptions(model_asset_path=MODEL_ASSET_PATH)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=1,
        )
        _landmarker_detector = vision.FaceLandmarker.create_from_options(options)
    except Exception as e:
        logger.error("FaceLandmarker init failed: %s", e)
        return None

    return _landmarker_detector


def _get_face_landmarks(image_bytes: bytes):
    """
    Returns: (landmarks, height, width) or (None, None, None)
    """
    try:
        import cv2
        import mediapipe as mp

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None, None, None

        h, w = img.shape[:2]
        max_side = max(256, _env_int("FACE_FRAME_MAX_SIDE", 720))
        longest = max(h, w)
        if longest > max_side:
            scale = max_side / float(longest)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            h, w = img.shape[:2]

        detector = _get_landmarker()
        if detector is None:
            return None, h, w

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        results = detector.detect(mp_image)
        if not results.face_landmarks:
            return None, h, w
        return results.face_landmarks[0], h, w
    except Exception:
        return None, None, None


def detect_sequence_from_frames(frames_bytes: list[bytes], action1_id: str, action2_id: str) -> dict:
    """
    Validate that action1 is detected first, then action2 later in the clip.
    """
    if not frames_bytes:
        return {"detected": False, "confidence": 0.0, "reason": "프레임이 없습니다."}

    original_count = len(frames_bytes)
    frames_bytes = _sample_frames(frames_bytes)
    if len(frames_bytes) != original_count:
        logger.info("Video Sequence frame sampling: %d -> %d", original_count, len(frames_bytes))

    landmarks_list = []
    for fb in frames_bytes:
        lm, _, _ = _get_face_landmarks(fb)
        landmarks_list.append(lm)

    valid_faces = sum(1 for x in landmarks_list if x is not None)
    logger.info("Video Sequence: %d frames (Valid faces: %d)", len(landmarks_list), valid_faces)

    if valid_faces < 5:
        return {"detected": False, "confidence": 0.0, "reason": "영상에서 얼굴이 충분히 인식되지 않았습니다."}

    act1_idx = _find_action(landmarks_list, 0, action1_id)
    if act1_idx == -1:
        return {"detected": False, "confidence": 0.0, "reason": f"첫 동작 '{action1_id}'을 감지하지 못했습니다."}

    act2_idx = _find_action(landmarks_list, act1_idx, action2_id)
    if act2_idx == -1:
        return {
            "detected": False,
            "confidence": 0.0,
            "reason": f"두 번째 동작 '{action2_id}'을 감지하지 못했습니다. (frame {act1_idx} 이후)",
        }

    return {
        "detected": True,
        "confidence": 0.99,
        "reason": f"순서 감지 성공: {action1_id} (frame {act1_idx}) -> {action2_id} (frame {act2_idx})",
    }


def detect_action_from_frame(frame_bytes: bytes, action_id: str) -> dict:
    """
    Single-frame action check for /api/auth/face/action compatibility.
    """
    lm, _, _ = _get_face_landmarks(frame_bytes)
    if lm is None:
        return {"detected": False, "confidence": 0.0, "reason": "얼굴을 감지하지 못했습니다."}

    if action_id in {"blink_right", "blink_left", "double_blink_right", "double_blink_left"}:
        eye = "right" if "right" in action_id else "left"
        ear = _calc_ear(lm, eye)
        threshold = 0.22
        detected = ear < threshold
        return {
            "detected": detected,
            "confidence": 0.9 if detected else 0.2,
            "reason": f"blink_check ear={ear:.3f}, threshold={threshold:.2f}",
        }

    if action_id == "mouth_close_after_open":
        # Sequence action cannot be fully verified with one frame.
        return {"detected": False, "confidence": 0.0, "reason": "단일 프레임으로 검증할 수 없는 동작입니다."}

    detected = _check_static_action(action_id, lm)
    return {
        "detected": detected,
        "confidence": 0.9 if detected else 0.2,
        "reason": f"static_action_check action={action_id}",
    }


def _find_action(landmarks_list: list, start_idx: int, action_id: str) -> int:
    if action_id in {"blink_right", "blink_left"}:
        eye = "right" if "right" in action_id else "left"
        return _find_n_blinks(landmarks_list, start_idx, len(landmarks_list) - 1, eye, target_count=1)

    if action_id in {"double_blink_right", "double_blink_left"}:
        eye = "right" if "right" in action_id else "left"
        return _find_n_blinks(landmarks_list, start_idx, len(landmarks_list) - 1, eye, target_count=2)

    if action_id == "mouth_close_after_open":
        return _find_mouth_open_close(landmarks_list, start_idx, len(landmarks_list) - 1)

    if action_id == "head_center_hold":
        return _find_head_center_hold(landmarks_list, start_idx, len(landmarks_list) - 1)

    for i in range(start_idx, len(landmarks_list)):
        lm = landmarks_list[i]
        if lm and _check_static_action(action_id, lm):
            return i
    return -1


def _find_n_blinks(
    landmarks_list: list,
    start_idx: int,
    end_idx: int,
    eye: str,
    target_count: int = 1,
) -> int:
    blink_min = 0.22
    blink_drop = 0.07

    state = "OPEN"
    closed_min_ear = 9.9
    close_start_ear = -1.0
    ear_values: list[tuple[int, float]] = []
    blink_count = 0

    for i in range(start_idx, end_idx + 1):
        lm = landmarks_list[i]
        if not lm:
            continue

        ear = _calc_ear(lm, eye)
        ear_values.append((i, ear))

        if state == "OPEN":
            if ear < blink_min:
                state = "CLOSED"
                closed_min_ear = ear
                close_start_ear = max([e for _, e in ear_values[-5:]] if ear_values else [ear])
        elif state == "CLOSED":
            closed_min_ear = min(closed_min_ear, ear)
            if ear > blink_min + 0.03:
                if close_start_ear - closed_min_ear >= blink_drop:
                    blink_count += 1
                    if blink_count >= target_count:
                        return i
                state = "OPEN"

    return -1


def _find_mouth_open_close(landmarks_list: list, start_idx: int, end_idx: int) -> int:
    opened = False
    open_threshold = 0.045
    close_threshold = 0.026
    for i in range(start_idx, end_idx + 1):
        lm = landmarks_list[i]
        if not lm:
            continue
        gap = _mouth_gap(lm)
        if not opened and gap > open_threshold:
            opened = True
        elif opened and gap < close_threshold:
            return i
    return -1


def _find_head_center_hold(landmarks_list: list, start_idx: int, end_idx: int) -> int:
    hold_frames = max(2, _env_int("FACE_CENTER_HOLD_FRAMES", 4))
    streak = 0
    for i in range(start_idx, end_idx + 1):
        lm = landmarks_list[i]
        if not lm:
            streak = 0
            continue
        if _check_head_center(lm):
            streak += 1
            if streak >= hold_frames:
                return i
        else:
            streak = 0
    return -1


def _calc_ear(lm, eye: str) -> float:
    idx = RIGHT_EYE_IDX if eye == "right" else LEFT_EYE_IDX

    def dist(i: int, j: int) -> float:
        return np.linalg.norm(np.array([lm[i].x, lm[i].y]) - np.array([lm[j].x, lm[j].y]))

    a = dist(idx[1], idx[5])
    b = dist(idx[2], idx[4])
    c = dist(idx[0], idx[3])
    return (a + b) / (2.0 * c + 1e-6)


def _mouth_gap(lm) -> float:
    return abs(lm[MOUTH_BOTTOM].y - lm[MOUTH_TOP].y)


def _check_static_action(action_id: str, lm) -> bool:
    if action_id == "head_right":
        return _check_head_horizontal(lm, direction="right")
    if action_id == "head_left":
        return _check_head_horizontal(lm, direction="left")
    if action_id == "head_up":
        return _check_head_up(lm)
    if action_id == "head_down":
        return _check_head_down(lm)
    if action_id == "head_tilt_left":
        return _check_head_tilt(lm, direction="left")
    if action_id == "head_tilt_right":
        return _check_head_tilt(lm, direction="right")
    if action_id == "head_center_hold":
        return _check_head_center(lm)
    if action_id == "mouth_open":
        return _check_mouth_open(lm)
    return False


def _check_head_horizontal(lm, direction: str) -> bool:
    nose_x = lm[NOSE_TIP].x
    left_x = lm[LEFT_CHEEK].x
    right_x = lm[RIGHT_CHEEK].x
    center = (left_x + right_x) / 2
    offset = (nose_x - center) / (right_x - left_x + 1e-6)
    threshold = 0.12
    return (offset < -threshold) if direction == "right" else (offset > threshold)


def _check_head_up(lm) -> bool:
    return lm[NOSE_TIP].y < 0.40


def _check_head_down(lm) -> bool:
    return lm[NOSE_TIP].y > 0.58


def _check_head_center(lm) -> bool:
    nose_x = lm[NOSE_TIP].x
    left_x = lm[LEFT_CHEEK].x
    right_x = lm[RIGHT_CHEEK].x
    center = (left_x + right_x) / 2
    offset = abs((nose_x - center) / (right_x - left_x + 1e-6))
    return offset < 0.06


def _check_head_tilt(lm, direction: str) -> bool:
    left_eye_y = lm[LEFT_EYE_IDX[0]].y
    right_eye_y = lm[RIGHT_EYE_IDX[0]].y
    delta = left_eye_y - right_eye_y
    threshold = 0.025
    return (delta > threshold) if direction == "left" else (delta < -threshold)


def _check_mouth_open(lm) -> bool:
    return _mouth_gap(lm) > 0.04
