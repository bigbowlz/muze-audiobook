#!/usr/bin/env python3
"""Run TTS benchmark variants for a given unit, or produce all units in one model load."""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torchaudio as ta

VOICES_PATH = Path("configs/voices.json")
SAMPLE_RATE = 24000  # Chatterbox S3GEN_SR
DEFAULT_SILENCE_SECONDS = 0.8
# S3 tokenizer runs at 25 tokens/sec; 150 words at ~2.5 words/sec needs ~1500 tokens.
# The model config ceiling is 4096. Use that so no chunk is ever silently truncated.
MAX_SPEECH_TOKENS = 4096
OUTPUT_DIR_BASE = Path("output")


def make_silence(seconds: float, sample_rate: int) -> np.ndarray:
    return np.zeros(int(seconds * sample_rate), dtype=np.float32)


def load_configs(variants_path: Path, voices_path: Path, phase: int):
    with open(variants_path) as f:
        all_variants = json.load(f)["variants"]
    with open(voices_path) as f:
        voices = json.load(f)
    variants = [v for v in all_variants if v["phase"] == phase]
    return variants, voices


def load_chunks(chunks_path: Path) -> list[dict]:
    with open(chunks_path) as f:
        return json.load(f)


def resolve_production_variant(units_path: Path, unit_name: str, all_variants: list[dict]) -> dict:
    with open(units_path) as f:
        units = json.load(f)
    if unit_name not in units:
        raise ValueError(f"Unit '{unit_name}' not found in {units_path}")
    variant_id = units[unit_name]["variant"]
    matches = [v for v in all_variants if v["id"] == variant_id]
    if not matches:
        raise ValueError(f"Variant '{variant_id}' not found in variants config")
    return matches[0]


def build_output_filename(unit_id: str, variant: dict, silence_seconds: float | None = None) -> str:
    v = variant
    base = f"{unit_id}_{v['id']}_{v['voice']}_e{v['exaggeration']}_c{v['cfg_weight']}_t{v['temperature']}"
    if silence_seconds is not None:
        base += f"_s{silence_seconds}"
    return base + ".wav"


def select_units_interactive(units_path: Path) -> list[str]:
    import questionary
    with open(units_path) as f:
        all_units = json.load(f)
    unit_keys = [k for k in all_units if k != "source_path"]
    choices = [
        questionary.Choice(
            title=f"{uid}  {all_units[uid]['name']}",
            value=uid,
            checked=True,
        )
        for uid in unit_keys
    ]
    selected = questionary.checkbox("Select units to process:", choices=choices).ask()
    return selected or []


def run_variant(model, variant: dict, chunks: list[dict], voices: dict, output_dir: Path,
                silence_seconds: float = DEFAULT_SILENCE_SECONDS, unit_id: str = "unit1"):
    vid = variant["id"]
    voice_name = variant["voice"]
    voice_path = voices[voice_name]

    print(f"\n[{vid}] voice={voice_name} exag={variant['exaggeration']} cfg={variant['cfg_weight']} temp={variant['temperature']}")

    audio_parts = []
    silence = make_silence(silence_seconds, SAMPLE_RATE)

    for i, chunk in enumerate(chunks):
        print(f"  chunk {chunk['id']:02d}/{len(chunks)} ({chunk['word_count']} words)...", end=" ", flush=True)

        # Pass audio_prompt_path only on the first chunk of each variant.
        # This triggers prepare_conditionals internally, caching conds on model.
        # Subsequent chunks reuse model.conds without re-loading the reference audio.
        audio_prompt = voice_path if (i == 0 and voice_path is not None) else None

        wav = model.generate(
            text=chunk["text"],
            audio_prompt_path=audio_prompt,
            exaggeration=variant["exaggeration"],
            cfg_weight=variant["cfg_weight"],
            temperature=variant["temperature"],
            max_new_tokens=MAX_SPEECH_TOKENS,
        )
        audio_parts.append(wav.squeeze(0).numpy())
        audio_parts.append(silence)
        print("done")

    # Drop trailing silence pad before concatenating
    final = np.concatenate(audio_parts[:-1])
    final_tensor = torch.from_numpy(final).unsqueeze(0)

    filename = build_output_filename(unit_id, variant, silence_seconds)
    out_path = output_dir / filename
    ta.save(str(out_path), final_tensor, SAMPLE_RATE)
    duration = len(final) / SAMPLE_RATE
    print(f"  → {out_path} ({duration:.1f}s)")


def main():
    parser = argparse.ArgumentParser(description="Run Chatterbox TTS benchmark variants")
    parser.add_argument("--book", required=True,
                        help="Book slug (a directory under configs/books/)")
    parser.add_argument("--phase", type=int, required=True, choices=[1, 2])
    parser.add_argument("--unit", type=str, default=None,
                        help="Unit to process; omit with --production for interactive multi-unit selection")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip variants whose output WAV already exists")
    parser.add_argument("--silence", type=float, default=DEFAULT_SILENCE_SECONDS,
                        help=f"Seconds of silence between chunks (default: {DEFAULT_SILENCE_SECONDS})")
    parser.add_argument("--variant", type=str,
                        help="Run only this variant id (e.g. v01); benchmark mode only")
    parser.add_argument("--production", action="store_true",
                        help="Read variant from units.json; output to output/ instead of benchmark/")
    args = parser.parse_args()

    if args.production and args.variant:
        parser.error("--production and --variant are mutually exclusive")

    variants_path = Path(f"configs/books/{args.book}/variants.json")
    units_path = Path(f"configs/books/{args.book}/units.json")
    all_variants, voices = load_configs(variants_path, VOICES_PATH, args.phase)

    # Determine units to process
    if args.unit:
        unit_names = [args.unit]
    elif args.production:
        unit_names = select_units_interactive(units_path)
        if not unit_names:
            print("No units selected.")
            return
    else:
        unit_names = ["unit1"]

    # Build per-unit jobs: (unit_name, chunks, variants_to_run, output_dir)
    jobs = []
    for unit_name in unit_names:
        chunks_path = Path(f"data/{args.book}/{unit_name}_chunks.json")
        chunks = load_chunks(chunks_path)

        if args.production:
            run_variants = [resolve_production_variant(units_path, unit_name, all_variants)]
            output_dir = OUTPUT_DIR_BASE / args.book / unit_name
        else:
            run_variants = list(all_variants)
            if args.variant:
                run_variants = [v for v in all_variants if v["id"] == args.variant]
                if not run_variants:
                    print(f"ERROR: variant '{args.variant}' not found in phase {args.phase}")
                    return
            output_dir = Path(f"benchmark/{args.book}/{unit_name}")

        if args.skip_existing:
            before = len(run_variants)
            run_variants = [v for v in run_variants
                            if not (output_dir / build_output_filename(unit_name, v, args.silence)).exists()]
            skipped = before - len(run_variants)
            if skipped:
                print(f"  {unit_name}: skipping {skipped} already-completed variant(s).")

        jobs.append((unit_name, chunks, run_variants, output_dir))

    # Validate voice files before loading model
    if args.phase == 2:
        needed = {v["voice"] for _, _, variants, _ in jobs for v in variants}
        missing = [name for name in needed if voices.get(name) and not Path(voices[name]).exists()]
        if missing:
            print(f"ERROR: Missing voice samples for: {', '.join(sorted(missing))}")
            print("Place WAV files (min 10s clean speech) in source_media/voices/ before running phase 2.")
            return

    total_variants = sum(len(vs) for _, _, vs, _ in jobs)
    if total_variants == 0:
        print("Nothing to do.")
        return

    from chatterbox.tts import ChatterboxTTS
    print("Loading Chatterbox model...")
    try:
        model = ChatterboxTTS.from_pretrained(device="cuda")
        device_used = "cuda"
    except RuntimeError as e:
        if "CUDA error" in str(e) or "kernel image" in str(e):
            print(f"CUDA not available ({e}), falling back to CPU")
            model = ChatterboxTTS.from_pretrained(device="cpu")
            device_used = "cpu"
        else:
            raise
    print(f"Model loaded on {device_used}. Processing {len(jobs)} unit(s), {total_variants} variant(s)...\n")

    for unit_name, chunks, run_variants, output_dir in jobs:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"── {unit_name} ──")
        for variant in run_variants:
            run_variant(model, variant, chunks, voices, output_dir, silence_seconds=args.silence, unit_id=unit_name)

    label = "production" if args.production else f"phase {args.phase}"
    print(f"\n{label} complete — {total_variants} variant(s) across {len(jobs)} unit(s)")


if __name__ == "__main__":
    main()
