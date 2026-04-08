#!/usr/bin/env python3
"""
Build weakly-supervised phishing keyword lexicon from FSS audio dataset folders.

Input (default):
  downloads/fss_audio/대출사기형
  downloads/fss_audio/수사기관사칭형

Output (default):
  stt_output/fss_seed_keywords.json
  stt_output/fss_seed_dataset.jsonl

Why:
  - File names already contain rich sentence-like clues.
  - Even when STT quality is unstable, we can bootstrap a domain lexicon.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


LABEL_MAP = {
    "대출사기형": "loan_fraud",
    "수사기관사칭형": "agency_fraud",
}

DEFAULT_DATA_ROOT = Path("downloads/fss_audio")
DEFAULT_KEYWORDS_OUT = Path("stt_output/fss_seed_keywords.json")
DEFAULT_DATASET_OUT = Path("stt_output/fss_seed_dataset.jsonl")

# Very lightweight stopword list; extend as needed.
STOPWORDS = {
    "고객",
    "고객님",
    "안내",
    "연락",
    "확인",
    "진행",
    "저희",
    "본인",
    "있습니다",
    "합니다",
    "하는",
    "위해",
    "대한",
    "경우",
    "관련",
    "통해",
    "부터",
    "까지",
    "이제",
    "다시",
    "지금",
    "현재",
    "정도",
    "혹시",
    "으로",
    "에서",
    "에게",
    "하고",
    "라고",
    "입니다",
    "입니다",
    # HTML-like artifact tokens from scraped filenames.
    "span",
    "style",
    "font",
    "weight",
    "color",
    "bold",
    "blue",
    "red",
    "new",
    # Placeholder-like artifacts.
    "ooo",
    "oo",
}


@dataclass
class Sample:
    label: str
    text: str
    file_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build keyword lexicon from downloads/fss_audio weak labels."
    )
    parser.add_argument(
        "--data-root",
        default=str(DEFAULT_DATA_ROOT),
        help="FSS audio root path (contains 대출사기형 and 수사기관사칭형).",
    )
    parser.add_argument(
        "--keywords-out",
        default=str(DEFAULT_KEYWORDS_OUT),
        help="Output JSON file for generated keywords.",
    )
    parser.add_argument(
        "--dataset-out",
        default=str(DEFAULT_DATASET_OUT),
        help="Output JSONL file for weakly-labeled text dataset.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=120,
        help="Top-K keywords per label.",
    )
    parser.add_argument(
        "--min-doc-freq",
        type=int,
        default=3,
        help="Minimum document frequency in label folder.",
    )
    return parser.parse_args()


def normalize_filename_to_text(path: Path) -> str:
    """Convert filename stem into sentence-like Korean text."""
    text = path.stem
    text = text.replace("_", " ")
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\([^\)]*\)", " ", text)
    text = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> set[str]:
    """
    Very simple tokenization for mixed Korean/English/digits.
    Returns set for document-frequency scoring.
    """
    tokens = re.findall(r"[0-9A-Za-z가-힣]{2,}", text)
    cleaned = {
        tok.lower()
        for tok in tokens
        if tok.lower() not in STOPWORDS and not tok.isdigit()
    }
    return cleaned


def collect_samples(data_root: Path) -> list[Sample]:
    samples: list[Sample] = []
    for folder_name, label in LABEL_MAP.items():
        folder = data_root / folder_name
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".mp3", ".wav", ".m4a"}:
                continue
            text = normalize_filename_to_text(path)
            if not text:
                continue
            samples.append(
                Sample(
                    label=label,
                    text=text,
                    file_path=str(path.as_posix()),
                )
            )
    return samples


def build_keywords(
    samples: list[Sample],
    top_k: int,
    min_doc_freq: int,
) -> dict[str, list[str]]:
    by_label_docs: dict[str, list[set[str]]] = defaultdict(list)
    label_doc_count: dict[str, int] = defaultdict(int)
    for s in samples:
        tokens = tokenize(s.text)
        if tokens:
            by_label_docs[s.label].append(tokens)
        label_doc_count[s.label] += 1

    keywords: dict[str, list[str]] = {}
    labels = sorted(by_label_docs.keys())

    for label in labels:
        this_docs = by_label_docs[label]
        other_docs = []
        for other_label in labels:
            if other_label != label:
                other_docs.extend(by_label_docs[other_label])

        this_n = max(1, len(this_docs))
        other_n = max(1, len(other_docs))

        this_df = Counter()
        other_df = Counter()

        for doc_tokens in this_docs:
            this_df.update(doc_tokens)
        for doc_tokens in other_docs:
            other_df.update(doc_tokens)

        scored: list[tuple[str, float]] = []
        for token, df in this_df.items():
            if df < min_doc_freq:
                continue
            p_this = (df + 1) / (this_n + 2)
            p_other = (other_df.get(token, 0) + 1) / (other_n + 2)
            score = p_this - p_other
            if score > 0:
                scored.append((token, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        keywords[label] = [token for token, _ in scored[:top_k]]

    return keywords


def write_dataset_jsonl(samples: list[Sample], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for sample in samples:
            row = {
                "label": sample.label,
                "text": sample.text,
                "source": "filename_weak_label",
                "file_path": sample.file_path,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_keywords_json(
    samples: list[Sample],
    keywords: dict[str, list[str]],
    output_path: Path,
) -> None:
    label_counts = Counter(s.label for s in samples)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "downloads/fss_audio filename weak labels",
        "doc_counts": dict(label_counts),
        "loan_fraud_keywords": keywords.get("loan_fraud", []),
        "agency_fraud_keywords": keywords.get("agency_fraud", []),
        "notes": {
            "tokenizer": "regex:[0-9A-Za-z가-힣]{2,}",
            "scoring": "smoothed_docfreq_diff",
            "stopwords_size": len(STOPWORDS),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    data_root = Path(args.data_root)
    keywords_out = Path(args.keywords_out)
    dataset_out = Path(args.dataset_out)

    samples = collect_samples(data_root)
    if not samples:
        print(f"[ERROR] No audio files found under: {data_root}")
        return 1

    keywords = build_keywords(
        samples=samples,
        top_k=args.top_k,
        min_doc_freq=args.min_doc_freq,
    )

    write_dataset_jsonl(samples, dataset_out)
    write_keywords_json(samples, keywords, keywords_out)

    print(f"[OK] samples={len(samples)}")
    print(f"[OK] dataset={dataset_out}")
    print(f"[OK] keywords={keywords_out}")
    print(f"[INFO] loan_keywords={len(keywords.get('loan_fraud', []))}")
    print(f"[INFO] agency_keywords={len(keywords.get('agency_fraud', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
