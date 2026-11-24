from __future__ import annotations

from ..config import VerifierConfig
from ..models import CheckResult, Readings
from ..timeseries import EPS


def check_evidence_cross_check(
    readings: Readings,
    config: VerifierConfig,
) -> CheckResult:
    cc = readings.cross_check
    if cc is None:
        return CheckResult(
            check="evidence_cross_check",
            verdict="INCONCLUSIVE",
            reason="Cross-check metadata is missing",
        )

    cc_cfg = config.cross_check
    issues: list[str] = []

    if cc.verdict.upper() != "PASS":
        issues.append(
            cc.reason or f"log reader reported cross_check verdict '{cc.verdict}'"
        )
    if cc.compared <= 0:
        issues.append("no samples were compared (recording missing or empty)")
    if cc.unmatched > 0:
        issues.append(
            f"{cc.unmatched} log sample(s) had no matching recorded sample within "
            f"{cc_cfg.same_time_within_s} s"
        )
    if cc.over_limit > 0:
        issues.append(
            f"{cc.over_limit} sample(s) exceeded max difference "
            f"{cc_cfg.max_difference_m} m"
        )
    if cc.max_difference_m is not None and cc.max_difference_m > (
        cc_cfg.max_difference_m + EPS
    ):
        issues.append(
            f"max difference {cc.max_difference_m:.6f} m exceeded "
            f"limit {cc_cfg.max_difference_m} m"
        )
    if cc.publishers is not None and cc.publishers != 1:
        issues.append(f"pose topic had {cc.publishers} publishers (expected 1)")

    if issues:
        # Preserve order while deduplicating if cc.reason states the same failure
        unique_issues = list(dict.fromkeys(issues))
        return CheckResult(
            check="evidence_cross_check",
            verdict="INCONCLUSIVE",
            reason=f"Evidence cross-check failed: {'; '.join(unique_issues)}",
        )

    diff_text = (
        f", max difference {cc.max_difference_m:.6f} m"
        if cc.max_difference_m is not None
        else ""
    )
    return CheckResult(
        check="evidence_cross_check",
        verdict="PASS",
        reason=(
            f"Compared {cc.compared} samples against recording"
            f"{diff_text} (limit {cc_cfg.max_difference_m} m)"
        ),
    )
