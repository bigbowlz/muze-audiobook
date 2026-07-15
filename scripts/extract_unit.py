#!/usr/bin/env python3
"""Extract a text unit from a mobi or epub source file."""

import argparse
import json
import re
import zipfile
from pathlib import Path

import mobi
from bs4 import BeautifulSoup

def load_unit_config(units_path: Path, unit_name: str) -> dict:
    with open(units_path) as f:
        units = json.load(f)
    if unit_name not in units:
        raise ValueError(f"Unit '{unit_name}' not found in {units_path}")
    return units[unit_name]


def extract_source(source_path: Path) -> Path:
    suffix = source_path.suffix.lower()
    if suffix == ".mobi":
        tmpdir, _ = mobi.extract(str(source_path))
        return Path(tmpdir)
    elif suffix == ".epub":
        import tempfile
        tmpdir = tempfile.mkdtemp()
        with zipfile.ZipFile(source_path) as zf:
            zf.extractall(tmpdir)
        return Path(tmpdir)
    else:
        raise ValueError(f"Unsupported format: {suffix!r} (expected .mobi or .epub)")


def read_chapter(tmpdir: Path, xhtml_relative: str) -> str:
    with open(tmpdir / xhtml_relative, encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text()


def clean_text(raw: str) -> str:
    text = re.sub(r"\n{2,}", "\n\n", raw)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)  # line-wrap artifacts → space
    text = re.sub(r" +", " ", text)
    return text.strip()


def extract_unit(text: str, start_after: str | None, end_before: str | None, max_words: int | None) -> str:
    if start_after:
        idx = text.find(start_after)
        if idx == -1:
            raise ValueError(f"start_after marker not found: {start_after!r}")
        text = text[idx + len(start_after):].strip()
    if end_before:
        idx = text.find(end_before)
        if idx == -1:
            raise ValueError(f"end_before marker not found: {end_before!r}")
        text = text[:idx + len(end_before)].strip()
    if max_words:
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words])
    return text.strip()


def main():
    parser = argparse.ArgumentParser(description="Extract text units from a mobi or epub source")
    parser.add_argument("--book", required=True,
                        help="Book slug (a directory under configs/books/)")
    parser.add_argument("--unit", default=None,
                        help="Unit name to extract (omit to extract all units)")
    parser.add_argument("--start-after", default=None,
                        help="Start extraction after this marker string (single-unit only)")
    parser.add_argument("--end-before", default=None,
                        help="End extraction at (and including) this marker string (single-unit only)")
    parser.add_argument("--max-words", type=int, default=None,
                        help="Truncate to this many words (single-unit only)")
    args = parser.parse_args()

    units_path = Path(f"configs/books/{args.book}/units.json")
    data_dir = Path(f"data/{args.book}")

    with open(units_path) as f:
        all_units = json.load(f)

    source_path = Path(all_units["source_path"])
    unit_names = [args.unit] if args.unit else [k for k in all_units if k != "source_path"]

    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting from {source_path}...")
    tmpdir = extract_source(source_path)

    for unit_name in unit_names:
        if unit_name not in all_units:
            raise ValueError(f"Unit '{unit_name}' not found in {units_path}")
        unit_config = all_units[unit_name]
        raw = read_chapter(tmpdir, unit_config["source_xhtml"])
        clean = clean_text(raw)
        start_after = args.start_after if args.unit else None
        end_before = args.end_before if args.unit else None
        max_words = args.max_words if args.unit else None
        text = extract_unit(clean, start_after, end_before, max_words)
        output_path = data_dir / f"{unit_name}_raw.txt"
        output_path.write_text(text, encoding="utf-8")
        print(f"  {unit_name}: {len(text.split())} words → {output_path}")


if __name__ == "__main__":
    main()
