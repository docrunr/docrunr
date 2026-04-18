"""Tests for recursive deterministic chunking."""

from __future__ import annotations

import json

from docrunr.chunk import (
    ChunkingConfig,
    chunk_markdown,
    count_tokens,
    derive_source_doc_id,
    splitter_version,
)


class TestCountTokens:
    def test_counts(self) -> None:
        assert count_tokens("Hello world") > 0

    def test_empty(self) -> None:
        assert count_tokens("") == 0


class TestChunkConfig:
    def test_defaults(self) -> None:
        cfg = ChunkingConfig()
        assert cfg.chunk_size_tokens == 300
        assert cfg.chunk_overlap_tokens == 0
        assert cfg.max_chunk_tokens == 450
        assert cfg.separators == ("\n\n", "\n", ".", "?", "!", " ", "")

    def test_splitter_version_is_stable(self) -> None:
        assert splitter_version(ChunkingConfig()) == "recursive_v1_token300_overlap0"


class TestDeterminism:
    def test_chunk_ids_and_text_repeat(self) -> None:
        md = (
            "# Intro\n\n"
            "DocRunr keeps extraction deterministic. "
            "This paragraph exists to validate stable boundaries.\n\n"
            "## Methods\n\n"
            "Chunking should be recursive, boundary-aware, and token-centered."
        )
        source_id = derive_source_doc_id("determinism.md")
        first = chunk_markdown(md, source_doc_id=source_id)
        second = chunk_markdown(md, source_doc_id=source_id)

        assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
        assert [c.text for c in first] == [c.text for c in second]

    def test_serialization_repeatable(self) -> None:
        md = "# Title\n\nAlpha beta gamma.\n\nDelta epsilon zeta."
        source_id = derive_source_doc_id("stable-json.md")
        chunks = chunk_markdown(md, source_doc_id=source_id)
        first = json.dumps([c.to_dict() for c in chunks], ensure_ascii=False, sort_keys=True)
        second = json.dumps(
            [c.to_dict() for c in chunk_markdown(md, source_doc_id=source_id)],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert first == second

    def test_chunk_id_depends_on_text_not_index(self) -> None:
        shared = (
            "Shared chunk marker. " * 30
            + "This paragraph should remain a stable chunk when its position changes."
        )
        first = chunk_markdown(
            "# Shared\n\n" + shared,
            config=ChunkingConfig(
                chunk_size_tokens=120,
                chunk_overlap_tokens=0,
                max_chunk_tokens=160,
            ),
            source_doc_id=derive_source_doc_id("shared.md"),
        )
        second = chunk_markdown(
            "# Prefix\n\nPrefix paragraph.\n\n# Shared\n\n" + shared,
            config=ChunkingConfig(
                chunk_size_tokens=120,
                chunk_overlap_tokens=0,
                max_chunk_tokens=160,
            ),
            source_doc_id=derive_source_doc_id("shared.md"),
        )

        first_chunk = next(chunk for chunk in first if "Shared chunk marker." in chunk.text)
        second_chunk = next(chunk for chunk in second if "Shared chunk marker." in chunk.text)
        assert first_chunk.text == second_chunk.text
        assert first_chunk.chunk_id == second_chunk.chunk_id


class TestContentSafety:
    def test_no_empty_or_whitespace_chunks(self) -> None:
        md = " \n\n# Header\n\n  \nParagraph one.\n\n\t\nParagraph two.\n\n"
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("safe.md"))
        assert chunks
        assert all(c.text.strip() for c in chunks)

    def test_exact_duplicate_chunks_removed(self) -> None:
        sentence = (
            "Deterministic retrieval baselines need stable chunk boundaries and stable metadata. "
        )
        paragraph = sentence * 20  # comfortably below hard cap but near target range
        md = f"{paragraph}\n\n{paragraph}\n\n{paragraph}"
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("dupes.md"))
        assert len(chunks) == 1
        assert chunks[0].text == paragraph.strip()

    def test_overlap_is_zero_by_unique_chunks(self) -> None:
        md = "\n\n".join(f"Section {i}. " + ("text " * 120) for i in range(1, 7))
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("overlap.md"))
        assert chunks
        assert len({c.chunk_id for c in chunks}) == len(chunks)

    def test_chunk_text_preserves_internal_spacing(self) -> None:
        md = "A    B\n\n```python\nx =  1\n    return  x\n```\n"
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("spacing.md"))
        joined = "\n".join(c.text for c in chunks)
        assert "A    B" in joined
        assert "x =  1" in joined
        assert "    return  x" in joined


class TestSizeBehavior:
    def test_majority_nontrivial_chunks_in_operating_range(self) -> None:
        sentence = (
            "This deterministic chunking baseline balances token targets, split boundaries, "
            "and stable metadata for downstream retrieval quality."
        )
        md = "\n\n".join(
            f"{' '.join(sentence for _ in range(14))} Paragraph marker {i}." for i in range(30)
        )

        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("size-behavior.md"))
        non_trivial = [c for c in chunks if c.token_count >= 120]
        assert len(non_trivial) >= 10

        in_range = [c for c in non_trivial if 200 <= c.token_count <= 400]
        ratio = len(in_range) / len(non_trivial)
        assert ratio >= 0.85

    def test_hard_cap_enforced_for_near_unsplittable_text(self) -> None:
        unsplittable = "A" * 12000
        chunks = chunk_markdown(unsplittable, source_doc_id=derive_source_doc_id("cap.md"))
        assert chunks
        assert all(c.token_count <= 450 for c in chunks)


class TestMetadata:
    def test_metadata_stable(self) -> None:
        md = "\n\n".join(
            [
                "# Title",
                "Paragraph one with enough content to create at least one chunk.",
                "Paragraph two with deterministic offset checks.",
                "Paragraph three with additional content.",
            ]
        )
        source_id = derive_source_doc_id("offsets.md")
        first = chunk_markdown(md, source_doc_id=source_id)
        second = chunk_markdown(md, source_doc_id=source_id)

        assert [c.chunk_id for c in first] == [c.chunk_id for c in second]

        for idx, chunk in enumerate(first):
            assert chunk.chunk_index == idx
            assert chunk.source_doc_id == source_id
            assert chunk.char_count == len(chunk.text)
            assert chunk.splitter_version == "recursive_v1_token300_overlap0"

    def test_offsets_are_monotonic_and_exact(self) -> None:
        md = (
            "# Intro\n\n"
            "Paragraph alpha with enough content to force chunking. "
            * 12
            + "\n\n## Details\n\n"
            + "Paragraph beta with more content and stable offsets. " * 12
        )
        chunks = chunk_markdown(
            md,
            config=ChunkingConfig(
                chunk_size_tokens=80,
                chunk_overlap_tokens=0,
                max_chunk_tokens=120,
            ),
            source_doc_id=derive_source_doc_id("offset-coverage.md"),
        )

        assert len(chunks) > 1

        previous_end = 0
        for chunk in chunks:
            assert 0 <= chunk.start_offset < chunk.end_offset <= len(md)
            assert chunk.start_offset >= previous_end
            assert md[chunk.start_offset : chunk.end_offset] == chunk.text
            assert chunk.to_dict()["start_offset"] == chunk.start_offset
            assert chunk.to_dict()["end_offset"] == chunk.end_offset
            gap = md[previous_end : chunk.start_offset]
            assert gap.isspace() or gap == ""
            previous_end = chunk.end_offset

        trailing_gap = md[previous_end:]
        assert trailing_gap.isspace() or trailing_gap == ""


class TestEdgeCases:
    def test_very_short_doc(self) -> None:
        chunks = chunk_markdown("Hi.", source_doc_id=derive_source_doc_id("short.md"))
        assert len(chunks) == 1
        assert chunks[0].text == "Hi."

    def test_very_long_paragraph(self) -> None:
        paragraph = " ".join(f"Long paragraph content token-{i}." for i in range(3000))
        chunks = chunk_markdown(paragraph, source_doc_id=derive_source_doc_id("long-para.md"))
        assert len(chunks) > 1
        assert all(c.token_count <= 450 for c in chunks)

    def test_markdown_code_block_and_table(self) -> None:
        md = (
            "# Data\n\n"
            "```python\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```\n\n"
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| A | 1 |\n"
            "| B | 2 |\n"
        )
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("code-table.md"))
        joined = "\n".join(c.text for c in chunks)
        assert "```python" in joined
        assert "| Name | Value |" in joined

    def test_unicode_heavy_text(self) -> None:
        md = "こんにちは 世界 🌍 — naïve façade coöperate.\n\n" * 20
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("unicode.md"))
        assert chunks
        assert all(c.token_count > 0 for c in chunks)

    def test_many_headings_preserved(self) -> None:
        md = "\n\n".join([f"# H{i}\n\nContent for heading {i}." for i in range(1, 20)])
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("headings.md"))
        joined = "\n".join(c.text for c in chunks)
        assert "# H1" in joined
        assert "# H19" in joined

    def test_already_clean_short_sections(self) -> None:
        md = "# A\n\nalpha\n\n# B\n\nbeta\n\n# C\n\ngamma"
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("clean-short.md"))
        assert chunks
        assert all(c.text for c in chunks)


def _section_paths_for_keyword(markdown: str, keyword: str) -> list[list[str]]:
    chunks = chunk_markdown(
        markdown,
        config=ChunkingConfig(
            chunk_size_tokens=60,
            chunk_overlap_tokens=0,
            max_chunk_tokens=80,
        ),
        source_doc_id=derive_source_doc_id("section-path.md"),
    )
    return [chunk.section_path for chunk in chunks if keyword in chunk.text]


class TestSectionPath:
    def test_single_heading(self) -> None:
        md = "# Heading\n\nalpha beta gamma delta epsilon zeta eta theta."
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("single-heading.md"))
        assert chunks
        assert all(chunk.section_path == ["Heading"] for chunk in chunks)

    def test_nested_headings_are_ordered(self) -> None:
        md = (
            "# Introduction\n\n"
            "intro marker content.\n\n"
            "## Methods\n\n"
            "methods marker content.\n\n"
            "### Sampling\n\n"
            "sampling marker content."
        )
        assert _section_paths_for_keyword(md, "intro marker") == [["Introduction"]]
        assert _section_paths_for_keyword(md, "methods marker") == [["Introduction", "Methods"]]
        assert _section_paths_for_keyword(md, "sampling marker") == [
            ["Introduction", "Methods", "Sampling"]
        ]

    def test_shallower_heading_resets_deeper_path(self) -> None:
        md = "# A\n\na marker.\n\n## B\n\nb marker.\n\n### C\n\nc marker.\n\n## D\n\nd marker."
        assert _section_paths_for_keyword(md, "d marker") == [["A", "D"]]

    def test_preamble_before_first_heading_is_empty_path(self) -> None:
        md = "preamble marker.\n\n# Heading\n\ninside marker."
        assert _section_paths_for_keyword(md, "preamble marker") == [[]]
        assert _section_paths_for_keyword(md, "inside marker") == [["Heading"]]

    def test_section_path_is_deterministic(self) -> None:
        md = "# Intro\n\nalpha.\n\n## Details\n\nbeta.\n\n### Deep\n\ngamma."
        source_id = derive_source_doc_id("section-deterministic.md")
        first = chunk_markdown(md, target_tokens=40, source_doc_id=source_id)
        second = chunk_markdown(md, target_tokens=40, source_doc_id=source_id)
        assert [chunk.section_path for chunk in first] == [chunk.section_path for chunk in second]

    def test_serialization_includes_section_path(self) -> None:
        md = "# Intro\n\nalpha beta gamma"
        chunks = chunk_markdown(md, source_doc_id=derive_source_doc_id("section-json.md"))
        payload = [chunk.to_dict() for chunk in chunks]
        assert payload
        assert all("chunk_id" not in chunk for chunk in payload)
        assert all("section_path" in chunk for chunk in payload)

    def test_no_headings_uses_empty_path(self) -> None:
        chunks = chunk_markdown(
            "plain paragraph without headings.",
            source_doc_id=derive_source_doc_id("no-headings.md"),
        )
        assert chunks
        assert all(chunk.section_path == [] for chunk in chunks)

    def test_multiple_sibling_headings(self) -> None:
        md = "# Alpha\n\nalpha marker.\n\n# Beta\n\nbeta marker."
        assert _section_paths_for_keyword(md, "alpha marker") == [["Alpha"]]
        assert _section_paths_for_keyword(md, "beta marker") == [["Beta"]]

    def test_deep_heading_nesting(self) -> None:
        md = "# L1\n\n## L2\n\n### L3\n\n#### L4\n\n##### L5\n\n###### L6\n\ndeep marker."
        assert _section_paths_for_keyword(md, "deep marker") == [
            ["L1", "L2", "L3", "L4", "L5", "L6"]
        ]

    def test_empty_section_between_headings(self) -> None:
        md = "# A\n\n## B\n\n## C\n\nc marker."
        assert _section_paths_for_keyword(md, "c marker") == [["A", "C"]]

    def test_very_short_document(self) -> None:
        chunks = chunk_markdown("Hi.", source_doc_id=derive_source_doc_id("section-short.md"))
        assert chunks
        assert chunks[0].section_path == []
