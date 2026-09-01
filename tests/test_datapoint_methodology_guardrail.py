from pathlib import Path


def test_research_spec_matches_datapoint_pairwise_contract():
    text = Path("RESEARCH_SPEC.md").read_text(encoding="utf-8")
    assert "Tie / no meaningful preference." not in text
    assert "forced-choice A/B" in text
    assert "one Datapoint comparison job per benchmark task" in text
    assert "primary 1–5 instruction-faithfulness endpoint is unchanged" in text
