import json
import pytest
from extract_unit import clean_text, extract_unit, load_unit_config


def test_clean_text_collapses_blank_lines():
    raw = "paragraph one\n\n\n\nparagraph two"
    assert clean_text(raw) == "paragraph one\n\nparagraph two"


def test_clean_text_collapses_multiple_spaces():
    raw = "word1   word2  word3"
    assert clean_text(raw) == "word1 word2 word3"


def test_clean_text_strips_edges():
    raw = "\n\n  hello world  \n\n"
    assert clean_text(raw) == "hello world"


def test_extract_unit_end_before_includes_marker():
    text = "First sentence. The marker ends here. Then more text follows."
    result = extract_unit(text, start_after=None, end_before="The marker ends here.", max_words=None)
    assert result == "First sentence. The marker ends here."


def test_extract_unit_raises_on_missing_end_before():
    text = "Some text that does not contain the marker."
    with pytest.raises(ValueError, match="end_before marker not found"):
        extract_unit(text, start_after=None, end_before="nonexistent marker.", max_words=None)


def test_extract_unit_end_before_excludes_text_after_marker():
    text = "Lead text. Everything else is just opinion. More text after."
    result = extract_unit(text, start_after=None, end_before="Everything else is just opinion.", max_words=None)
    assert result.endswith("Everything else is just opinion.")
    assert "More text after." not in result


def test_extract_unit_start_after_trims_prefix():
    text = "Preamble to skip. Real content starts here. End of content."
    result = extract_unit(text, start_after="Preamble to skip.", end_before=None, max_words=None)
    assert result.startswith("Real content starts here.")
    assert "Preamble to skip." not in result


def test_extract_unit_max_words_truncates():
    text = "one two three four five six seven eight nine ten"
    result = extract_unit(text, start_after=None, end_before=None, max_words=5)
    assert result == "one two three four five"


def test_load_unit_config_returns_config(tmp_path):
    units_data = {
        "unit2": {
            "name": "Chapter 2 - Avoiding bad data",
            "source_xhtml": "mobi8/OEBPS/Text/part0004.xhtml",
            "variant": "v02",
            "chunks_path": "data/demo-book/unit2_chunks.json"
        }
    }
    units_path = tmp_path / "units.json"
    units_path.write_text(json.dumps(units_data))

    config = load_unit_config(units_path, "unit2")

    assert config["source_xhtml"] == "mobi8/OEBPS/Text/part0004.xhtml"
    assert config["variant"] == "v02"


def test_load_unit_config_raises_on_missing_unit(tmp_path):
    units_path = tmp_path / "units.json"
    units_path.write_text(json.dumps({"unit1": {"source_xhtml": "part0003.xhtml", "variant": "v03"}}))

    with pytest.raises(ValueError, match="not found"):
        load_unit_config(units_path, "unit99")
