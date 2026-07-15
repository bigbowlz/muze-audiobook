#!/usr/bin/env python3
"""Split a unit raw text file into TTS-safe chunks (<=150 words, paragraph boundaries)."""

import argparse
import json
import re
from pathlib import Path

MAX_WORDS = 150

# Titles/abbreviations that end with "." but are not sentence boundaries.
_ABBREVS = frozenset({
    "Dr", "Mr", "Mrs", "Ms", "Prof", "Sr", "Jr", "St", "vs", "etc",
    "Fig", "Vol", "No", "pp", "approx", "dept", "est", "Rev", "Sq", "Ft",
})


def normalize_caps(text: str) -> str:
    """Convert ALL-CAPS words to title case so TTS pronounces them correctly."""
    return re.sub(r"\b[A-Z]{2,}\b", lambda m: m.group().title(), text)


def split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\n+", text)
    return [normalize_caps(p.strip()) for p in parts if p.strip()]


def split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[.!?])\s+", text)
    # Merge any bare abbreviation fragment ("Dr.", "Mr.", …) into the next part
    # so we never produce a 1-word chunk like "Dr." followed by "Leah Somerville…".
    merged: list[str] = []
    i = 0
    while i < len(raw):
        part = raw[i].strip()
        if not part:
            i += 1
            continue
        bare = part[:-1] if part.endswith(".") else None
        if bare and bare in _ABBREVS and i + 1 < len(raw):
            merged.append(part + " " + raw[i + 1].strip())
            i += 2
        else:
            merged.append(part)
            i += 1
    return [p for p in merged if p]


def build_chunks(paragraphs: list[str], max_words: int = MAX_WORDS) -> list[str]:
    chunks = []
    for para in paragraphs:
        if len(para.split()) <= max_words:
            chunks.append(para)
            continue
        # Paragraph is too long — split into sentences, then re-group greedily
        # so each group stays ≤ max_words and sentences aren't isolated TTS calls.
        sentences = split_sentences(para)
        group: list[str] = []
        group_words = 0
        for sent in sentences:
            sent_words = len(sent.split())
            if group and group_words + sent_words > max_words:
                chunks.append(" ".join(group))
                group = [sent]
                group_words = sent_words
            else:
                group.append(sent)
                group_words += sent_words
        if group:
            chunks.append(" ".join(group))
    return chunks


def main():
    parser = argparse.ArgumentParser(description="Chunk a unit raw text file for TTS")
    parser.add_argument("--book", required=True,
                        help="Book slug (a directory under configs/books/)")
    parser.add_argument("--unit", default=None,
                        help="Unit name to chunk (omit to chunk all units)")
    args = parser.parse_args()

    units_path = Path(f"configs/books/{args.book}/units.json")
    data_dir = Path(f"data/{args.book}")

    with open(units_path) as f:
        all_units = json.load(f)

    unit_names = [args.unit] if args.unit else [k for k in all_units if k != "source_path"]

    for unit_name in unit_names:
        input_path = data_dir / f"{unit_name}_raw.txt"
        output_path = data_dir / f"{unit_name}_chunks.json"

        text = input_path.read_text(encoding="utf-8")
        paragraphs = split_paragraphs(text)
        chunks = build_chunks(paragraphs)

        records = [
            {"id": i + 1, "text": chunk, "word_count": len(chunk.split())}
            for i, chunk in enumerate(chunks)
        ]

        output_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        total = sum(r["word_count"] for r in records)
        print(f"  {unit_name}: {len(records)} chunks, {total} words → {output_path}")


if __name__ == "__main__":
    main()
