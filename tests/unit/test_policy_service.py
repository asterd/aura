from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aura.services.policy_service import PolicyService


@dataclass
class _PolicyCarrier:
    model_policy_id: object | None = None
    pii_policy_id: object | None = None
    sandbox_policy_id: object | None = None


def test_first_candidate_wins_for_policy_precedence():
    service = PolicyService()
    preferred_policy_id = uuid4()
    fallback_policy_id = uuid4()

    resolved = service._resolve_candidate_policy_id(  # noqa: SLF001
        [
            _PolicyCarrier(model_policy_id=preferred_policy_id),
            _PolicyCarrier(model_policy_id=fallback_policy_id),
        ],
        "model_policy_id",
    )

    assert resolved == preferred_policy_id


def test_conflicting_space_policy_bindings_are_rejected():
    service = PolicyService()

    with pytest.raises(HTTPException) as exc_info:
        service._resolve_candidate_policy_id(  # noqa: SLF001
            [
                _PolicyCarrier(),
                _PolicyCarrier(pii_policy_id=uuid4()),
                _PolicyCarrier(pii_policy_id=uuid4()),
            ],
            "pii_policy_id",
        )

    assert exc_info.value.status_code == 422
    assert "Conflicting policy bindings" in str(exc_info.value.detail)
