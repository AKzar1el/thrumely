import pytest

from thrumely.scoring import (
    aspect_ratio_score,
    atomic_coverage,
    candidate_metric_registry,
    normalize_ocr_text,
    required_text_score,
)


def test_aspect_ratio_score_uses_relative_tolerance():
    assert aspect_ratio_score("16:9", 1600, 900) == 1.0
    assert aspect_ratio_score("16:9", 1610, 900, tolerance=0.02) == 1.0
    assert aspect_ratio_score("16:9", 1400, 900, tolerance=0.02) == 0.0
    with pytest.raises(ValueError):
        aspect_ratio_score("4:3", 800, 600)


def test_ocr_normalization_and_required_text_score():
    assert normalize_ocr_text("  MORNING--Roast!  ") == "morning roast"
    assert required_text_score((), "anything") is None
    assert required_text_score(("MORNING ROAST", "$3.50"), "Morning roast / $3.50") == 1.0
    assert required_text_score(("MORNING ROAST", "OPEN"), "Morning roast only") == 0.5


def test_atomic_coverage_returns_fraction_or_none():
    assert atomic_coverage((), set()) is None
    assert atomic_coverage(("a", "b", "c"), {"a", "c"}) == pytest.approx(2 / 3)
    with pytest.raises(ValueError, match="unknown"):
        atomic_coverage(("a",), {"z"})


def test_metric_registry_is_unique_and_model_metrics_are_not_primary():
    metrics = candidate_metric_registry()
    assert len(metrics) == len({metric.name for metric in metrics})
    names = {metric.name for metric in metrics}
    assert {"tifa_style_qa", "vqascore", "clipscore", "hpsv2", "pairwise_vlm_judge", "aspect_ratio", "required_text", "tool_validity"} <= names
    assert all(not metric.primary_eligible for metric in metrics if metric.requires_model)
    assert all(metric.implementation_status in {"implemented", "future_optional"} for metric in metrics)
