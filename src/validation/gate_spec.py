"""
Declarative Gate Specifications (Proposal 3: Plugin Layer).

Gate decision logic as DATA, evaluated by a pure interpreter. Facts
extraction (WKT parsing, area measurement, evidence collection) stays in
code; every threshold, branch, and combinator moves into a serializable
GateSpec. Onboarding a new facility domain = writing a spec dict, not
patching engine code.

Design invariants:
  INV-9  Spec/data separation - the interpreter holds no domain knowledge;
         it only walks the constraint tree against a facts mapping.
  INV-10 Fail-closed specs - unknown operators or malformed trees raise at
         LOAD time (constraint_from_dict / GateSpec.validate), never
         silently pass at evaluate time.
  INV-11 Totality - evaluation never throws: any missing/None fact is a
         plain failed constraint, so a sparse facts dict cannot crash a gate.

Vocabulary (each node is a frozen dataclass, JSON-serializable):
  fact(field, op, value?)        - atomic predicate over facts[field]
  min_count(field, n)            - len(facts[field]) >= n (list facts)
  none_match(field, substrings)  - no element of facts[field] contains any
  all_of(children) / any_of(children) / not_(child)
  warn_if(child)                 - child failing downgrades to WARNED, not FAIL

GateSpec(gate_id, must, blocked?, warns?) outcome contract:
  blocked HOLDS  -> BLOCKED (hard, un-softenable)
  must fails     -> FAILED  (decision_ready=False)
  warns signaling, must holding -> WARNED (decision_ready=True)
  all good       -> PASSED
Signaling conventions for `warns` (both tested):
  - WarnIf-wrapped: the finding is non-empty exactly when the child fails.
  - Raw constraint: it states the GOOD condition; failing it warns.
`blocked` states the BAD condition: holding = hard failure.

The `op` registry is closed: adding an operator is an explicit code change,
which is what keeps specs auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


class SpecError(ValueError):
    """INV-10: malformed or unknown spec content, raised at load time."""


# ---------------------------------------------------------------------------
# Operator registry (closed world).
# ---------------------------------------------------------------------------

def _op_eq(fact, value):
    return fact == value


def _op_ne(fact, value):
    return fact != value


def _op_in(fact, value):
    return fact in value


def _op_not_in(fact, value):
    return fact not in value


def _op_gt(fact, value):
    return fact is not None and fact > value


def _op_gte(fact, value):
    return fact is not None and fact >= value


def _op_lt(fact, value):
    return fact is not None and fact < value


def _op_lte(fact, value):
    return fact is not None and fact <= value


def _op_between(fact, value):
    lo, hi = value
    return fact is not None and lo <= fact <= hi


def _op_nonempty(fact, _value):
    return bool(fact)


def _op_present(fact, _value):
    return fact is not None


def _op_regex(fact, value):
    return isinstance(fact, str) and re.search(value, fact) is not None


OPERATORS = {
    "eq": _op_eq,
    "ne": _op_ne,
    "in": _op_in,
    "not_in": _op_not_in,
    "gt": _op_gt,
    "gte": _op_gte,
    "lt": _op_lt,
    "lte": _op_lte,
    "between": _op_between,
    "nonempty": _op_nonempty,
    "present": _op_present,
    "regex": _op_regex,
}


# ---------------------------------------------------------------------------
# Constraint tree (data).
# ---------------------------------------------------------------------------

def _validate_child(child: Any) -> None:
    v = getattr(child, "validate", None)
    if v is not None:
        v()


@dataclass(frozen=True)
class Fact:
    """Atomic predicate: facts[field] compared via OPERATORS[op] to value."""
    field: str
    op: str
    value: Any = None

    def validate(self) -> None:
        if self.op not in OPERATORS:
            raise SpecError(f"unknown operator '{self.op}' for field "
                            f"'{self.field}' (INV-10)")


@dataclass(frozen=True)
class MinCount:
    field: str
    n: int

    def validate(self) -> None:
        if self.n < 0:
            raise SpecError("MinCount.n must be >= 0")


@dataclass(frozen=True)
class NoneMatch:
    """No element of facts[field] (a list of strings) contains any of the
    substrings - e.g. no evidence content mentions a contradiction."""
    field: str
    substrings: Tuple[str, ...]

    def validate(self) -> None:
        if not self.substrings:
            raise SpecError("NoneMatch requires at least one substring")


@dataclass(frozen=True)
class AllOf:
    children: Tuple[Any, ...]

    def validate(self) -> None:
        if not self.children:
            raise SpecError("AllOf requires children")
        for ch in self.children:
            _validate_child(ch)


@dataclass(frozen=True)
class AnyOf:
    children: Tuple[Any, ...]

    def validate(self) -> None:
        if not self.children:
            raise SpecError("AnyOf requires children")
        for ch in self.children:
            _validate_child(ch)


@dataclass(frozen=True)
class Not:
    child: Any

    def validate(self) -> None:
        _validate_child(self.child)


@dataclass(frozen=True)
class WarnIf:
    """A soft constraint: failing it downgrades the gate to WARNED
    (decision stays ready) instead of failing it."""

    child: Any

    def validate(self) -> None:
        _validate_child(self.child)


Constraint = Any  # Fact | MinCount | NoneMatch | AllOf | AnyOf | Not | WarnIf


# ---------------------------------------------------------------------------
# Serialization (INV-10 applies here too).
# ---------------------------------------------------------------------------

def constraint_to_dict(c: Constraint) -> Dict[str, Any]:
    if isinstance(c, Fact):
        d = {"node": "fact", "field": c.field, "op": c.op}
        if c.value is not None:
            d["value"] = c.value
        return d
    if isinstance(c, MinCount):
        return {"node": "min_count", "field": c.field, "n": c.n}
    if isinstance(c, NoneMatch):
        return {"node": "none_match", "field": c.field,
                "substrings": list(c.substrings)}
    if isinstance(c, AllOf):
        return {"node": "all_of",
                "children": [constraint_to_dict(ch) for ch in c.children]}
    if isinstance(c, AnyOf):
        return {"node": "any_of",
                "children": [constraint_to_dict(ch) for ch in c.children]}
    if isinstance(c, Not):
        return {"node": "not", "child": constraint_to_dict(c.child)}
    if isinstance(c, WarnIf):
        return {"node": "warn_if", "child": constraint_to_dict(c.child)}
    raise SpecError(f"unserializable constraint {type(c).__name__}")


def constraint_from_dict(d: Dict[str, Any]) -> Constraint:
    node = d.get("node")
    if node == "fact":
        c = Fact(field=d["field"], op=d["op"], value=d.get("value"))
    elif node == "min_count":
        c = MinCount(field=d["field"], n=int(d["n"]))
    elif node == "none_match":
        c = NoneMatch(field=d["field"], substrings=tuple(d["substrings"]))
    elif node == "all_of":
        c = AllOf(children=tuple(constraint_from_dict(ch) for ch in d["children"]))
    elif node == "any_of":
        c = AnyOf(children=tuple(constraint_from_dict(ch) for ch in d["children"]))
    elif node == "not":
        c = Not(child=constraint_from_dict(d["child"]))
    elif node == "warn_if":
        c = WarnIf(child=constraint_from_dict(d["child"]))
    else:
        raise SpecError(f"unknown constraint node '{node}' (INV-10)")
    c.validate()
    return c


# ---------------------------------------------------------------------------
# GateSpec and the interpreter.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateSpec:
    """Declarative gate; see module docstring for the outcome contract."""

    gate_id: str
    must: Constraint
    blocked: Optional[Constraint] = None
    warns: Optional[Constraint] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"gate_id": self.gate_id,
                             "must": constraint_to_dict(self.must)}
        if self.blocked is not None:
            d["blocked"] = constraint_to_dict(self.blocked)
        if self.warns is not None:
            d["warns"] = constraint_to_dict(self.warns)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GateSpec":
        return cls(
            gate_id=d["gate_id"],
            must=constraint_from_dict(d["must"]),
            blocked=constraint_from_dict(d["blocked"]) if "blocked" in d else None,
            warns=constraint_from_dict(d["warns"]) if "warns" in d else None,
        )

    def validate(self) -> None:
        """INV-10: full recursive validation, load-time."""
        self.must.validate()
        if self.blocked is not None:
            self.blocked.validate()
        if self.warns is not None:
            self.warns.validate()


@dataclass(frozen=True)
class GateOutcome:
    """Result of interpreting a spec against facts. Status vocabulary mirrors
    the pipeline's ValidationStatus without importing it."""

    gate_id: str
    status: str
    decision_ready: bool
    findings: Tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "PASSED"


def _eval(c: Constraint, facts: Dict[str, Any]) -> Tuple[bool, str]:
    """Returns (holds, finding). Totality (INV-11): missing facts are False
    with a finding, never exceptions. WarnIf nodes never fail their parent:
    a failing WarnIf child records a finding but holds."""
    if isinstance(c, WarnIf):
        holds, finding = _eval(c.child, facts)
        return True, (finding if not holds else "")
    if isinstance(c, Fact):
        try:
            holds = OPERATORS[c.op](facts.get(c.field), c.value)
        except (TypeError, ValueError):
            holds = False
        return holds, f"{c.field}:{c.op}:{c.value}"
    if isinstance(c, MinCount):
        seq = facts.get(c.field) or []
        return len(seq) >= c.n, f"{c.field}:count<{c.n}"
    if isinstance(c, NoneMatch):
        seq = facts.get(c.field) or []
        bad = [s for s in seq
               if any(sub in str(s) for sub in c.substrings)]
        if bad:
            return False, f"{c.field}:forbidden_match:{bad[0]}"
        return True, ""
    if isinstance(c, AllOf):
        for child in c.children:
            holds, finding = _eval(child, facts)
            if not holds:
                return False, finding
        return True, ""
    if isinstance(c, AnyOf):
        findings: List[str] = []
        for child in c.children:
            holds, finding = _eval(child, facts)
            if holds:
                return True, ""
            findings.append(finding)
        return False, findings[0] if findings else "any_of_empty"
    if isinstance(c, Not):
        holds, finding = _eval(c.child, facts)
        return (not holds), (f"not({finding})" if not holds else "")
    raise SpecError(f"uninterpretable constraint {type(c).__name__}")


def evaluate_spec(spec: GateSpec, facts: Dict[str, Any]) -> GateOutcome:
    """INV-9: pure interpretation. Order: blocked -> must -> warns.
    `blocked` HOLDING means a hard-fail condition is present (any bad-fact
    detector fired) -> BLOCKED, un-softenable by warns."""
    if spec.blocked is not None:
        holds, finding = _eval(spec.blocked, facts)
        if holds:
            return GateOutcome(spec.gate_id, "BLOCKED", False, (finding,))

    holds, finding = _eval(spec.must, facts)
    if not holds:
        return GateOutcome(spec.gate_id, "FAILED", False, (finding,))

    warn_findings: List[str] = []
    if spec.warns is not None:
        if isinstance(spec.warns, WarnIf):
            # WarnIf convention: holds is always True; the finding is
            # non-empty exactly when the child condition fails.
            _, w_finding = _eval(spec.warns, facts)
            if w_finding:
                warn_findings.append(w_finding)
        else:
            # Raw convention: the constraint states the GOOD condition;
            # failing it produces the warning.
            w_holds, w_finding = _eval(spec.warns, facts)
            if not w_holds:
                warn_findings.append(w_finding)

    # Collect WarnIf findings anywhere inside must/blocked trees.
    def _collect_warns(node: Constraint) -> None:
        if isinstance(node, WarnIf):
            _, f = _eval(node, facts)
            if f:
                warn_findings.append(f)
        elif isinstance(node, (AllOf, AnyOf)):
            for ch in node.children:
                _collect_warns(ch)
        elif isinstance(node, Not):
            _collect_warns(node.child)

    _collect_warns(spec.must)
    if spec.blocked is not None:
        _collect_warns(spec.blocked)

    if warn_findings:
        return GateOutcome(spec.gate_id, "WARNED", True,
                           tuple(warn_findings))
    return GateOutcome(spec.gate_id, "PASSED", True, ())
