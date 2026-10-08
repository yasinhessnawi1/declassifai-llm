"""Record-level coherence: the cast of a document must be a possible family and a possible staff.

Pilot v4 shipped two kinds of impossible people. A psychologist's note about a 93-year-old
named his "parent", a 121-year-old, as a contact (the sampler drew a parent as the subject's
age plus 22 to 42 years, with no ceiling), and a security-clearance letter was signed by a
19-year-old (professionals were drawn from the "working" age band, whose lowest bracket is
18-29). Neither defect is in the model's text: the record was already wrong when the prompt
was built, so every call spent on it was wasted and the document was uselessly strange. This
module is the check that runs on the sampled cast before any prompt is built.

The rules, each a fact about a possible Norwegian household or workplace rather than a tuning
knob:

* **Professionals are 25-67.** An author, caseworker, physician, psychologist, vet, lawyer,
  officer, teacher, employer contact or creditor contact is qualified and has not retired.
* **No living parent past 100.** A parent over `MAX_LIVING_PARENT_AGE` is not a contact. The
  repair keeps the relation instead of dropping it where it can: a 93-year-old subject has a
  child of 55, not a parent of 121.
* **A parent is 16 to 55 years older than the child, and a child is that much younger.** A
  child is at least `MIN_PARENT_GAP` years younger than the subject (usually more); a
  93-year-old does not have a six-year-old.
* **A spouse is within 15 years of the subject, an adult, and not over 100.**

`enforce_cast` repairs what can be repaired (redraws an age inside the allowed range, flips a
too-old parent to a child, drops a member who cannot exist) and counts each outcome;
`check` is the independent test that the finished cast satisfies all of it, and
`generate_documents.new_attempt_record` rejects and resamples a record that fails it, so no
model call is made on it.
"""

from __future__ import annotations

import collections
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

PROFESSIONAL_ROLES = frozenset({
    "author", "physician", "psychologist", "veterinarian", "lawyer", "caseworker", "officer",
    "teacher", "employer_contact", "creditor_contact",
})
PROFESSIONAL_AGE = (25, 67)
MAX_LIVING_PARENT_AGE = 100
MIN_PARENT_GAP = 16
MAX_PARENT_GAP = 55
MAX_SPOUSE_GAP = 15
MIN_SPOUSE_AGE = 18
MAX_ANY_AGE = 105

# A role is "family of the subject" for the gap rules; a guardian is a relative only when the
# subject is a minor (an adult's guardian is a professional verge).
PARENT_ROLES = frozenset({"parent"})


@dataclass
class Member:
    """One cast member as the coherence rules see them.

    Attributes:
        role: Cast role id (`gendoc_genres.CAST_ROLES`) or "author".
        age: Age in whole years.
    """

    role: str
    age: int


@dataclass
class CoherenceReport:
    """What the coherence pass did to one record's cast.

    Attributes:
        checked: Cast members examined.
        violations: Rule ids found on the cast as drawn, in order.
        fixed: Members whose age was redrawn inside the allowed range.
        flipped: Parents turned into children because the parent would be too old.
        dropped: Members removed because no age could make them possible.
        notes: One line per action, for the metadata.
    """

    checked: int = 0
    violations: List[str] = field(default_factory=list)
    fixed: int = 0
    flipped: int = 0
    dropped: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """Whether the cast needed no repair."""
        return not self.violations

    def as_dict(self) -> dict:
        """Return the report as plain data for the document metadata."""
        return {"checked": self.checked, "violations": list(self.violations), "fixed": self.fixed,
                "flipped": self.flipped, "dropped": self.dropped, "notes": list(self.notes)}


def member_violations(subject_age: int, member: Member, subject_is_minor: Optional[bool] = None) -> List[str]:
    """Return the rule ids one member breaks, relative to the subject.

    Args:
        subject_age: The data subject's age.
        member: The cast member.
        subject_is_minor: Whether the subject is under 18; derived from `subject_age` if None.

    Returns:
        Rule ids, from `professional_age`, `parent_too_old`, `parent_gap`, `child_gap`,
        `spouse_age`, `implausible_age`; empty when the member is possible.
    """
    minor = subject_age < 18 if subject_is_minor is None else subject_is_minor
    out: List[str] = []
    role, age = member.role, member.age
    if age > MAX_ANY_AGE or age < 0:
        out.append("implausible_age")
    if role in PROFESSIONAL_ROLES and not PROFESSIONAL_AGE[0] <= age <= PROFESSIONAL_AGE[1]:
        out.append("professional_age")
    if role == "guardian" and not minor and not PROFESSIONAL_AGE[0] <= age <= PROFESSIONAL_AGE[1]:
        out.append("professional_age")
    if role in PARENT_ROLES or (role == "guardian" and minor):
        if age > MAX_LIVING_PARENT_AGE:
            out.append("parent_too_old")
        elif not MIN_PARENT_GAP <= age - subject_age <= MAX_PARENT_GAP:
            out.append("parent_gap")
    if role == "child" and not MIN_PARENT_GAP <= subject_age - age <= MAX_PARENT_GAP:
        out.append("child_gap")
    if role == "spouse" and (age < MIN_SPOUSE_AGE or abs(age - subject_age) > MAX_SPOUSE_GAP
                             or age > MAX_LIVING_PARENT_AGE):
        out.append("spouse_age")
    return out


def check(subject_age: Optional[int], members: Sequence[Member]) -> List[Tuple[str, str, int]]:
    """Test a finished cast against every rule.

    Args:
        subject_age: The data subject's age, or None for a record with no subject.
        members: The cast, the author included.

    Returns:
        `(rule, role, age)` for every violation; empty when the cast is coherent.
    """
    if subject_age is None:
        return []
    found = []
    for member in members:
        for rule in member_violations(subject_age, member):
            found.append((rule, member.role, member.age))
    return found


def _allowed_range(subject_age: int, role: str) -> Optional[Tuple[int, int]]:
    """Return the inclusive age range a member of this role may have, or None if none exists."""
    minor = subject_age < 18
    if role in PROFESSIONAL_ROLES or (role == "guardian" and not minor):
        return PROFESSIONAL_AGE
    if role in PARENT_ROLES or role == "guardian":
        lo, hi = subject_age + MIN_PARENT_GAP + 2, min(MAX_LIVING_PARENT_AGE, subject_age + 45)
        return (lo, hi) if lo <= hi else None
    if role == "child":
        lo, hi = max(1, subject_age - MAX_PARENT_GAP), subject_age - MIN_PARENT_GAP - 2
        return (lo, hi) if lo <= hi else None
    if role == "spouse":
        lo, hi = max(MIN_SPOUSE_AGE, subject_age - 8), min(MAX_LIVING_PARENT_AGE, subject_age + 8)
        return (lo, hi) if lo <= hi else None
    return None


def enforce_cast(
    subject_age: int, members: Sequence[Member], rng: random.Random,
) -> Tuple[List[Optional[Member]], CoherenceReport]:
    """Repair a drawn cast so that it satisfies every rule, and say what was done.

    Args:
        subject_age: The data subject's age.
        members: The cast as drawn.
        rng: Seeded RNG for the redraws.

    Returns:
        `(cast, report)`: one entry per input member, in order -- the member itself, the
        member with a new age or a new role, or None when it was dropped.
    """
    report = CoherenceReport(checked=len(members))
    out: List[Optional[Member]] = []
    for member in members:
        broken = member_violations(subject_age, member)
        if not broken:
            out.append(member)
            continue
        report.violations.extend(broken)
        role, age = member.role, member.age
        if "parent_too_old" in broken:
            # The relation survives as the other direction when the subject is old enough
            # to have an adult child; otherwise there is nobody to name.
            flipped_range = _allowed_range(subject_age, "child")
            if flipped_range and subject_age >= 40:
                new_age = rng.randint(*flipped_range)
                report.flipped += 1
                report.notes.append(f"parent {age} -> child {new_age} (subject {subject_age})")
                out.append(Member("child", new_age))
                continue
        allowed = _allowed_range(subject_age, role)
        if allowed is None:
            report.dropped += 1
            report.notes.append(f"{role} {age} dropped (no possible age for subject {subject_age})")
            out.append(None)
            continue
        new_age = rng.randint(*allowed)
        report.fixed += 1
        report.notes.append(f"{role} {age} -> {new_age} ({', '.join(broken)})")
        out.append(Member(role, new_age))
    return out, report


def summarise(reports: Sequence[dict], rejected: int = 0) -> Dict[str, object]:
    """Aggregate per-record reports (`CoherenceReport.as_dict()`) into the counts a run reports.

    Args:
        reports: One report per record that went on to generation.
        rejected: Records the final `check` refused and that were sampled again.

    Returns:
        Records checked, records that needed a repair, repairs by kind, the violations by
        rule, and the records rejected before generation.
    """
    by_rule: collections.Counter = collections.Counter()
    for report in reports:
        by_rule.update(report["violations"])
    return {
        "records_checked": len(reports) + rejected,
        "records_with_a_violation": sum(1 for r in reports if r["violations"]),
        "fixed_by_redrawing_an_age": sum(r["fixed"] for r in reports),
        "fixed_by_turning_a_parent_into_a_child": sum(r["flipped"] for r in reports),
        "fixed_by_dropping_the_member": sum(r["dropped"] for r in reports),
        "rejected_and_resampled": rejected,
        "violations_by_rule": dict(by_rule),
    }
