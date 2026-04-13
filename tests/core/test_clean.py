"""Tests for Markdown cleaning."""

from __future__ import annotations

from docrunr.clean import clean_markdown


class TestCleanMarkdown:
    def test_collapse_blank_lines(self) -> None:
        result = clean_markdown("Hello\n\n\n\n\nWorld")
        assert "\n\n\n" not in result
        assert "Hello" in result
        assert "World" in result

    def test_strip_page_numbers(self) -> None:
        result = clean_markdown("Some text\n\n- 12 -\n\nMore text")
        assert "- 12 -" not in result

    def test_preserve_numeric_content_lines(self) -> None:
        result = clean_markdown("# Timeline\n\n2024\n\nRelease complete")
        assert "2024" in result

    def test_normalize_bullets(self) -> None:
        result = clean_markdown("• First item\n• Second item")
        assert "- First item" in result
        assert "- Second item" in result

    def test_trailing_newline(self) -> None:
        result = clean_markdown("Hello world")
        assert result.endswith("\n")

    def test_trailing_spaces_removed(self) -> None:
        result = clean_markdown("Hello   \nWorld   ")
        for line in result.split("\n"):
            assert line == line.rstrip()

    def test_nested_bullets_from_pdf_docling(self) -> None:
        text = "- Level 1\n- o Level 2\n- § Level 3\n- § Level 3.2\n"
        result = clean_markdown(text)
        assert "- Level 1" in result
        assert "  - Level 2" in result
        assert "    - Level 3" in result
        assert "    - Level 3.2" in result
        assert "- o " not in result
        assert "- § " not in result

    def test_nested_bullets_from_pdf_pypdfium(self) -> None:
        text = "- Level 1\no Level 2\n§ Level 3\n§ Level 3.2\n"
        result = clean_markdown(text)
        assert "- Level 1" in result
        assert "  - Level 2" in result
        assert "    - Level 3" in result
        assert "    - Level 3.2" in result

    def test_nested_bullets_from_markitdown(self) -> None:
        text = "* Level 1\n + Level 2\n - Level 3\n * Level 4\n - Level 3.2\n + Level 2.1\n"
        result = clean_markdown(text)
        lines = [line for line in result.strip().split("\n") if line.strip()]
        assert lines[0] == "- Level 1"
        assert lines[1] == "    - Level 2"
        assert lines[2] == "      - Level 3"
        assert lines[3] == "        - Level 4"
        assert lines[4] == "      - Level 3.2"
        assert lines[5] == "    - Level 2.1"

    def test_empty_input(self) -> None:
        result = clean_markdown("")
        assert result == "\n"

    def test_normalize_toc_markdown_table(self) -> None:
        text = (
            "# Table of Contents\n\n"
            "| Section | Page |\n"
            "| --- | --- |\n"
            "| Introduction ............ | 1 |\n"
            "| Methods | 3 |\n"
            "| Appendix ---- | |\n\n"
            "# Data\n\n"
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| A | 1 |\n"
        )

        result = clean_markdown(text)

        assert "Introduction — page 1" in result
        assert "Methods — page 3" in result
        assert "Appendix" in result
        assert "| Section | Page |" not in result
        assert "# Data" in result
        assert "| Name | Value |" in result
        assert "| A | 1 |" in result

    def test_normalize_toc_lines_multilingual_heading(self) -> None:
        text = "## Índice\n\n1 Introducción .......... 5\n2 Resultados ............ 9\n"
        result = clean_markdown(text)
        assert "1 Introducción — page 5" in result
        assert "2 Resultados — page 9" in result
        assert ".........." not in result

    def test_non_toc_data_table_is_preserved(self) -> None:
        text = (
            "# Budget\n\n| Item | Q1-Q2 |\n| ---- | ----- |\n| R&D | 100-200 |\n| Ops | 300-400 |\n"
        )
        result = clean_markdown(text)
        assert "# Budget" in result
        assert "| Item | Q1-Q2 |" in result
        assert "| ---- | ----- |" in result
        assert "| R&D | 100-200 |" in result

    def test_fenced_code_is_not_rewritten(self) -> None:
        text = "```bash\ncat a|grep x\nx    y\n* not a list\n```\n"
        result = clean_markdown(text)
        assert "cat a|grep x" in result
        assert "x    y" in result
        assert "* not a list" in result
        assert "- not a list" not in result

    def test_index_heading_table_is_not_treated_as_toc(self) -> None:
        text = "# Index\n\n| Item | Value |\n| --- | --- |\n| latency | 12 |\n| throughput | 48 |\n"
        result = clean_markdown(text)
        assert "| Item | Value |" in result
        assert "| latency | 12 |" in result
        assert "latency — page 12" not in result
