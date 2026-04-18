"""
test_6c_thinking_strip.py — Unit tests for <thinking> tag stripping (6C).

Run:  pytest tests/test_6c_thinking_strip.py -v
"""
import pytest
from chat import _strip_thinking


# ── Basic cases ────────────────────────────────────────────────────────────────

def test_no_thinking_tag_passthrough():
    """Clean text with no thinking tags is returned unchanged."""
    text = "MXene has high electrical conductivity of ~10⁴ S/m."
    assert _strip_thinking(text) == text


def test_single_thinking_block_removed():
    """A complete <thinking>...</thinking> block is stripped, answer kept."""
    text = "<thinking>Let me reason through this step by step.</thinking>MXene conductivity is ~10⁴ S/m."
    result = _strip_thinking(text)
    assert "<thinking>" not in result
    assert "MXene conductivity is ~10⁴ S/m." in result


def test_multiline_thinking_block_removed():
    """Multi-line thinking block spanning many lines is fully stripped."""
    text = (
        "<thinking>\n"
        "First I should consider the filler loading.\n"
        "Then think about the matrix.\n"
        "Conclusion: use EMI SE values.\n"
        "</thinking>\n"
        "The shielding effectiveness is 45 dB at 1 GHz."
    )
    result = _strip_thinking(text)
    assert "<thinking>" not in result
    assert "</thinking>" not in result
    assert "45 dB at 1 GHz" in result


def test_unclosed_thinking_tag_strips_to_end():
    """If </thinking> is missing (split across tokens), everything from <thinking> onwards is stripped."""
    text = "Some preamble. <thinking>This is unfinished reasoning"
    result = _strip_thinking(text)
    assert "<thinking>" not in result
    assert "Some preamble." in result
    assert "unfinished reasoning" not in result


def test_case_insensitive_strip():
    """Tags with different casing are stripped."""
    text = "<THINKING>internal reasoning</THINKING>Final answer here."
    result = _strip_thinking(text)
    assert "internal reasoning" not in result
    assert "Final answer here." in result


def test_thinking_at_start():
    """Thinking block at very start of string leaves only the answer."""
    text = "<thinking>internal</thinking>The answer is 42."
    result = _strip_thinking(text)
    assert result == "The answer is 42."


def test_empty_string_passthrough():
    """Empty string input returns empty string."""
    assert _strip_thinking("") == ""


def test_none_input_passthrough():
    """None input is returned as-is (guard clause)."""
    assert _strip_thinking(None) is None


def test_multiple_thinking_blocks():
    """Two separate thinking blocks are both removed."""
    text = "<thinking>thought 1</thinking>Answer part 1. <thinking>thought 2</thinking>Answer part 2."
    result = _strip_thinking(text)
    assert "thought 1" not in result
    assert "thought 2" not in result
    assert "Answer part 1." in result
    assert "Answer part 2." in result


def test_no_extra_whitespace_at_edges():
    """Result is stripped of leading/trailing whitespace."""
    text = "<thinking>reasoning</thinking>   Clean answer.   "
    result = _strip_thinking(text)
    assert result == "Clean answer."
