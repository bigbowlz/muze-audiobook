from chunk_text import split_paragraphs, build_chunks, split_sentences, _ABBREVS


def test_split_paragraphs_keeps_single_newlines_together():
    text = "First sentence.\nSecond sentence."
    result = split_paragraphs(text)
    assert result == ["First sentence.\nSecond sentence."]


def test_split_paragraphs_on_blank_lines():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird."
    result = split_paragraphs(text)
    assert result == ["First paragraph.", "Second paragraph.", "Third."]


def test_split_paragraphs_strips_empty():
    text = "Para one.\n\n\n\nPara two."
    result = split_paragraphs(text)
    assert len(result) == 2
    assert result[0] == "Para one."


def test_build_chunks_respects_max_words():
    # 20 short sentences of 10 words each = 200 words; should produce 2 chunks
    sentence = "This is exactly ten words long in this here sentence."  # 10 words
    paragraphs = [sentence] * 20
    chunks = build_chunks(paragraphs, max_words=150)
    for chunk in chunks:
        assert len(chunk.split()) <= 150


def test_build_chunks_keeps_each_paragraph_separate():
    # Short paragraphs are no longer merged — each stays its own chunk
    para = "Short para has five words."  # 5 words
    paragraphs = [para] * 3
    chunks = build_chunks(paragraphs, max_words=150)
    assert len(chunks) == 3


def test_build_chunks_keeps_oversized_paragraph_as_own_chunk():
    # A paragraph with NO sentence-ending punctuation cannot be sub-split
    # and should be kept as a single chunk regardless of word count
    long_para = " ".join(["word"] * 160)  # no .!? boundaries
    chunks = build_chunks([long_para], max_words=150)
    assert len(chunks) == 1
    assert chunks[0] == long_para


def test_build_chunks_output_is_non_empty_strings():
    paras = ["Hello world.", "Second sentence here.", "Third one."]
    chunks = build_chunks(paras, max_words=150)
    for chunk in chunks:
        assert isinstance(chunk, str)
        assert len(chunk.strip()) > 0


def test_split_sentences_basic():
    text = "First sentence. Second sentence. Third one."
    result = split_sentences(text)
    assert result == ["First sentence.", "Second sentence.", "Third one."]


def test_split_sentences_merges_abbreviation():
    # "Dr." must not be treated as a sentence boundary
    text = "This is a test. Dr. Smith went to the store. Then he left."
    result = split_sentences(text)
    assert any("Dr. Smith" in part for part in result), f"Abbreviation split incorrectly: {result}"
    # "Dr." must not appear as a standalone fragment
    assert not any(part.strip() == "Dr." for part in result)


def test_build_chunks_splits_oversized_paragraphs():
    # A paragraph of 200 words that has sentence boundaries should be split
    sentence = "This is ten words long for sure right here now."  # 10 words
    big_para = " ".join([sentence] * 20)  # 200 words, multiple sentences
    chunks = build_chunks([big_para], max_words=150)
    for chunk in chunks:
        assert len(chunk.split()) <= 150


def test_build_chunks_regroups_sentences():
    # After splitting a long paragraph, sentences should be recombined greedily —
    # not emitted as individual TTS calls.
    sentence = "This is ten words long for sure right here now."  # 10 words
    big_para = " ".join([sentence] * 20)  # 200 words
    chunks = build_chunks([big_para], max_words=150)
    # Should produce 2 dense chunks, not 20 individual sentences
    assert len(chunks) == 2
    assert len(chunks[0].split()) == 150
    assert len(chunks[1].split()) == 50
