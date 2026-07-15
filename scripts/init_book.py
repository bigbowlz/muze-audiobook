#!/usr/bin/env python3
"""Generate units.json and variants.json for a new book from an epub or mobi source."""

import argparse
import json
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

CONFIGS_DIR = Path("configs/books")
VARIANTS_TEMPLATE_PATH = Path("configs/variants_template.json")
DEFAULT_VARIANT = "v02"

BOILERPLATE_LABELS = {
    "cover", "other titles", "title page", "copyright", "contents",
    "table of contents", "endnotes", "notes", "glossary", "image credits",
    "acknowledgments", "index", "next reads", "about the author",
    "also by", "credits",
}

BOILERPLATE_FILE_RE = re.compile(
    r"_(cvi|cop|toc|nts|gls|cri|tp|adc|nav|bm|fm)_", re.IGNORECASE
)


def to_slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def is_boilerplate(label: str, xhtml_path: str) -> bool:
    if label.strip().lower() in BOILERPLATE_LABELS:
        return True
    if BOILERPLATE_FILE_RE.search(xhtml_path):
        return True
    return False


def parse_ncx(ncx_bytes: bytes, ncx_zip_path: str) -> tuple[str, str, list[dict]]:
    """Parse NCX file; return (title, author, chapters).

    source_xhtml in each chapter is relative to the archive root
    (epub zip root or mobi extraction dir).
    """
    ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
    root = ET.fromstring(ncx_bytes)

    title = root.findtext("ncx:docTitle/ncx:text", default="", namespaces=ns).strip()
    author = root.findtext("ncx:docAuthor/ncx:text", default="", namespaces=ns).strip()

    ncx_dir = posixpath.dirname(ncx_zip_path)

    chapters = []
    seen = set()
    for nav_point in root.findall(".//ncx:navPoint", ns):
        label = nav_point.findtext("ncx:navLabel/ncx:text", default="", namespaces=ns).strip()
        content = nav_point.find("ncx:content", ns)
        if content is None:
            continue
        src = content.get("src", "").split("#")[0]
        if not src.endswith(".xhtml"):
            continue
        full_path = posixpath.normpath(posixpath.join(ncx_dir, src)) if ncx_dir else src
        if full_path in seen:
            continue
        seen.add(full_path)
        chapters.append({"name": label, "source_xhtml": full_path})

    return title, author, chapters


def get_epub_chapters(epub_path: Path) -> tuple[str, str, list[dict]]:
    with zipfile.ZipFile(epub_path) as zf:
        ncx_names = [n for n in zf.namelist() if n.endswith(".ncx")]
        if not ncx_names:
            raise ValueError("No NCX file found in epub")
        ncx_zip_path = ncx_names[0]
        ncx_bytes = zf.read(ncx_zip_path)
    return parse_ncx(ncx_bytes, ncx_zip_path)


def get_mobi_chapters(mobi_path: Path) -> tuple[str, str, list[dict]]:
    import mobi as mobi_lib
    tmpdir, _ = mobi_lib.extract(str(mobi_path))
    tmpdir = Path(tmpdir)
    ncx_files = list(tmpdir.rglob("*.ncx"))
    if not ncx_files:
        raise ValueError("No NCX file found in extracted mobi")
    ncx_file = ncx_files[0]
    ncx_relative = ncx_file.relative_to(tmpdir).as_posix()
    return parse_ncx(ncx_file.read_bytes(), ncx_relative)


def main():
    parser = argparse.ArgumentParser(description="Generate book config from epub or mobi")
    parser.add_argument("--source", required=True, help="Path to source .epub or .mobi file")
    parser.add_argument("--slug", default=None,
                        help="Book slug (auto-generated from title + author if omitted)")
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        parser.error(f"Source file not found: {source_path}")

    suffix = source_path.suffix.lower()
    if suffix == ".epub":
        title, author, chapters = get_epub_chapters(source_path)
    elif suffix == ".mobi":
        title, author, chapters = get_mobi_chapters(source_path)
    else:
        parser.error(f"Unsupported format: {suffix!r} (expected .epub or .mobi)")

    slug = args.slug or to_slug(f"{title} {author}")

    book_dir = CONFIGS_DIR / slug
    if book_dir.exists():
        parser.error(f"Config already exists: {book_dir} — use --slug to choose a different name")

    print(f"\nBook:   {title}")
    print(f"Author: {author}")
    print(f"Slug:   {slug}")
    print(f"Source: {source_path}\n")
    print("Chapters:")

    units: dict = {}
    unit_idx = 0
    for ch in chapters:
        if is_boilerplate(ch["name"], ch["source_xhtml"]):
            print(f"  skip    {ch['name']!r}")
            continue
        unit_id = f"unit{unit_idx}"
        units[unit_id] = {
            "name": ch["name"],
            "source_xhtml": ch["source_xhtml"],
            "variant": DEFAULT_VARIANT,
        }
        print(f"  {unit_id}  {ch['name']!r}")
        unit_idx += 1

    book_dir.mkdir(parents=True)

    units_data = {"source_path": str(source_path), **units}
    units_path = book_dir / "units.json"
    units_path.write_text(json.dumps(units_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n→ {units_path}")

    with open(VARIANTS_TEMPLATE_PATH) as f:
        variants_data = json.load(f)
    variants_path = book_dir / "variants.json"
    variants_path.write_text(json.dumps(variants_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"→ {variants_path}")

    print(f"\nNext steps:")
    print(f"  python3 scripts/extract_unit.py --book {slug}")
    print(f"  python3 scripts/chunk_text.py --book {slug}")
    print(f"  python3 scripts/run_benchmark.py --book {slug} --unit unit0 --phase 2")
    print(f"  # review benchmark output, update variant assignments in {units_path}")
    print(f"  # then run production:")
    print(f"  for unit in {' '.join(units.keys())}; do")
    print(f"    python3 scripts/run_benchmark.py --book {slug} --unit $unit --phase 2 --production")
    print(f"  done")
    print(f"  python3 scripts/make_m4b.py {slug} --author \"{author}\"")


if __name__ == "__main__":
    main()
