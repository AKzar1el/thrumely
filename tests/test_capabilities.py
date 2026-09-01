from thrumely.capabilities import (
    NORMALIZED_ASPECT_RATIOS,
    NORMALIZED_QUALITY_TIERS,
    ProviderCapability,
    candidate_capabilities,
    validate_candidate_matrix,
)


def test_candidate_capabilities_cover_three_image_backends() -> None:
    capabilities = candidate_capabilities()
    assert len(capabilities) == 3
    assert {item.backend_id for item in capabilities} == {
        "openai:gpt-image-2",
        "google:gemini-3.1-flash-image",
        "bfl:flux-2-pro",
    }
    assert len({item.backend_id for item in capabilities}) == len(capabilities)


def test_candidate_capabilities_cover_normalized_surface() -> None:
    for item in candidate_capabilities():
        assert {"generate", "edit_previous"}.issubset(item.operations)
        assert NORMALIZED_ASPECT_RATIOS.issubset(item.aspect_ratios)
        assert NORMALIZED_QUALITY_TIERS.issubset(item.quality_tiers)


def test_static_candidate_matrix_has_no_schema_blockers() -> None:
    assert validate_candidate_matrix() == ()


def test_validator_reports_missing_edit_support() -> None:
    broken = ProviderCapability(
        backend_id="example:broken",
        provider="example",
        model="broken-v1",
        operations=frozenset({"generate"}),
        aspect_ratios=NORMALIZED_ASPECT_RATIOS,
        quality_tiers=NORMALIZED_QUALITY_TIERS,
        pinned_snapshot=True,
        notes="test fixture",
    )
    blockers = validate_candidate_matrix((broken,))
    assert any("edit_previous" in blocker for blocker in blockers)
    assert any("exactly 3" in blocker for blocker in blockers)
