"""Any edit to a reviewed clause sends it back to draft for re-approval (AGENTS.md gate 1)."""

from typing import Any

from cascadeguard.domain.policies import ClauseStatus, PolicyClause
from cascadeguard.knowledge.loader import clause_digest, load_approvals, load_clauses

CLAUSE: dict[str, Any] = {
    "id": "test.clause",
    "title": "A clause",
    "text": "Some verbatim text.",
    "source_file": "doc.pdf",
    "page": 3,
    "issuer": "Issuer",
    "jurisdiction": "UAE",
    "document_date": "2021",
    "status": "reviewed",
    "binding": True,
    "notes": "n",
}


def test_every_reviewed_clause_matches_its_approved_digest() -> None:
    approved, _ = load_approvals()
    for clause in load_clauses():
        if clause.status is ClauseStatus.REVIEWED:
            assert clause.id in approved, f"{clause.id}: reviewed without a human approval"
            assert clause_digest(clause) == approved[clause.id], (
                f"{clause.id} was edited after approval: set it back to draft and list it "
                "under reapproval_needed in policies/approvals.yaml"
            )


def test_a_demoted_clause_is_draft_and_listed_for_reapproval() -> None:
    approved, pending = load_approvals()
    status = {c.id: c.status for c in load_clauses()}
    for cid in approved:
        assert cid in status, f"{cid}: approved but no longer exists"
        if status[cid] is not ClauseStatus.REVIEWED:
            assert status[cid] is ClauseStatus.DRAFT, cid
            assert cid in pending, f"{cid}: no longer reviewed but not listed for re-approval"
    for cid in pending:
        assert cid in approved and status.get(cid) is ClauseStatus.DRAFT, cid


def test_any_field_edit_changes_the_digest_but_status_does_not() -> None:
    base = clause_digest(PolicyClause.model_validate(CLAUSE))
    assert clause_digest(PolicyClause.model_validate(CLAUSE | {"status": "draft"})) == base
    for field, value in [("text", "Other text."), ("notes", "m"), ("page", 4), ("binding", False)]:
        edited = PolicyClause.model_validate(CLAUSE | {field: value})
        assert clause_digest(edited) != base, field
