#!/usr/bin/env python3
"""Package audiobook WAV units into a single M4B file with chapter markers.

Run from the repository root:
    python3 scripts/make_m4b.py <book-slug> [--title "..."] [--author "..."]

Example:
    python3 scripts/make_m4b.py kwaidan-stories-and-studies-of-strange-things --author "Lafcadio Hearn"
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

AAC_BITRATE = "64k"
CHAPTER_PAUSE_SECONDS = 1.5


def unit_sort_key(unit_id: str) -> int:
    return int(unit_id.removeprefix("unit"))


def get_duration_seconds(wav_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            str(wav_path),
        ],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(result.stdout)["streams"]
    return float(streams[0]["duration"])


def build_ffmetadata(title: str, author: str, chapters: list[tuple[str, int, int]]) -> str:
    lines = [
        ";FFMETADATA1",
        f"title={title}",
        f"artist={author}",
        f"album={title}",
        "genre=Audiobook",
        "",
    ]
    for name, start_ms, end_ms in chapters:
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={name}",
            "",
        ]
    return "\n".join(lines)


def slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").title()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book", help="Book slug matching a directory in output/ and configs/books/")
    parser.add_argument("--title", help="Book title for metadata (default: derived from slug)")
    parser.add_argument("--author", default="Unknown", help="Book author for metadata (default: Unknown)")
    parser.add_argument("--cover", help="Path to cover image (PNG or JPG) to embed in the M4B")
    args = parser.parse_args()

    book_slug = args.book
    title = args.title or slug_to_title(book_slug)
    author = args.author
    cover = Path(args.cover) if args.cover else None
    if cover and not cover.exists():
        parser.error(f"Cover image not found: {cover}")

    units_path = Path("configs/books") / book_slug / "units.json"
    output_dir = Path("output") / book_slug

    if not units_path.exists():
        parser.error(f"No units config found at {units_path}")
    if not output_dir.exists():
        parser.error(f"No output directory found at {output_dir}")

    with open(units_path) as f:
        units = json.load(f)

    wav_files: list[Path] = []
    chapter_names: list[str] = []

    unit_keys = sorted((k for k in units if k.startswith("unit")), key=unit_sort_key)
    for key in unit_keys:
        unit_dir = output_dir / key
        wavs = sorted(unit_dir.glob("*.wav"))
        if not wavs:
            print(f"  skip {key}: no WAV in {unit_dir}")
            continue
        if len(wavs) > 1:
            print(f"  warn {key}: multiple WAVs, using {wavs[0].name}")
        wav_files.append(wavs[0])
        chapter_names.append(units[key]["name"])

    if not wav_files:
        print("No WAV files found — generate the audiobook first.")
        return 1

    print(f"Packaging {len(wav_files)} units for '{title}':")
    for name, wav in zip(chapter_names, wav_files):
        print(f"  {name}")
        print(f"    {wav}")

    print("\nMeasuring durations...")
    durations: list[float] = []
    for wav in wav_files:
        dur = get_duration_seconds(wav)
        durations.append(dur)
        print(f"  {wav.parent.name}: {dur / 60:.1f} min")

    total_seconds = sum(durations)
    print(f"  Total: {total_seconds / 60:.1f} min ({total_seconds / 3600:.2f} h)")

    chapters: list[tuple[str, int, int]] = []
    cursor = 0.0
    for name, dur in zip(chapter_names, durations):
        start_ms = int(cursor * 1000)
        total_dur = dur + CHAPTER_PAUSE_SECONDS
        end_ms = int((cursor + total_dur) * 1000)
        chapters.append((name, start_ms, end_ms))
        cursor += total_dur

    out_file = Path("output") / f"{book_slug}.m4b"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Generate a silence WAV matched to the first chapter's sample rate/channels.
        silence_wav = tmp_path / "silence.wav"
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(wav_files[0])],
            capture_output=True, text=True, check=True,
        )
        stream = json.loads(probe.stdout)["streams"][0]
        sample_rate = stream.get("sample_rate", "44100")
        channels = stream.get("channels", 1)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r={sample_rate}:cl={'stereo' if channels == 2 else 'mono'}",
                "-t", str(CHAPTER_PAUSE_SECONDS),
                str(silence_wav),
            ],
            check=True, capture_output=True,
        )

        concat_entries: list[str] = []
        for wav in wav_files:
            concat_entries.append(f"file '{wav.absolute()}'")
            concat_entries.append(f"file '{silence_wav.absolute()}'")

        concat_file = tmp_path / "concat.txt"
        concat_file.write_text("\n".join(concat_entries) + "\n")

        meta_file = tmp_path / "metadata.txt"
        meta_file.write_text(build_ffmetadata(title, author, chapters))

        print(f"\nEncoding → {out_file}")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(meta_file),
        ]
        if cover:
            cmd += ["-i", str(cover.absolute())]
        cmd += ["-map", "0:a"]
        if cover:
            cmd += ["-map", "2:v", "-c:v", "copy", "-disposition:v", "attached_pic"]
        cmd += [
            "-map_metadata", "1",
            "-c:a", "aac", "-b:a", AAC_BITRATE,
            "-f", "mp4",
            str(out_file),
        ]
        subprocess.run(cmd, check=True)

    size_mb = out_file.stat().st_size / 1024 / 1024
    print(f"Done: {out_file} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
