"""
Face verification module.

Policy:
- Retry in face flow for user/input issues (no face, photo/screen spoof suspicion, mismatch).
- Fallback to voice auth only for system-level failures.
"""
from __future__ import annotations

import inspect
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

# DeepFace/TensorFlow compatibility guards
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

logger = logging.getLogger(__name__)

REGISTERED_FACE_PATH = str((Path(__file__).resolve().parent.parent / "registered_face.jpg"))
_prewarmed_models: set[str] = set()


def _face_model_name() -> str:
    return os.getenv("DEEPFACE_MODEL_NAME", "ArcFace")


def _face_fallback_model_name() -> str:
    return os.getenv("DEEPFACE_MODEL_FALLBACK", "VGG-Face")


def _face_detector_backend() -> str:
    return os.getenv("DEEPFACE_DETECTOR_BACKEND", "opencv")


def _face_detector_backends() -> list[str]:
    raw = os.getenv("DEEPFACE_DETECTOR_BACKENDS", "").strip()
    if raw:
        candidates = [x.strip() for x in raw.split(",") if x.strip()]
    else:
        candidates = [_face_detector_backend()]

    # Always include legacy single backend var as fallback to keep compatibility.
    legacy = _face_detector_backend().strip()
    if legacy:
        candidates.append(legacy)

    deduped: list[str] = []
    seen: set[str] = set()
    for backend in candidates:
        key = backend.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(backend)
    return deduped or ["opencv"]


def _face_distance_metric() -> str:
    return os.getenv("DEEPFACE_DISTANCE_METRIC", "cosine")


DEFAULT_DISTANCE_THRESHOLDS: dict[tuple[str, str], float] = {
    ("vgg-face", "cosine"): 0.68,
    ("vgg-face", "euclidean"): 1.17,
    ("vgg-face", "euclidean_l2"): 1.17,
    ("facenet", "cosine"): 0.40,
    ("facenet", "euclidean"): 10.0,
    ("facenet", "euclidean_l2"): 0.80,
    ("arcface", "cosine"): 0.68,
    ("arcface", "euclidean"): 4.15,
    ("arcface", "euclidean_l2"): 1.13,
}

DEFAULT_HARD_MAX_THRESHOLDS: dict[tuple[str, str], float] = {
    # Conservative, but not over-tight to avoid false rejects for real user.
    ("vgg-face", "cosine"): 0.56,
    ("vgg-face", "euclidean_l2"): 0.86,
    ("arcface", "cosine"): 0.52,
    ("arcface", "euclidean_l2"): 0.92,
    ("facenet", "cosine"): 0.35,
}

SECONDARY_METRIC_BY_PRIMARY = {
    "cosine": "euclidean_l2",
    "euclidean_l2": "cosine",
    "euclidean": "cosine",
}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float env %s=%s, use default %.4f", name, raw, default)
        return default


def _resolve_strict_threshold(model_name: str, distance_metric: str, verify_result: dict) -> float:
    """
    Resolve strict pass threshold for 1:1 verification.

    Priority:
    1) DEEPFACE_VERIFY_MAX_DISTANCE (absolute)
    2) verify_result.threshold (from DeepFace)
    3) internal fallback table by model+metric
    Then apply DEEPFACE_STRICT_MULTIPLIER for tighter matching.
    """
    env_override = os.getenv("DEEPFACE_VERIFY_MAX_DISTANCE")
    if env_override:
        try:
            return float(env_override)
        except ValueError:
            logger.warning("Invalid DEEPFACE_VERIFY_MAX_DISTANCE=%s", env_override)

    result_threshold = verify_result.get("threshold")
    if isinstance(result_threshold, (float, int)):
        base_threshold = float(result_threshold)
    else:
        key = (model_name.lower(), distance_metric.lower())
        base_threshold = DEFAULT_DISTANCE_THRESHOLDS.get(key, 0.68)

    strict_multiplier = _env_float("DEEPFACE_STRICT_MULTIPLIER", 0.82)
    min_threshold = _env_float("DEEPFACE_MIN_DISTANCE_THRESHOLD", 0.15)
    strict_threshold = max(min_threshold, base_threshold * strict_multiplier)
    key = (model_name.lower(), distance_metric.lower())
    hard_cap = _env_float(
        "DEEPFACE_HARD_MAX_DISTANCE",
        DEFAULT_HARD_MAX_THRESHOLDS.get(key, strict_threshold),
    )
    strict_threshold = min(strict_threshold, hard_cap)
    return strict_threshold


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _secondary_metric(primary_metric: str) -> str:
    return SECONDARY_METRIC_BY_PRIMARY.get(primary_metric.lower(), "cosine")


def _get_deepface():
    try:
        from deepface import DeepFace

        return DeepFace
    except Exception as e:
        logger.error("DeepFace import failed: %s", e)
        return None


def _elapsed_ms(start: float) -> int:
    return int((time.time() - start) * 1000)


def _retry_result(start: float, message: str, distance: float | None = None) -> dict:
    return {
        "verified": False,
        "distance": distance,
        "threshold": None,
        "time_ms": _elapsed_ms(start),
        "fallback": False,
        "message": message,
    }


def _fallback_result(start: float, message: str) -> dict:
    return {
        "verified": False,
        "distance": None,
        "threshold": None,
        "time_ms": _elapsed_ms(start),
        "fallback": True,
        "message": message,
    }


def _extract_faces_with_optional_antispoof(DeepFace: Any, img_path: str) -> tuple[bool, str, bool]:
    """
    Returns:
      (ok, reason, retryable)
      - retryable=True: stay in face flow and ask user to retry capture.
      - retryable=False: system issue, allow voice fallback.
    """
    try:
        sig = inspect.signature(DeepFace.extract_faces)
        supports_antispoof = "anti_spoofing" in sig.parameters
    except Exception:
        supports_antispoof = False
    liveness_soft_bypass = _env_bool("DEEPFACE_LIVENESS_SOFT_BYPASS", True)
    detector_backends = _face_detector_backends()
    saw_detection_miss = False
    hard_errors: list[str] = []

    for detector_backend in detector_backends:
        kwargs = {
            "img_path": img_path,
            "enforce_detection": True,
            "detector_backend": detector_backend,
            "align": True,
        }
        if supports_antispoof:
            kwargs["anti_spoofing"] = True

        try:
            faces = DeepFace.extract_faces(**kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "face could not be detected" in msg or "no face" in msg:
                saw_detection_miss = True
                logger.info("extract_faces miss (%s): %s", detector_backend, e)
                continue
            hard_errors.append(f"{detector_backend}: {e}")
            logger.warning("extract_faces failed (%s): %s", detector_backend, e)
            continue

        if not faces:
            saw_detection_miss = True
            logger.info("extract_faces empty (%s)", detector_backend)
            continue

        face = faces[0] if isinstance(faces, list) else {}
        is_real = face.get("is_real")
        antispoof_score = face.get("antispoof_score", face.get("anti_spoof_score"))

        if is_real is False:
            if liveness_soft_bypass:
                # Anti-spoof can produce false negatives on glasses reflection.
                # Re-check without anti-spoof and continue only when a valid face is detected.
                try:
                    bypass_faces = DeepFace.extract_faces(
                        img_path=img_path,
                        enforce_detection=True,
                        detector_backend=detector_backend,
                        align=True,
                    )
                    if bypass_faces:
                        logger.warning(
                            "Liveness soft-bypass used (%s, score=%s). Verify stage remains strict.",
                            detector_backend,
                            antispoof_score,
                        )
                        return True, "", True
                except Exception as e:
                    logger.info("Liveness bypass check failed (%s): %s", detector_backend, e)

            if isinstance(antispoof_score, (float, int)):
                msg = f"실사 얼굴이 아닌 것으로 감지되었습니다(score={antispoof_score:.3f}). 실제 얼굴로 다시 인증해 주세요."
            else:
                msg = "실사 얼굴이 아닌 것으로 감지되었습니다. 실제 얼굴로 다시 인증해 주세요."
            return False, msg, True

        if not supports_antispoof:
            logger.warning("anti_spoofing is not supported in current DeepFace version.")

        return True, "", True

    if saw_detection_miss:
        return (
            False,
            "얼굴이 감지되지 않았습니다. 안경 반사를 줄이고 정면에서 다시 촬영해 주세요.",
            True,
        )

    if hard_errors:
        return False, "안면 검증 엔진 오류가 발생했습니다.", False

    return (
        False,
        "얼굴이 감지되지 않았습니다. 본인 얼굴이 화면 중앙에 오도록 다시 촬영해 주세요.",
        True,
    )


def prewarm_model() -> bool:
    """
    Preload deepface model to avoid first-request latency spikes.
    """
    DeepFace = _get_deepface()
    if DeepFace is None:
        return False

    requested = _face_model_name()
    fallback = _face_fallback_model_name()
    candidates = [requested]
    if fallback not in candidates:
        candidates.append(fallback)

    for model_name in candidates:
        if model_name in _prewarmed_models:
            return True
        try:
            DeepFace.build_model(model_name)
            _prewarmed_models.add(model_name)
            logger.info("DeepFace model prewarmed: %s", model_name)
            return True
        except Exception as e:
            logger.warning("DeepFace prewarm failed (%s): %s", model_name, e)

    return False


def verify_face_from_bytes(
    image_bytes: bytes,
    registered_image_path: str = REGISTERED_FACE_PATH,
) -> dict:
    """
    Compare camera frame against registered face with optional liveness pre-check.
    """
    start = time.time()

    if not Path(registered_image_path).exists():
        logger.warning("Registered face not found: %s", registered_image_path)
        return _fallback_result(start, "등록된 얼굴이 없습니다. 먼저 안면 등록을 진행해 주세요.")

    DeepFace = _get_deepface()
    if DeepFace is None:
        return _fallback_result(start, "안면 인식 모듈 로드 실패로 음성 인증으로 전환합니다.")

    # Best-effort warmup. Verification can still proceed if warmup fails.
    prewarm_model()
    requested_model_name = _face_model_name()
    fallback_model_name = _face_fallback_model_name()
    model_candidates = [requested_model_name]
    if fallback_model_name not in model_candidates:
        model_candidates.append(fallback_model_name)
    detector_backends = _face_detector_backends()
    distance_metric = _face_distance_metric()

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        ok, reason, retryable = _extract_faces_with_optional_antispoof(DeepFace, tmp_path)
        if not ok:
            logger.warning("Liveness/pre-check failed: %s", reason)
            if retryable:
                return _retry_result(start, reason)
            return _fallback_result(start, f"{reason} 음성 인증으로 전환합니다.")

        result = None
        used_model_name = requested_model_name
        last_verify_error = None
        used_detector_backend = detector_backends[0]
        for model_name in model_candidates:
            for detector_backend in detector_backends:
                try:
                    result = DeepFace.verify(
                        img1_path=tmp_path,
                        img2_path=registered_image_path,
                        model_name=model_name,
                        detector_backend=detector_backend,
                        distance_metric=distance_metric,
                        enforce_detection=True,
                        silent=True,
                    )
                    used_model_name = model_name
                    used_detector_backend = detector_backend
                    if model_name != requested_model_name:
                        logger.warning("DeepFace verify fallback model used: %s", model_name)
                    if detector_backend != detector_backends[0]:
                        logger.warning("DeepFace verify fallback detector used: %s", detector_backend)
                    break
                except Exception as e:
                    last_verify_error = e
                    logger.warning("DeepFace verify failed (%s/%s): %s", model_name, detector_backend, e)
            if result is not None:
                break

        if result is None:
            raise RuntimeError(last_verify_error or "DeepFace verify failed")

        elapsed = _elapsed_ms(start)
        distance = float(result.get("distance", 1.0))
        strict_threshold = _resolve_strict_threshold(used_model_name, distance_metric, result)
        strict_pass = distance <= strict_threshold
        primary_verified = bool(result.get("verified") and strict_pass)
        final_verified = primary_verified

        # Optional second-pass metric cross-check to reduce false accepts.
        secondary_enabled = _env_bool("DEEPFACE_REQUIRE_SECONDARY_METRIC", True)
        secondary_metric = _secondary_metric(distance_metric)
        secondary_distance: float | None = None
        secondary_threshold: float | None = None
        secondary_verified = True

        if secondary_enabled:
            try:
                secondary_result = DeepFace.verify(
                    img1_path=tmp_path,
                    img2_path=registered_image_path,
                    model_name=used_model_name,
                    detector_backend=used_detector_backend,
                    distance_metric=secondary_metric,
                    enforce_detection=True,
                    silent=True,
                )
                secondary_distance = float(secondary_result.get("distance", 1.0))
                secondary_threshold = _resolve_strict_threshold(
                    used_model_name,
                    secondary_metric,
                    secondary_result,
                )
                secondary_verified = bool(
                    secondary_result.get("verified")
                    and secondary_distance <= secondary_threshold
                )
            except Exception as e:
                # If secondary check engine fails, do not allow false accept;
                # force retry so user stays in face flow.
                logger.warning("DeepFace secondary verify failed: %s", e)
                secondary_verified = False

        final_verified = primary_verified and secondary_verified

        if final_verified:
            logger.info(
                "Face verified (distance=%.4f <= threshold=%.4f, %dms, model=%s, metric=%s)",
                distance,
                strict_threshold,
                elapsed,
                used_model_name,
                distance_metric,
            )
            return {
                "verified": True,
                "distance": distance,
                "threshold": strict_threshold,
                "time_ms": elapsed,
                "fallback": False,
                "message": "인증 성공",
            }

        if result.get("verified") and not strict_pass:
            logger.warning(
                "Face strict reject: distance=%.4f threshold=%.4f model=%s metric=%s",
                distance,
                strict_threshold,
                used_model_name,
                distance_metric,
            )
            reject_payload = _retry_result(
                start,
                "등록된 사진과 일치도가 낮습니다. 정면에서 다시 인증해 주세요.",
                distance=distance,
            )
            reject_payload["threshold"] = strict_threshold
            return reject_payload

        if secondary_enabled and primary_verified and not secondary_verified:
            logger.warning(
                "Face secondary reject: primary %.4f<=%.4f(%s), secondary %.4f<=%.4f(%s) failed",
                distance,
                strict_threshold,
                distance_metric,
                secondary_distance if secondary_distance is not None else -1.0,
                secondary_threshold if secondary_threshold is not None else -1.0,
                secondary_metric,
            )
            reject_payload = _retry_result(
                start,
                "등록된 사진과 일치도가 낮습니다. 다른 사람일 수 있어 재인증이 필요합니다.",
                distance=distance,
            )
            reject_payload["threshold"] = strict_threshold
            return reject_payload

        logger.info("Face mismatch (distance=%.4f)", distance)
        result_payload = _retry_result(
            start,
            "등록된 사진과 다른 사람입니다. 다시 인증을 진행해 주세요.",
            distance=distance,
        )
        result_payload["threshold"] = strict_threshold
        return result_payload

    except Exception as e:
        msg = str(e).lower()
        logger.warning("Face verify error: %s", e)
        if "face could not be detected" in msg or "no face" in msg:
            return _retry_result(start, "얼굴이 감지되지 않았습니다. 본인 얼굴을 다시 촬영해 주세요.")
        return _fallback_result(start, "안면 인식 시스템 오류로 음성 인증으로 전환합니다.")
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


def register_face(image_bytes: bytes, save_path: str = REGISTERED_FACE_PATH) -> bool:
    try:
        Path(save_path).write_bytes(image_bytes)
        logger.info("Face registered: %s", save_path)
        return True
    except Exception as e:
        logger.error("Face register failed: %s", e)
        return False
