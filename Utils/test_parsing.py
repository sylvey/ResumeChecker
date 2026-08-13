"""Unit tests for JD text splitting in Parsing.py. Pure functions over
text -- no database or PDF required.
"""

import pytest

from Parsing.Parsing import ParseError, parse_jd, split_jd_into_blocks, _looks_like_jd_heading


class TestLooksLikeJDHeading:
    def test_short_no_trailing_punctuation_is_heading(self):
        assert _looks_like_jd_heading("Bonus Points")
        assert _looks_like_jd_heading("Your Core Responsibilities")
        assert _looks_like_jd_heading("What Will Make You Successful")

    def test_ends_in_punctuation_is_not_heading(self):
        assert not _looks_like_jd_heading("Must be able to start June 7, 2027")
        assert not _looks_like_jd_heading("We are hiring.")

    def test_long_line_is_not_heading(self):
        assert not _looks_like_jd_heading(
            "Strong knowledge of algorithms and data structures is required for this role"
        )

    def test_empty_line_is_not_heading(self):
        assert not _looks_like_jd_heading("")


class TestSplitJDIntoBlocks:
    def test_header_immediately_followed_by_bullets_no_blank_line(self):
        # Regression test: real JDs often don't put a blank line between a
        # header and its own bullet list (see jd1.txt) -- blank-line
        # grouping alone would lump this all into one block.
        text = (
            "Your Core Responsibilities\n"
            "Work on meaningful projects.\n"
            "Participate in training.\n"
            "Your Skills and Experience\n"
            "Strong knowledge of algorithms and data structures is required.\n"
        )
        blocks = split_jd_into_blocks(text)
        headings = [b["heading"] for b in blocks]
        assert "Your Core Responsibilities" in headings
        assert "Your Skills and Experience" in headings

        resp_block = next(b for b in blocks if b["heading"] == "Your Core Responsibilities")
        assert "Participate in training." in resp_block["content"]
        assert "Strong knowledge" not in resp_block["content"]

    def test_text_before_first_heading_gets_empty_heading(self):
        text = (
            "Some intro line that is definitely long enough to not read as a heading.\n"
            "Real Heading\n"
            "Content here.\n"
        )
        blocks = split_jd_into_blocks(text)
        assert blocks[0]["heading"] == ""
        assert "intro line" in blocks[0]["content"]

    def test_heading_with_no_content_preserved_as_its_own_block(self):
        # A short marker line with nothing beneath it (e.g. a trailing
        # "#LI-DNP" tag) still gets its own block, even though its content
        # is empty.
        text = "Real Heading\nSome content.\n#LI-DNP\n"
        blocks = split_jd_into_blocks(text)
        tag_block = next(b for b in blocks if b["heading"] == "#LI-DNP")
        assert tag_block["content"] == ""

    def test_short_line_with_internal_punctuation_stays_as_content(self):
        # "Base Salary: $200,000" is short but has an internal colon and
        # comma, so it should NOT be misdetected as a heading -- it stays
        # part of the preceding block's content instead.
        text = "Real Heading\nSome content.\nBase Salary: $200,000\n"
        blocks = split_jd_into_blocks(text)
        assert not any(b["heading"] == "Base Salary: $200,000" for b in blocks)
        heading_block = next(b for b in blocks if b["heading"] == "Real Heading")
        assert "Base Salary: $200,000" in heading_block["content"]

    def test_empty_text_returns_no_blocks(self):
        assert split_jd_into_blocks("") == []


class TestParseJD:
    def test_empty_text_raises(self):
        with pytest.raises(ParseError):
            parse_jd("")
        with pytest.raises(ParseError):
            parse_jd("   ")

    def test_returns_raw_sections_shape(self):
        result = parse_jd("Role Overview\nWe build things.\n")
        assert list(result.keys()) == ["sections"]
        assert result["sections"][0]["heading"] == "Role Overview"
        assert result["sections"][0]["content"] == "We build things."
