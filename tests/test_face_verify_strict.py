from ai import deepface_auth
from pathlib import Path
from uuid import uuid4


class _FakeDeepFace:
    verify_result = {"verified": False, "distance": 1.0, "threshold": 0.6}
    verify_calls = 0

    @staticmethod
    def extract_faces(**kwargs):
        return [{"is_real": True, "antispoof_score": 0.99}]

    @staticmethod
    def verify(**kwargs):
        _FakeDeepFace.verify_calls += 1
        return dict(_FakeDeepFace.verify_result)

    @staticmethod
    def build_model(model_name):
        return object()


def _run_verify(monkeypatch, verify_result):
    tmp_dir = Path("tests/.tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    registered = tmp_dir / f"registered_face_{uuid4().hex}.jpg"
    registered.write_bytes(b"registered")

    _FakeDeepFace.verify_result = verify_result
    _FakeDeepFace.verify_calls = 0
    monkeypatch.setattr(deepface_auth, "_get_deepface", lambda: _FakeDeepFace)
    monkeypatch.setenv("DEEPFACE_STRICT_MULTIPLIER", "0.90")
    monkeypatch.setenv("DEEPFACE_REQUIRE_SECONDARY_METRIC", "true")

    try:
        return deepface_auth.verify_face_from_bytes(
            image_bytes=b"camera-frame",
            registered_image_path=str(registered),
        )
    finally:
        registered.unlink(missing_ok=True)


def test_reject_when_distance_is_above_strict_threshold(monkeypatch):
    result = _run_verify(
        monkeypatch,
        {"verified": True, "distance": 0.50, "threshold": 0.55},
    )

    assert result["verified"] is False
    assert result["fallback"] is False
    assert "일치도" in result["message"]


def test_pass_when_distance_is_within_strict_threshold(monkeypatch):
    result = _run_verify(
        monkeypatch,
        {"verified": True, "distance": 0.40, "threshold": 0.55},
    )

    assert result["verified"] is True
    assert result["fallback"] is False
    assert result["message"] == "인증 성공"
    assert _FakeDeepFace.verify_calls >= 2
