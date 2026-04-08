#!/usr/bin/env python3
"""
보이스피싱 음성 데이터용 STT + 화자 분리 + 역할 추정 배치 파이프라인.

핵심 목표
- 입력 폴더(예: 대출사기형, 수사기관사칭형)의 음성 파일(wav/mp3/m4a)을 일괄 처리한다.
- 한국어 STT를 수행하고, 가능한 경우 diarization으로 화자를 분리한다.
- 발화 순서를 유지한 대화문 TXT와 분석용 JSON을 함께 저장한다.
- diarization이 실패해도 STT 결과는 반드시 저장한다.

주의
- pyannote diarization 사용 시 Hugging Face 토큰(HF_TOKEN)이 필요하다.
- 역할 추정(피싱범/피해자)은 휴리스틱 기반이므로 확신이 낮으면 fallback 라벨을 사용한다.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import traceback
from glob import glob
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a"}
DEFAULT_INPUT_DIRS = ["대출사기형", "수사기관사칭형"]

# STT 텍스트 정리용 간단한 패턴.
FILLER_PATTERNS = [
    r"\b(어+|음+|아+|그+|저+)\b",
    r"[\.\,\s]*(어\.{2,}|음\.{2,}|아\.{2,})",
]
BEEP_PATTERNS = [
    r"삐+",
    r"비프",
    r"beep",
    r"삡+",
]

# 역할 추정 키워드(필요 시 확장 가능).
SCAMMER_KEYWORDS = [
    "검찰", "경찰", "금감원", "금융감독원", "수사기관", "사건", "피의자", "계좌", "이체",
    "송금", "현금", "인출", "앱", "원격", "설치", "보안", "비밀", "알리지", "즉시",
    "빨리", "긴급", "협조", "지시", "조사", "영장", "명의도용", "범죄연루",
]

VICTIM_KEYWORDS = [
    "정말", "왜", "어떻게", "몰라", "무슨", "제가", "저는", "확인", "맞나요", "아닌데",
    "당황", "무서워", "가족", "남편", "아내", "부모", "돈", "계좌", "어디로", "다시",
    "잘", "못", "이해", "네?", "네", "잠시만", "질문", "확인해볼게요",
]


def load_env_file(env_path: Path) -> None:
    """
    .env 파일의 KEY=VALUE를 읽어 환경변수로 주입한다.

    규칙
    - 이미 OS 환경변수에 존재하는 키는 덮어쓰지 않는다.
    - 주석/빈 줄은 무시한다.
    - 양쪽 따옴표(" 또는 ')는 제거한다.
    """
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {'"', "'"}
            ):
                value = value[1:-1]

            if key and key not in os.environ:
                os.environ[key] = value
    except Exception as exc:
        logging.warning(".env 로드 실패(%s): %s", env_path, exc)


@dataclass
class Utterance:
    """단일 발화 단위 데이터."""

    idx: int
    speaker: str
    text: str
    start: Optional[float]
    end: Optional[float]


class STTEngine:
    """faster-whisper 우선 STT 엔진. 실패 시 whisper(원본)로 fallback 시도."""

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "int8",
        language: str = "ko",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.backend = None
        self.model = None

        self._initialize_model()

    def _initialize_model(self) -> None:
        """가능한 STT 백엔드를 순서대로 로드한다."""
        # 1) faster-whisper 시도
        try:
            from faster_whisper import WhisperModel  # type: ignore

            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            self.backend = "faster-whisper"
            logging.info("STT backend: faster-whisper (%s)", self.model_size)
            return
        except Exception as exc:
            logging.warning("faster-whisper 초기화 실패: %s", exc)

        # 2) openai-whisper(whisper) 시도
        try:
            import whisper  # type: ignore

            self.model = whisper.load_model(self.model_size)
            self.backend = "whisper"
            logging.info("STT backend: whisper (%s)", self.model_size)
            return
        except Exception as exc:
            logging.warning("whisper 초기화 실패: %s", exc)

        raise RuntimeError(
            "사용 가능한 STT 백엔드를 찾지 못했습니다. "
            "faster-whisper 또는 whisper 설치를 확인해 주세요."
        )

    def transcribe(self, audio_path: Path) -> List[Dict[str, Any]]:
        """오디오를 STT 수행하여 세그먼트 목록을 반환한다."""
        if self.backend == "faster-whisper":
            return self._transcribe_faster_whisper(audio_path)
        if self.backend == "whisper":
            return self._transcribe_whisper(audio_path)
        raise RuntimeError("STT backend가 초기화되지 않았습니다.")

    def _transcribe_faster_whisper(self, audio_path: Path) -> List[Dict[str, Any]]:
        """faster-whisper 기반 STT."""
        segments, info = self.model.transcribe(
            str(audio_path),
            language=self.language,
            vad_filter=True,
            beam_size=5,
            word_timestamps=False,
            condition_on_previous_text=True,
        )
        logging.info(
            "STT 완료(faster-whisper): %s | language=%s prob=%.3f",
            audio_path.name,
            info.language,
            info.language_probability,
        )

        output = []
        for seg in segments:
            text = normalize_segment_text(seg.text)
            output.append(
                {
                    "start": safe_float(seg.start),
                    "end": safe_float(seg.end),
                    "text": text if text else "[불명확]",
                }
            )
        return output

    def _transcribe_whisper(self, audio_path: Path) -> List[Dict[str, Any]]:
        """openai-whisper 기반 STT."""
        result = self.model.transcribe(
            str(audio_path),
            language=self.language,
            fp16=False,
            condition_on_previous_text=True,
        )
        logging.info("STT 완료(whisper): %s", audio_path.name)

        output = []
        for seg in result.get("segments", []):
            text = normalize_segment_text(seg.get("text", ""))
            output.append(
                {
                    "start": safe_float(seg.get("start")),
                    "end": safe_float(seg.get("end")),
                    "text": text if text else "[불명확]",
                }
            )
        return output


class DiarizationEngine:
    """pyannote 또는 NVIDIA NeMo 기반 diarization 엔진."""

    def __init__(
        self,
        hf_token: Optional[str],
        device: str = "cpu",
        model_id: str = "pyannote/speaker-diarization-3.1",
        backend: str = "pyannote",
        nemo_num_speakers: Optional[int] = None,
        nemo_out_dir: str = ".nemo_diarization",
    ) -> None:
        self.available = False
        self.pipeline = None  # pyannote pipeline
        self.nemo_diarizer_cls = None
        self.omegaconf = None
        self.device = device
        self.model_id = model_id
        self.backend = backend.lower().strip()
        self.nemo_num_speakers = nemo_num_speakers
        self.nemo_out_dir = Path(nemo_out_dir)

        if self.backend not in {"pyannote", "nemo"}:
            logging.warning("알 수 없는 diarization backend: %s", self.backend)
            return

        if self.backend == "pyannote":
            self._init_pyannote(hf_token)
        elif self.backend == "nemo":
            self._init_nemo()

    def _init_pyannote(self, hf_token: Optional[str]) -> None:
        """pyannote 초기화."""
        if not hf_token:
            logging.warning("HF 토큰이 없어 pyannote diarization 비활성화")
            return
        try:
            from pyannote.audio import Pipeline  # type: ignore
            import torch  # type: ignore

            self.pipeline = Pipeline.from_pretrained(
                self.model_id,
                use_auth_token=hf_token,
            )
            if self.device.startswith("cuda") and torch.cuda.is_available():
                self.pipeline.to(torch.device("cuda"))
            else:
                self.pipeline.to(torch.device("cpu"))
            self.available = True
            logging.info("diarization backend: pyannote.audio (%s)", self.model_id)
        except Exception as exc:
            logging.warning("pyannote 초기화 실패, diarization 비활성화: %s", exc)

    def _init_nemo(self) -> None:
        """NVIDIA NeMo diarization 초기화."""
        try:
            from nemo.collections.asr.models.msdd_models import NeuralDiarizer  # type: ignore
            from omegaconf import OmegaConf  # type: ignore

            self.nemo_diarizer_cls = NeuralDiarizer
            self.omegaconf = OmegaConf
            self.available = True
            logging.info("diarization backend: NVIDIA NeMo (MSDD)")
        except Exception as exc:
            logging.warning("NeMo 초기화 실패, diarization 비활성화: %s", exc)

    def diarize(self, audio_path: Path) -> List[Dict[str, Any]]:
        """화자 구간 목록 반환. 실패 시 빈 리스트 반환."""
        if not self.available:
            return []

        if self.backend == "pyannote":
            return self._diarize_pyannote(audio_path)
        if self.backend == "nemo":
            return self._diarize_nemo(audio_path)
        return []

    def _diarize_pyannote(self, audio_path: Path) -> List[Dict[str, Any]]:
        """pyannote diarization."""
        try:
            diarization = self.pipeline(str(audio_path))
            segments: List[Dict[str, Any]] = []
            for segment, _, speaker in diarization.itertracks(yield_label=True):
                segments.append(
                    {
                        "speaker": str(speaker),
                        "start": safe_float(segment.start),
                        "end": safe_float(segment.end),
                    }
                )
            return segments
        except Exception as exc:
            logging.warning("diarization 실패(%s): %s", audio_path.name, exc)
            return []

    def _diarize_nemo(self, audio_path: Path) -> List[Dict[str, Any]]:
        """NVIDIA NeMo MSDD diarization."""
        try:
            self.nemo_out_dir.mkdir(parents=True, exist_ok=True)
            file_workdir = self.nemo_out_dir / audio_path.stem
            file_workdir.mkdir(parents=True, exist_ok=True)

            manifest_path = file_workdir / "input_manifest.json"
            manifest_item: Dict[str, Any] = {
                "audio_filepath": str(audio_path.resolve()),
                "offset": 0,
                "duration": None,
                "label": "infer",
                "text": "-",
                "rttm_filepath": None,
                "uem_filepath": None,
            }
            if self.nemo_num_speakers is not None:
                manifest_item["num_speakers"] = int(self.nemo_num_speakers)

            manifest_path.write_text(
                json.dumps(manifest_item, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            cfg = self.omegaconf.create(
                {
                    "device": ("cuda" if self.device.startswith("cuda") else "cpu"),
                    "verbose": False,
                    "batch_size": 64,
                    "num_workers": 1,
                    "sample_rate": 16000,
                    "name": "nemo_diarization_infer",
                    "diarizer": {
                        "manifest_filepath": str(manifest_path),
                        "out_dir": str(file_workdir),
                        "oracle_vad": False,
                        "collar": 0.25,
                        "ignore_overlap": True,
                        "vad": {
                            "model_path": "vad_multilingual_marblenet",
                            "parameters": {
                                "onset": 0.8,
                                "offset": 0.6,
                                "pad_onset": 0.05,
                                "pad_offset": -0.05,
                                "min_duration_on": 0.1,
                                "min_duration_off": 0.1,
                            },
                        },
                        "speaker_embeddings": {
                            "model_path": "titanet_large",
                            "parameters": {
                                "window_length_in_sec": [1.5, 1.25, 1.0, 0.75, 0.5],
                                "shift_length_in_sec": [0.75, 0.625, 0.5, 0.375, 0.25],
                                "multiscale_weights": [1, 1, 1, 1, 1],
                            },
                        },
                        "clustering": {
                            "parameters": {
                                "oracle_num_speakers": self.nemo_num_speakers is not None,
                                "max_num_speakers": int(self.nemo_num_speakers or 8),
                                "enhanced_count_thres": 80,
                            }
                        },
                        "msdd_model": {
                            "model_path": "diar_msdd_telephonic",
                            "parameters": {
                                "use_speaker_model_from_ckpt": True,
                                "infer_batch_size": 25,
                                "sigmoid_threshold": [0.7],
                                "seq_eval_mode": False,
                                "split_infer": True,
                                "diar_window_length": 50,
                                "overlap_infer_spk_limit": 5,
                            },
                        },
                    }
                }
            )

            diarizer = self.nemo_diarizer_cls(cfg=cfg)
            diarizer.diarize()

            rttm_files = glob(str(file_workdir / "**" / "*.rttm"), recursive=True)
            if not rttm_files:
                return []

            # 일반적으로 단일 파일이므로 첫 RTTM 사용
            return parse_rttm_file(Path(rttm_files[0]))
        except Exception as exc:
            logging.warning("NeMo diarization 실패(%s): %s", audio_path.name, exc)
            return []


def parse_rttm_file(rttm_path: Path) -> List[Dict[str, Any]]:
    """RTTM 파일을 내부 diarization 세그먼트 형식으로 변환."""
    segments: List[Dict[str, Any]] = []
    if not rttm_path.exists():
        return segments

    for line in rttm_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) < 8 or parts[0] != "SPEAKER":
            continue
        try:
            start = float(parts[3])
            duration = float(parts[4])
            speaker = parts[7]
            segments.append(
                {
                    "speaker": str(speaker),
                    "start": safe_float(start),
                    "end": safe_float(start + duration),
                }
            )
        except Exception:
            continue
    return segments


def clean_text(text: str) -> str:
    """의미를 훼손하지 않는 범위에서 불필요한 추임새/공백을 정리한다."""
    text = (text or "").strip()
    if not text:
        return ""

    cleaned = text
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 지나치게 짧고 의미 없는 경우 [불명확]로 보낼 수 있도록 빈 문자열 처리.
    if cleaned in {".", ",", "..", "..."}:
        return ""
    return cleaned


def normalize_segment_text(raw_text: str) -> str:
    """
    STT 원문을 정규화하여 특수 토큰을 보존한다.
    - 삐/비프 계열은 [비식별음]으로 통일
    - 일반 텍스트는 clean_text 적용
    """
    raw = (raw_text or "").strip()
    if not raw:
        return ""

    lowered = raw.lower()
    for pattern in BEEP_PATTERNS:
        if re.search(pattern, raw, flags=re.IGNORECASE):
            return "[비식별음]"
    if lowered in {"beep", "beep.", "beep.."}:
        return "[비식별음]"

    return clean_text(raw)


def inject_silence_tokens(
    stt_segments: List[Dict[str, Any]],
    silence_threshold_sec: float = 1.2,
) -> List[Dict[str, Any]]:
    """
    인접 STT 세그먼트 사이 공백이 길면 [무음] 세그먼트를 삽입한다.
    """
    if not stt_segments:
        return []

    output: List[Dict[str, Any]] = []
    prev_end: Optional[float] = None

    for seg in stt_segments:
        start = safe_float(seg.get("start"))
        end = safe_float(seg.get("end"))

        if prev_end is not None and start is not None:
            gap = start - prev_end
            if gap >= silence_threshold_sec:
                output.append(
                    {
                        "start": safe_float(prev_end),
                        "end": safe_float(start),
                        "text": "[무음]",
                    }
                )

        output.append(
            {
                "start": start,
                "end": end,
                "text": seg.get("text", "") or "[불명확]",
            }
        )
        prev_end = end if end is not None else prev_end

    return output


def safe_float(value: Any) -> Optional[float]:
    """JSON 직렬화를 위해 숫자형을 float로 안전 변환."""
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except Exception:
        return None


def find_audio_files(input_dirs: Iterable[Path]) -> List[Tuple[str, Path]]:
    """(카테고리명, 파일경로) 목록을 확장자 기준으로 수집한다."""
    collected: List[Tuple[str, Path]] = []
    for category_dir in input_dirs:
        if not category_dir.exists():
            logging.warning("입력 폴더 없음: %s", category_dir)
            continue

        category = category_dir.name
        for path in category_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                collected.append((category, path))

    # 재현 가능한 처리 순서를 위해 정렬.
    collected.sort(key=lambda x: (x[0], str(x[1]).lower()))
    return collected


def compute_overlap(a_start: Optional[float], a_end: Optional[float], b_start: float, b_end: float) -> float:
    """두 구간의 겹치는 길이를 계산한다."""
    if a_start is None or a_end is None:
        return 0.0
    left = max(a_start, b_start)
    right = min(a_end, b_end)
    return max(0.0, right - left)


def assign_speakers(
    stt_segments: List[Dict[str, Any]],
    diar_segments: List[Dict[str, Any]],
    fallback_speakers: int = 2,
) -> List[Utterance]:
    """
    STT 세그먼트에 diarization 화자를 매칭한다.

    전략
    - STT 세그먼트와 diarization 구간의 overlap이 가장 큰 화자를 우선 선택.
    - diarization이 아예 없으면 STT 구간을 턴 단위로 묶고 fallback 화자를 배정한다.
    - diarization 일부 실패 구간은 시간적으로 가장 가까운 diarization 화자로 보정 시도.
    - 그래도 불가하면 UNKNOWN 단일 화자로 묶는다.
    """
    utterances: List[Utterance] = []

    # diarization이 없으면 pause 기반 턴 분할 후 fallback 화자 라벨을 부여한다.
    if not diar_segments:
        turns = build_turns_from_stt(stt_segments, pause_threshold=0.9)
        if not turns:
            return []

        if fallback_speakers <= 1 or len(turns) == 1:
            for idx, turn in enumerate(turns, start=1):
                utterances.append(
                    Utterance(
                        idx=idx,
                        speaker="NO_DIAR_SPK",
                        text=turn["text"],
                        start=turn["start"],
                        end=turn["end"],
                    )
                )
            return utterances

        # 2화자 대화 fallback: 턴 단위 교대 배정(낮은 신뢰도 전제)
        labels = [f"FALLBACK_{i}" for i in range(1, fallback_speakers + 1)]
        for idx, turn in enumerate(turns, start=1):
            speaker = labels[(idx - 1) % fallback_speakers]
            utterances.append(
                Utterance(
                    idx=idx,
                    speaker=speaker,
                    text=turn["text"],
                    start=turn["start"],
                    end=turn["end"],
                )
            )
        return utterances

    for idx, seg in enumerate(stt_segments, start=1):
        best_speaker = "UNKNOWN"
        best_overlap = 0.0

        for diar in diar_segments:
            overlap = compute_overlap(seg.get("start"), seg.get("end"), diar["start"], diar["end"])
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = diar["speaker"]

        utterances.append(
            Utterance(
                idx=idx,
                speaker=best_speaker,
                text=seg.get("text", "") or "[불명확]",
                start=safe_float(seg.get("start")),
                end=safe_float(seg.get("end")),
            )
        )

    # overlap이 0인 UNKNOWN 구간은 시간적으로 가장 가까운 diarization 구간으로 보정.
    for utt in utterances:
        if utt.speaker != "UNKNOWN":
            continue

        if utt.start is None and utt.end is None:
            continue

        center = None
        if utt.start is not None and utt.end is not None:
            center = (utt.start + utt.end) / 2.0
        elif utt.start is not None:
            center = utt.start
        elif utt.end is not None:
            center = utt.end

        if center is None:
            continue

        nearest_speaker = None
        nearest_distance = float("inf")
        for diar in diar_segments:
            diar_center = (diar["start"] + diar["end"]) / 2.0
            dist = abs(center - diar_center)
            if dist < nearest_distance:
                nearest_distance = dist
                nearest_speaker = diar["speaker"]

        # 너무 멀면 오매칭 위험이 있어 보수적으로 UNKNOWN 유지.
        if nearest_speaker is not None and nearest_distance <= 4.0:
            utt.speaker = nearest_speaker

    # 보정 후에도 UNKNOWN이 남아있으면 한 명의 fallback 화자로 묶는다.
    for utt in utterances:
        if utt.speaker == "UNKNOWN":
            utt.speaker = "UNK_FALLBACK"

    return merge_consecutive_utterances(utterances)


def merge_consecutive_utterances(utterances: List[Utterance]) -> List[Utterance]:
    """동일 화자가 연속으로 발화한 세그먼트를 합쳐 문맥 단위를 개선한다."""
    if not utterances:
        return []

    merged: List[Utterance] = []
    current = utterances[0]

    for nxt in utterances[1:]:
        if nxt.speaker == current.speaker:
            # 연속 화자면 텍스트를 이어붙여 대화 가독성을 개선.
            current.text = f"{current.text} {nxt.text}".strip()
            current.end = nxt.end if nxt.end is not None else current.end
        else:
            merged.append(current)
            current = nxt

    merged.append(current)

    # idx 재부여(병합 후 순번)
    for i, utt in enumerate(merged, start=1):
        utt.idx = i

    return merged


def build_turns_from_stt(
    stt_segments: List[Dict[str, Any]],
    pause_threshold: float = 0.9,
    max_turn_duration: float = 12.0,
) -> List[Dict[str, Any]]:
    """
    diarization이 없을 때 STT 세그먼트를 pause 기준 턴 단위로 병합한다.
    """
    if not stt_segments:
        return []

    turns: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for seg in stt_segments:
        text = (seg.get("text") or "").strip() or "[불명확]"
        start = safe_float(seg.get("start"))
        end = safe_float(seg.get("end"))

        # [무음]은 문맥 단절 정보를 보존하기 위해 독립 턴으로 유지한다.
        if text == "[무음]":
            if current is not None:
                turns.append(current)
                current = None
            turns.append({"start": start, "end": end, "text": "[무음]"})
            continue

        if current is None:
            current = {"start": start, "end": end, "text": text}
            continue

        prev_end = current.get("end")
        gap = None
        if prev_end is not None and start is not None:
            gap = start - prev_end

        if gap is not None and gap > pause_threshold:
            turns.append(current)
            current = {"start": start, "end": end, "text": text}
        else:
            # 무음이 거의 없더라도 너무 긴 단일 턴이 되지 않도록 길이 기반 분할을 적용.
            if (
                current.get("start") is not None
                and end is not None
                and (end - current["start"]) >= max_turn_duration
            ):
                turns.append(current)
                current = {"start": start, "end": end, "text": text}
                continue

            current["text"] = f"{current['text']} {text}".strip()
            current["end"] = end if end is not None else current["end"]

    if current is not None:
        turns.append(current)
    return turns


def normalize_speaker_ids(utterances: List[Utterance]) -> Tuple[List[Utterance], Dict[str, str]]:
    """화자 ID를 화자1/화자2/... 형식으로 안정적으로 매핑한다."""
    speakers = []
    for utt in utterances:
        if utt.speaker not in speakers:
            speakers.append(utt.speaker)

    speaker_to_fallback = {spk: f"화자{i}" for i, spk in enumerate(speakers, start=1)}

    for utt in utterances:
        utt.speaker = speaker_to_fallback[utt.speaker]

    return utterances, speaker_to_fallback


def score_role_for_text(text: str) -> Tuple[int, int]:
    """텍스트 한 줄에서 (피싱범점수, 피해자점수)를 계산한다."""
    lowered = text.lower()
    scam_score = sum(1 for kw in SCAMMER_KEYWORDS if kw in lowered)
    victim_score = sum(1 for kw in VICTIM_KEYWORDS if kw in lowered)
    return scam_score, victim_score


def infer_roles(utterances: List[Utterance]) -> Tuple[Dict[str, str], Dict[str, float], List[str]]:
    """
    화자별 역할을 휴리스틱으로 추정한다.

    반환값
    - role_mapping: {화자N: 라벨(피싱범/피해자/화자N)}
    - role_confidence: {화자N: 0~1}
    - notes: 불확실성/근거 메모
    """
    speaker_scores: Dict[str, Counter] = defaultdict(Counter)

    for utt in utterances:
        scam_score, victim_score = score_role_for_text(utt.text)
        speaker_scores[utt.speaker]["scam"] += scam_score
        speaker_scores[utt.speaker]["victim"] += victim_score
        speaker_scores[utt.speaker]["tokens"] += len(utt.text.split())

    role_mapping: Dict[str, str] = {}
    role_confidence: Dict[str, float] = {}
    notes: List[str] = []

    for speaker, scores in speaker_scores.items():
        scam = scores["scam"]
        victim = scores["victim"]
        evidence = scam + victim

        if evidence < 2:
            # 근거가 부족하면 단정하지 않는다.
            role_mapping[speaker] = speaker
            role_confidence[speaker] = 0.2
            notes.append(f"{speaker}: 역할 근거 부족으로 fallback 라벨 유지")
            continue

        # 두 점수 차이가 충분히 클 때만 역할 확정.
        if scam >= victim + 2 and scam >= 2:
            role_mapping[speaker] = "피싱범"
            role_confidence[speaker] = min(0.95, 0.5 + (scam - victim) * 0.1)
        elif victim >= scam + 2 and victim >= 2:
            role_mapping[speaker] = "피해자"
            role_confidence[speaker] = min(0.95, 0.5 + (victim - scam) * 0.1)
        else:
            role_mapping[speaker] = speaker
            role_confidence[speaker] = 0.35
            notes.append(
                f"{speaker}: 피싱범/피해자 점수가 유사해 fallback 라벨 유지 "
                f"(scam={scam}, victim={victim})"
            )

    role_mapping, role_confidence, post_notes = enforce_role_consistency(
        speaker_scores, role_mapping, role_confidence
    )
    notes.extend(post_notes)

    return role_mapping, role_confidence, notes


def enforce_role_consistency(
    speaker_scores: Dict[str, Counter],
    role_mapping: Dict[str, str],
    role_confidence: Dict[str, float],
) -> Tuple[Dict[str, str], Dict[str, float], List[str]]:
    """
    역할 라벨 충돌을 완화한다.
    - 2화자 대화에서 두 화자가 동일 역할(둘 다 피싱범/둘 다 피해자)로 확정되면
      더 약한 쪽을 fallback 라벨로 되돌린다.
    """
    notes: List[str] = []
    speakers = list(role_mapping.keys())
    if len(speakers) != 2:
        return role_mapping, role_confidence, notes

    s1, s2 = speakers[0], speakers[1]
    r1, r2 = role_mapping.get(s1), role_mapping.get(s2)
    locked_roles = {"피싱범", "피해자"}

    if r1 in locked_roles and r1 == r2:
        # 근거가 약한 쪽(점수 차 작은 화자)을 fallback으로 돌린다.
        diff1 = abs(speaker_scores[s1]["scam"] - speaker_scores[s1]["victim"])
        diff2 = abs(speaker_scores[s2]["scam"] - speaker_scores[s2]["victim"])
        weaker = s1 if diff1 <= diff2 else s2
        role_mapping[weaker] = weaker
        role_confidence[weaker] = min(role_confidence.get(weaker, 0.35), 0.35)
        notes.append(
            f"{weaker}: 2화자 동시 동일역할 충돌로 fallback 라벨 유지"
        )

    return role_mapping, role_confidence, notes


def build_txt_lines(utterances: List[Utterance], role_mapping: Dict[str, str]) -> List[str]:
    """최종 TXT 저장 라인 구성(발화 순서 유지)."""
    lines: List[str] = []
    for utt in utterances:
        label = role_mapping.get(utt.speaker, utt.speaker)
        text = utt.text if utt.text.strip() else "[불명확]"
        lines.append(f"{label}: {text}")
    return lines


def build_json_payload(
    category: str,
    original_filename: str,
    utterances: List[Utterance],
    role_mapping: Dict[str, str],
    role_confidence: Dict[str, float],
    notes: List[str],
    diarization_used: bool,
    stt_backend: str,
) -> Dict[str, Any]:
    """요구 필드를 포함하는 유연한 JSON 구조 생성."""
    transcript = []
    for utt in utterances:
        transcript.append(
            {
                "utterance_index": utt.idx,
                "speaker": utt.speaker,
                "role": role_mapping.get(utt.speaker, utt.speaker),
                "start": utt.start,
                "end": utt.end,
                "text": utt.text if utt.text.strip() else "[불명확]",
            }
        )

    return {
        "source_category": category,
        "original_filename": original_filename,
        "speakers_detected": sorted({u.speaker for u in utterances}),
        "role_mapping": role_mapping,
        "role_mapping_confidence": role_confidence,
        "transcript": transcript,
        "notes": notes,
        "meta": {
            "stt_backend": stt_backend,
            "diarization_used": diarization_used,
            "utterance_count": len(transcript),
        },
    }


def ensure_output_dirs(output_root: Path, categories: Iterable[str]) -> None:
    """카테고리별 출력 폴더 생성."""
    output_root.mkdir(parents=True, exist_ok=True)
    for category in categories:
        (output_root / category).mkdir(parents=True, exist_ok=True)


def process_single_file(
    category: str,
    audio_path: Path,
    output_root: Path,
    stt_engine: STTEngine,
    diar_engine: Optional[DiarizationEngine],
    fallback_speakers: int = 2,
) -> None:
    """단일 파일 처리(STT -> diarization 결합 -> 역할 추정 -> txt/json 저장)."""
    category_output = output_root / category
    category_output.mkdir(parents=True, exist_ok=True)

    base_name = audio_path.stem
    txt_path = category_output / f"{base_name}.txt"
    json_path = category_output / f"{base_name}.json"

    # 1) STT
    stt_segments = stt_engine.transcribe(audio_path)
    if not stt_segments:
        stt_segments = [{"start": None, "end": None, "text": "[불명확]"}]
    stt_segments = inject_silence_tokens(stt_segments, silence_threshold_sec=1.2)

    # 2) diarization (가능할 때만)
    diar_segments: List[Dict[str, Any]] = []
    diarization_used = False
    if diar_engine and diar_engine.available:
        diar_segments = diar_engine.diarize(audio_path)
        diarization_used = len(diar_segments) > 0

    # 3) 화자 매핑 + fallback 정규화
    utterances = assign_speakers(
        stt_segments,
        diar_segments,
        fallback_speakers=fallback_speakers,
    )
    utterances, _ = normalize_speaker_ids(utterances)

    # 4) 역할 추정(불확실하면 fallback 유지)
    role_mapping, role_confidence, infer_notes = infer_roles(utterances)
    notes = list(infer_notes)
    if not diarization_used:
        notes.append(
            f"diarization 미사용 또는 실패: fallback {fallback_speakers}화자 규칙 기반으로 저장"
        )

    # 5) TXT 저장
    txt_lines = build_txt_lines(utterances, role_mapping)
    txt_path.write_text("\n".join(txt_lines), encoding="utf-8")

    # 6) JSON 저장
    payload = build_json_payload(
        category=category,
        original_filename=audio_path.name,
        utterances=utterances,
        role_mapping=role_mapping,
        role_confidence=role_confidence,
        notes=notes,
        diarization_used=diarization_used,
        stt_backend=stt_engine.backend or "unknown",
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """CLI 인자 파싱."""
    parser = argparse.ArgumentParser(
        description="보이스피싱 음성 폴더 일괄 STT/화자분리/역할추정 파이프라인"
    )
    parser.add_argument(
        "--input-dirs",
        nargs="+",
        default=DEFAULT_INPUT_DIRS,
        help="처리할 입력 폴더 목록(상대경로 또는 절대경로)",
    )
    parser.add_argument(
        "--output-root",
        default="stt_output",
        help="출력 루트 폴더(카테고리 하위 폴더 자동 생성)",
    )
    parser.add_argument("--model-size", default="large-v3", help="Whisper 모델 크기")
    parser.add_argument("--language", default="ko", help="STT 언어 코드")
    parser.add_argument(
        "--device",
        default="auto",
        help="STT 디바이스(auto/cpu/cuda)",
    )
    parser.add_argument(
        "--compute-type",
        default="int8",
        help="faster-whisper compute_type (int8/float16 등)",
    )
    parser.add_argument(
        "--enable-diarization",
        action="store_true",
        help="diarization 사용 시도(backend는 --diarization-backend로 선택)",
    )
    parser.add_argument(
        "--diarization-backend",
        default=os.environ.get("DIARIZATION_BACKEND", "pyannote"),
        choices=["pyannote", "nemo"],
        help="diarization backend 선택(pyannote 또는 nemo)",
    )
    parser.add_argument(
        "--hf-token",
        default=os.environ.get("HF_TOKEN", ""),
        help="Hugging Face token (미지정 시 HF_TOKEN 환경변수 사용)",
    )
    parser.add_argument(
        "--diarization-model",
        default=os.environ.get("DIARIZATION_MODEL_ID", "pyannote/speaker-diarization-3.1"),
        help="pyannote용 모델 ID(HF repo). 미지정 시 DIARIZATION_MODEL_ID 또는 기본값 사용",
    )
    parser.add_argument(
        "--nemo-num-speakers",
        type=int,
        default=int(os.environ.get("NEMO_NUM_SPEAKERS", "0") or 0),
        help="NeMo diarization 시 기대 화자 수(0이면 자동 추정)",
    )
    parser.add_argument(
        "--nemo-out-dir",
        default=os.environ.get("NEMO_OUT_DIR", ".nemo_diarization"),
        help="NeMo diarization 중간 산출물 저장 경로",
    )
    parser.add_argument(
        "--log-file",
        default="stt_output/process.log",
        help="실행 로그 파일 경로",
    )
    parser.add_argument(
        "--fallback-speakers",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="diarization 불가 시 사용할 fallback 화자 수(기본 2)",
    )
    return parser.parse_args()


def configure_logging(log_file: Path) -> None:
    """콘솔+파일 로깅 설정."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(asctime)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def main() -> int:
    # CLI 인자 기본값에서 환경변수를 사용할 수 있도록 parse_args 이전에 로드.
    load_env_file(Path(".env"))
    args = parse_args()
    log_file = Path(args.log_file)
    configure_logging(log_file)

    input_dirs = [Path(p) for p in args.input_dirs]
    output_root = Path(args.output_root)

    ensure_output_dirs(output_root, [d.name for d in input_dirs])

    try:
        stt_engine = STTEngine(
            model_size=args.model_size,
            device=args.device,
            compute_type=args.compute_type,
            language=args.language,
        )
    except Exception as exc:
        logging.error("STT 엔진 초기화 실패: %s", exc)
        return 1

    diar_engine: Optional[DiarizationEngine] = None
    if args.enable_diarization:
        diar_device = "cuda" if args.device.startswith("cuda") else "cpu"
        diar_engine = DiarizationEngine(
            hf_token=args.hf_token,
            device=diar_device,
            model_id=args.diarization_model,
            backend=args.diarization_backend,
            nemo_num_speakers=(args.nemo_num_speakers if args.nemo_num_speakers > 0 else None),
            nemo_out_dir=args.nemo_out_dir,
        )

    targets = find_audio_files(input_dirs)
    if not targets:
        logging.warning("처리할 오디오 파일이 없습니다.")
        return 0

    logging.info("총 %d개 파일 처리 시작", len(targets))

    success_count = 0
    error_count = 0

    for category, audio_path in targets:
        try:
            logging.info("처리 중: [%s] %s", category, audio_path)
            process_single_file(
                category=category,
                audio_path=audio_path,
                output_root=output_root,
                stt_engine=stt_engine,
                diar_engine=diar_engine,
                fallback_speakers=args.fallback_speakers,
            )
            success_count += 1
        except Exception as exc:
            error_count += 1
            logging.error("파일 처리 실패: %s | %s", audio_path, exc)
            logging.debug(traceback.format_exc())

    logging.info("처리 완료 - 성공: %d, 실패: %d", success_count, error_count)
    logging.info("출력 위치: %s", output_root.resolve())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
