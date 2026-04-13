from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from aura.domain.contracts import PiiMode, PiiPolicy, RequestContext, UserIdentity
from aura.services.pii_service import PiiService


pytestmark = pytest.mark.asyncio


class _StubPolicyService:
    def __init__(self, policy: PiiPolicy | None) -> None:
        self._policy = policy

    async def resolve_pii_policy(self, session, entity, context):  # noqa: ANN001
        return self._policy


def _build_context() -> RequestContext:
    tenant_id = uuid4()
    return RequestContext(
        request_id="req-test",
        trace_id="trace-test",
        tenant_id=tenant_id,
        identity=UserIdentity(
            user_id=uuid4(),
            tenant_id=tenant_id,
            okta_sub="okta|test",
            email="test@example.com",
        ),
        now_utc=datetime.now(UTC),
    )


def _build_policy(mode: PiiMode) -> PiiPolicy:
    tenant_id = uuid4()
    now = datetime.now(UTC)
    return PiiPolicy(
        id=uuid4(),
        tenant_id=tenant_id,
        name="default",
        mode=mode,
        entities_to_detect=[],
        score_threshold=0.7,
        persist_mapping=False,
        mapping_ttl_days=None,
        allow_raw_in_logs=False,
        allow_raw_in_traces=False,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


async def test_pii_transform_off_returns_raw():
    service = PiiService(policy_service=_StubPolicyService(_build_policy(PiiMode.off)))

    result = await service.transform_input_if_needed(
        session=None,  # type: ignore[arg-type]
        context=_build_context(),
        text="Il mio CF è RSSMRA85M01H501Z",
    )

    assert result.transformed_text == "Il mio CF è RSSMRA85M01H501Z"
    assert not result.had_transformations


async def test_pii_mask_inference_only():
    service = PiiService(policy_service=_StubPolicyService(_build_policy(PiiMode.mask_inference_only)))

    input_result = await service.transform_input_if_needed(
        session=None,  # type: ignore[arg-type]
        context=_build_context(),
        text="CF: RSSMRA85M01H501Z",
    )
    output_result = await service.transform_output_if_needed(
        session=None,  # type: ignore[arg-type]
        context=_build_context(),
        text="CF: RSSMRA85M01H501Z",
    )

    assert "RSSMRA85M01H501Z" not in input_result.transformed_text
    assert input_result.had_transformations
    assert output_result.transformed_text == "CF: RSSMRA85M01H501Z"


async def test_pii_mask_persist_and_inference_masks_output_and_persistence():
    service = PiiService(policy_service=_StubPolicyService(_build_policy(PiiMode.mask_persist_and_inference)))

    output_result = await service.transform_output_if_needed(
        session=None,  # type: ignore[arg-type]
        context=_build_context(),
        text="CF: RSSMRA85M01H501Z",
    )
    persisted_result = await service.transform_persisted_text_if_needed(
        session=None,  # type: ignore[arg-type]
        context=_build_context(),
        text="CF: RSSMRA85M01H501Z",
    )

    assert output_result.transformed_text == "CF: [IT_FISCAL_CODE]"
    assert persisted_result.transformed_text == "CF: [IT_FISCAL_CODE]"


async def test_logs_are_masked_when_raw_logging_is_disallowed_even_if_mode_is_off():
    policy = _build_policy(PiiMode.off).model_copy(update={"allow_raw_in_logs": False})
    service = PiiService(policy_service=_StubPolicyService(policy))

    log_result = await service.transform_log_text_if_needed(
        session=None,  # type: ignore[arg-type]
        context=_build_context(),
        text="CF: RSSMRA85M01H501Z",
    )

    assert log_result.transformed_text == "CF: [IT_FISCAL_CODE]"
    assert log_result.had_transformations
