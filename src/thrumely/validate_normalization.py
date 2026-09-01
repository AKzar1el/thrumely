from __future__ import annotations

from .capabilities import candidate_capabilities, validate_candidate_matrix


def normalization_report() -> str:
    blockers = validate_candidate_matrix()
    lines = ["STATIC_ONLY: Thrumely candidate normalization check"]
    for item in candidate_capabilities():
        pin = "pinned" if item.pinned_snapshot else "stable-alias"
        lines.append(
            f"- {item.backend_id}: model={item.model}; version={pin}; "
            f"operations={','.join(sorted(item.operations))}"
        )
    if blockers:
        lines.append("Static blockers:")
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("Static schema coverage: PASS")
    lines.append(
        "Scientific gate: live provider calibration remains required; "
        "this command does not establish quality-tier equivalence, API behavior, cost, or output comparability."
    )
    return "\n".join(lines)


def main() -> int:
    report = normalization_report()
    print(report)
    return 1 if validate_candidate_matrix() else 0


if __name__ == "__main__":
    raise SystemExit(main())
