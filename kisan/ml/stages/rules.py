"""Stage 7: state law (rule 5)."""

from __future__ import annotations

from kisan.ml.types import StageResult
from kisan.rules.engine import StateRuleRow, evaluate

NAME = "rules"


def run(rule: StateRuleRow | None, *, state: str, species: str, docs_present: set[str]) -> StageResult:
    out = evaluate(rule, state=state, species=species, docs_present=docs_present)
    return StageResult(
        name=NAME,
        passed=not out.blocked and not out.flags,
        score=None,
        flags=out.flags,
        blocked=out.blocked,
        block_reasons=out.reasons,
        evidence={"state": state, **out.as_evidence()},
    )
