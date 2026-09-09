"""Tests for evidence relevance filtering."""

from __future__ import annotations

from minos_core.evidence_relevance import (
    _tokenize,
    filter_relevant_evidence_refs,
)

# ---------------------------------------------------------------------------
# _tokenize
# ---------------------------------------------------------------------------

def test_tokenize_empty_string_returns_empty_set():
    assert _tokenize("") == set()
    assert _tokenize("   ") == set()


def test_tokenize_includes_bigrams_and_single_chars():
    tokens = _tokenize("ab")
    # Bigram "ab" + single chars "a", "b"
    assert "ab" in tokens
    assert "a" in tokens
    assert "b" in tokens


def test_tokenize_lowercases_input():
    tokens = _tokenize("Hello")
    assert "he" in tokens
    assert "h" in tokens
    assert "HE" not in tokens


def test_tokenize_chinese_text():
    tokens = _tokenize("冲压")  # 冲压
    assert "冲压" in tokens  # bigram 冲压
    assert "冲" in tokens  # single 冲
    assert "压" in tokens  # single 压


# ---------------------------------------------------------------------------
# filter_relevant_evidence_refs
# ---------------------------------------------------------------------------

# Shared fixture data
EVIDENCE_MATCHING = [
    {
        "evidence_id": "EV-001",
        "content": "冲压毛坯轮廓检查",  # 冲压毛坯轮廓检查
    },
    {
        "evidence_id": "EV-002",
        "content": "焊接强度测试报告",  # 焊接强度测试报告
    },
    {
        "evidence_id": "EV-003",
        "content": "stamping blank profile inspection report",
    },
    {
        "evidence_id": "EV-004",
        "content": "",  # empty content
    },
]


def test_matching_text_keeps_ref():
    """Evidence with matching text overlap is kept."""
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-001"],
        entity_text="冲压毛坯轮廓",
        available_evidence=EVIDENCE_MATCHING,
    )
    assert result == ["EV-001"]


def test_unrelated_text_filters_out():
    """Evidence with completely unrelated text is filtered out.

    Uses two refs — one relevant and one irrelevant — so the filtering is
    observable without the safety net kicking in.
    """
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-001", "EV-002"],  # stamping + welding
        entity_text="冲压毛坯轮廓",  # stamping text
        available_evidence=EVIDENCE_MATCHING,
    )
    # EV-001 (stamping) stays, EV-002 (welding) is dropped.
    assert "EV-001" in result
    assert "EV-002" not in result


def test_safety_net_keeps_first_when_all_filtered():
    """When all refs would be filtered out, at least the first one stays."""
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-002", "EV-001"],
        entity_text="注塑成型参数",  # injection molding — unrelated to both
        available_evidence=EVIDENCE_MATCHING,
    )
    # EV-002 is first in the input list, should be kept even though
    # its welding content has nothing to do with injection molding.
    assert result == ["EV-002"]


def test_empty_evidence_refs_returns_empty():
    """Empty input returns empty list."""
    result = filter_relevant_evidence_refs(
        evidence_refs=[],
        entity_text="anything",
        available_evidence=EVIDENCE_MATCHING,
    )
    assert result == []


def test_missing_evidence_in_available_kept_conservatively():
    """Evidence ref not found in available_evidence is kept (conservative)."""
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-999"],
        entity_text="anything",
        available_evidence=EVIDENCE_MATCHING,
    )
    assert result == ["EV-999"]


def test_empty_entity_text_keeps_all():
    """Empty entity text keeps all refs (conservative fallback)."""
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-001", "EV-002"],
        entity_text="",
        available_evidence=EVIDENCE_MATCHING,
    )
    assert result == ["EV-001", "EV-002"]


def test_empty_content_in_evidence_kept_conservatively():
    """Evidence with empty content is kept (can't prove irrelevance)."""
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-004"],
        entity_text="冲压毛坯轮廓",
        available_evidence=EVIDENCE_MATCHING,
    )
    assert result == ["EV-004"]


def test_mixed_relevant_and_irrelevant():
    """Mixed list: relevant kept, irrelevant dropped."""
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-003", "EV-002"],  # stamping English + welding Chinese
        entity_text="stamping blank inspection",
        available_evidence=EVIDENCE_MATCHING,
    )
    assert "EV-003" in result  # stamping matches stamping
    assert "EV-002" not in result  # welding unrelated


def test_english_cross_matching():
    """English entity text against English evidence content."""
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-003"],
        entity_text="stamping profile check",
        available_evidence=EVIDENCE_MATCHING,
    )
    assert result == ["EV-003"]


def test_english_no_cross_match():
    """English entity against Chinese-only evidence: no overlap, filtered.

    EV-001 has Chinese content, entity_text is pure Latin — zero character
    overlap. EV-002 also has Chinese content. Both filtered, safety net
    keeps EV-001 (first in list).
    """
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-001", "EV-002"],  # both Chinese content
        entity_text="welding strength test",  # pure ASCII, no CJK characters
        available_evidence=EVIDENCE_MATCHING,
    )
    # Chinese characters share zero bigrams with ASCII text — both filtered.
    # Safety net keeps EV-001.
    assert result == ["EV-001"]


def test_min_overlap_strict_threshold():
    """With a higher min_overlap, only strongly related evidence stays."""
    result = filter_relevant_evidence_refs(
        evidence_refs=["EV-001"],
        entity_text="冲压轮廓",  # partial overlap with 冲压毛坯轮廓检查
        available_evidence=EVIDENCE_MATCHING,
        min_overlap=0.3,  # higher bar
    )
    # Still has some bigram overlap (冲压 + 压毛 etc.)
    # With min_overlap=0.3 it should pass if overlap is above threshold
    assert result == ["EV-001"]
