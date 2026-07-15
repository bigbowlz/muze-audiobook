import json
from pathlib import Path

import numpy as np
import pytest

from run_benchmark import make_silence, load_configs, build_output_filename, resolve_production_variant


def test_make_silence_correct_length():
    silence = make_silence(seconds=1.2, sample_rate=24000)
    assert len(silence) == 28800  # 1.2 * 24000


def test_make_silence_is_zeros():
    silence = make_silence(seconds=0.5, sample_rate=24000)
    assert np.all(silence == 0.0)


def test_make_silence_dtype():
    silence = make_silence(seconds=0.1, sample_rate=24000)
    assert silence.dtype == np.float32


def test_load_configs_phase1_only(tmp_path):
    variants_data = {
        "variants": [
            {"id": "v01", "voice": "default", "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8, "phase": 1},
            {"id": "v07", "voice": "clone1", "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8, "phase": 2},
        ]
    }
    voices_data = {"default": None, "clone1": "source_media/voices/clone1.wav"}

    variants_path = tmp_path / "variants.json"
    voices_path = tmp_path / "voices.json"
    variants_path.write_text(json.dumps(variants_data))
    voices_path.write_text(json.dumps(voices_data))

    variants, voices = load_configs(variants_path, voices_path, phase=1)
    assert len(variants) == 1
    assert variants[0]["id"] == "v01"
    assert voices["default"] is None


def test_load_configs_phase2_only(tmp_path):
    variants_data = {
        "variants": [
            {"id": "v01", "voice": "default", "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8, "phase": 1},
            {"id": "v07", "voice": "clone1", "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8, "phase": 2},
        ]
    }
    voices_data = {"default": None, "clone1": "source_media/voices/clone1.wav"}

    variants_path = tmp_path / "variants.json"
    voices_path = tmp_path / "voices.json"
    variants_path.write_text(json.dumps(variants_data))
    voices_path.write_text(json.dumps(voices_data))

    variants, voices = load_configs(variants_path, voices_path, phase=2)
    assert len(variants) == 1
    assert variants[0]["id"] == "v07"


def test_build_output_filename():
    variant = {"id": "v01", "voice": "default", "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8}
    name = build_output_filename("unit1", variant)
    assert name == "unit1_v01_default_e0.5_c0.5_t0.8.wav"


def test_skip_existing_filters_completed(tmp_path):
    """build_output_filename output used to determine which variants to skip."""
    variants = [
        {"id": "v01", "voice": "default", "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8},
        {"id": "v02", "voice": "default", "exaggeration": 0.3, "cfg_weight": 0.5, "temperature": 0.8},
    ]
    # Simulate v01 already written
    (tmp_path / build_output_filename("unit1", variants[0])).touch()

    remaining = [v for v in variants
                 if not (tmp_path / build_output_filename("unit1", v)).exists()]
    assert len(remaining) == 1
    assert remaining[0]["id"] == "v02"


def test_resolve_production_variant_returns_correct_variant(tmp_path):
    units_data = {
        "unit2": {
            "name": "Chapter 2",
            "source_xhtml": "mobi8/OEBPS/Text/part0004.xhtml",
            "variant": "v02",
            "chunks_path": "data/demo-book/unit2_chunks.json"
        }
    }
    units_path = tmp_path / "units.json"
    units_path.write_text(json.dumps(units_data))
    all_variants = [
        {"id": "v02", "voice": "narrator_a", "exaggeration": 0.5, "cfg_weight": 0.7, "temperature": 0.8, "phase": 2},
        {"id": "v03", "voice": "narrator_b", "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8, "phase": 2},
    ]

    result = resolve_production_variant(units_path, "unit2", all_variants)

    assert result["id"] == "v02"
    assert result["voice"] == "narrator_a"


def test_resolve_production_variant_raises_on_missing_unit(tmp_path):
    units_path = tmp_path / "units.json"
    units_path.write_text(json.dumps({"unit1": {"variant": "v03"}}))

    with pytest.raises(ValueError, match="unit99.*not found"):
        resolve_production_variant(units_path, "unit99", [])


def test_resolve_production_variant_raises_when_variant_id_absent(tmp_path):
    units_path = tmp_path / "units.json"
    units_path.write_text(json.dumps({"unit2": {"variant": "v99"}}))
    all_variants = [
        {"id": "v02", "voice": "narrator_a", "exaggeration": 0.5, "cfg_weight": 0.7, "temperature": 0.8, "phase": 2},
    ]

    with pytest.raises(ValueError, match="v99.*not found in variants"):
        resolve_production_variant(units_path, "unit2", all_variants)
