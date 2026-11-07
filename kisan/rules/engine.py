"""State law rules engine (rule 5).

Rules are data in ``state_rules``, not code. An unreviewed rule never auto-approves.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StateRuleRow:
    state: str
    species: str
    action: str
    allowed: bool
    docs_required: list[str] = field(default_factory=list)
    note: str = ""
    legally_reviewed: bool = False


@dataclass
class RuleOutcome:
    blocked: bool = False
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def as_evidence(self) -> dict:
        return {"blocked": self.blocked, "flags": self.flags, "reasons": self.reasons}


def evaluate(
    rule: StateRuleRow | None,
    *,
    state: str,
    species: str,
    docs_present: set[str],
) -> RuleOutcome:
    out = RuleOutcome()
    if rule is None:
        out.flags.append(f"no sale rule configured for {species} in {state}")
        return out
    if not rule.allowed:
        out.blocked = True
        out.reasons.append(rule.note or f"sale of {species} is not permitted in {state}")
        return out
    if not rule.legally_reviewed:
        out.flags.append(f"{state} rules for {species} are pending legal review")
    missing = [d for d in rule.docs_required if d not in docs_present]
    if missing:
        out.flags.append("missing required documents: " + ", ".join(missing))
    return out
