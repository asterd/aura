from __future__ import annotations

import importlib.util
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aura.domain.contracts import DetectedEntity, PiiMode, PiiPolicy, PiiTransformResult, RequestContext
from aura.services.policy_service import PolicyService
from aura.utils.observability import record_pii_transform_error

try:
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
except ImportError:  # pragma: no cover - exercised only when optional deps are missing
    AnalyzerEngine = None
    Pattern = None
    PatternRecognizer = None
    RecognizerRegistry = None


logger = logging.getLogger("aura")

_ITALIAN_CF_RE = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?:(?<=\s)|^)(?:\+?\d[\d\s-]{7,}\d)(?=\s|$)")
_PREVIEW_KEEP = 2


@dataclass(slots=True)
class _Detection:
    entity_type: str
    start: int
    end: int
    score: float


class PiiService:
    def __init__(self, policy_service: PolicyService | None = None) -> None:
        self._policy_service = policy_service or PolicyService()
        self._analyzer = self._build_presidio_analyzer()

    async def _resolve_and_transform(self, *, session: AsyncSession, context: RequestContext, text: str, policy_entity: Any, sink: str) -> PiiTransformResult:
        policy = await self._policy_service.resolve_pii_policy(session, policy_entity, context)
        return self._transform_text(text=text, policy=policy, sink=sink)

    async def transform_input_if_needed(self, *, session: AsyncSession, context: RequestContext, text: str, policy_entity: Any = None) -> PiiTransformResult:
        return await self._resolve_and_transform(session=session, context=context, text=text, policy_entity=policy_entity, sink="input")

    async def transform_output_if_needed(self, *, session: AsyncSession, context: RequestContext, text: str, policy_entity: Any = None) -> PiiTransformResult:
        return await self._resolve_and_transform(session=session, context=context, text=text, policy_entity=policy_entity, sink="output")

    async def transform_persisted_text_if_needed(self, *, session: AsyncSession, context: RequestContext, text: str, policy_entity: Any = None) -> PiiTransformResult:
        return await self._resolve_and_transform(session=session, context=context, text=text, policy_entity=policy_entity, sink="persistence")

    async def transform_log_text_if_needed(self, *, session: AsyncSession, context: RequestContext, text: str, policy_entity: Any = None) -> PiiTransformResult:
        return await self._resolve_and_transform(session=session, context=context, text=text, policy_entity=policy_entity, sink="logs")

    async def transform_trace_text_if_needed(self, *, session: AsyncSession, context: RequestContext, text: str, policy_entity: Any = None) -> PiiTransformResult:
        return await self._resolve_and_transform(session=session, context=context, text=text, policy_entity=policy_entity, sink="traces")

    async def transform_agent_input_if_needed(self, *, session: AsyncSession, context: RequestContext, input_obj: dict[str, Any], policy: PiiPolicy | None) -> dict[str, Any]:
        return self._transform_object(input_obj, policy=policy, sink="input")

    async def transform_agent_output_if_needed(self, *, session: AsyncSession, context: RequestContext, output_obj: dict[str, Any], policy: PiiPolicy | None) -> dict[str, Any]:
        return self._transform_object(output_obj, policy=policy, sink="output")

    def _transform_object(self, value: Any, *, policy: PiiPolicy | None, sink: str) -> Any:
        if isinstance(value, dict):
            return {key: self._transform_object(item, policy=policy, sink=sink) for key, item in value.items()}
        if isinstance(value, list):
            return [self._transform_object(item, policy=policy, sink=sink) for item in value]
        if isinstance(value, str):
            return self._transform_text(text=value, policy=policy, sink=sink).transformed_text
        return value

    def _transform_text(self, *, text: str, policy: PiiPolicy | None, sink: str) -> PiiTransformResult:
        effective_policy = policy
        if effective_policy is None:
            return self._raw_result(text=text, mode=PiiMode.off)

        if effective_policy.mode == PiiMode.pseudonymize_rehydratable:
            raise NotImplementedError("pseudonymize_rehydratable mode is not implemented")

        detections = self._detect_entities_batch([text], effective_policy)[0]
        if not self._should_transform(policy=effective_policy, sink=sink):
            return self._result_from(text=text, transformed_text=text, policy=effective_policy, detections=detections)

        transformed_text = self._mask_text(text, detections)
        return self._result_from(
            text=text,
            transformed_text=transformed_text,
            policy=effective_policy,
            detections=detections,
        )

    def _should_transform(self, *, policy: PiiPolicy, sink: str) -> bool:
        if sink == "input":
            return policy.mode in {PiiMode.mask_inference_only, PiiMode.mask_persist_and_inference}
        if sink == "output":
            return policy.mode == PiiMode.mask_persist_and_inference
        if sink == "persistence":
            return policy.mode == PiiMode.mask_persist_and_inference
        if sink == "logs":
            return not policy.allow_raw_in_logs
        if sink == "traces":
            return not policy.allow_raw_in_traces
        return False

    def _raw_result(self, *, text: str, mode: PiiMode) -> PiiTransformResult:
        return PiiTransformResult(
            mode=mode.value,
            transformed_text=text,
            detected_entities=[],
            mapping_refs=[],
            had_transformations=False,
        )

    def _result_from(
        self,
        *,
        text: str,
        transformed_text: str,
        policy: PiiPolicy,
        detections: list[_Detection],
    ) -> PiiTransformResult:
        return PiiTransformResult(
            mode=policy.mode.value,
            transformed_text=transformed_text,
            detected_entities=[
                DetectedEntity(
                    entity_type=d.entity_type,
                    start=d.start,
                    end=d.end,
                    score=d.score,
                    value_preview=self._preview_value(text[d.start:d.end]),
                )
                for d in detections
            ],
            mapping_refs=[],
            had_transformations=transformed_text != text,
        )

    def _detect_entities_batch(self, texts: list[str], policy: PiiPolicy) -> list[list[_Detection]]:
        if not texts:
            return []
        if self._analyzer is not None:
            try:
                return [self._detect_with_presidio(text, policy) for text in texts]
            except Exception:
                record_pii_transform_error(mode=policy.mode.value, tenant_id=self._policy_tenant_id(policy))
                logger.warning("presidio_detection_failed_falling_back_to_regex")
        return [self._detect_with_regex(text, policy) for text in texts]

    def _policy_tenant_id(self, policy: PiiPolicy) -> str:
        tenant_id = getattr(policy, "tenant_id", None)
        return str(tenant_id) if tenant_id is not None else "unknown"

    def _detect_with_presidio(self, text: str, policy: PiiPolicy) -> list[_Detection]:
        if self._analyzer is None:
            return self._detect_with_regex(text, policy)

        entities = policy.entities_to_detect or None
        results = self._analyzer.analyze(
            text=text,
            entities=entities,
            language="en",
            score_threshold=policy.score_threshold,
        )
        return self._dedupe_detections(
            [
                _Detection(
                    entity_type=result.entity_type,
                    start=result.start,
                    end=result.end,
                    score=float(result.score),
                )
                for result in results
            ]
        )

    def _detect_with_regex(self, text: str, policy: PiiPolicy) -> list[_Detection]:
        enabled = set(policy.entities_to_detect)
        all_detections: list[_Detection] = []
        for entity_type, pattern in (
            ("IT_FISCAL_CODE", _ITALIAN_CF_RE),
            ("EMAIL_ADDRESS", _EMAIL_RE),
            ("PHONE_NUMBER", _PHONE_RE),
        ):
            if enabled and entity_type not in enabled:
                continue
            for match in pattern.finditer(text):
                score = 0.99
                if score < policy.score_threshold:
                    continue
                all_detections.append(
                    _Detection(
                        entity_type=entity_type,
                        start=match.start(),
                        end=match.end(),
                        score=score,
                    )
                )
        return self._dedupe_detections(all_detections)

    def _build_presidio_analyzer(self):
        if AnalyzerEngine is None or Pattern is None or PatternRecognizer is None or RecognizerRegistry is None:
            return None
        if importlib.util.find_spec("en_core_web_lg") is None:
            logger.warning("presidio_spacy_model_missing_falling_back_to_regex")
            return None

        try:
            registry = RecognizerRegistry()
            registry.load_predefined_recognizers()
            registry.add_recognizer(
                PatternRecognizer(
                    supported_entity="IT_FISCAL_CODE",
                    patterns=[Pattern(name="italian_fiscal_code", regex=_ITALIAN_CF_RE.pattern, score=0.99)],
                )
            )
            return AnalyzerEngine(registry=registry, supported_languages=["en"])
        except Exception:
            logger.warning("presidio_unavailable_falling_back_to_regex")
            return None

    def _mask_text(self, text: str, detections: list[_Detection]) -> str:
        if not detections:
            return text

        masked: list[str] = []
        cursor = 0
        for detection in sorted(detections, key=lambda item: (item.start, item.end)):
            if detection.start < cursor:
                continue
            masked.append(text[cursor:detection.start])
            masked.append(f"[{detection.entity_type}]")
            cursor = detection.end
        masked.append(text[cursor:])
        return "".join(masked)

    def _dedupe_detections(self, detections: list[_Detection]) -> list[_Detection]:
        deduped: list[_Detection] = []
        for detection in sorted(detections, key=lambda item: (item.start, item.end, item.entity_type)):
            if deduped and detection.start < deduped[-1].end and detection.end <= deduped[-1].end:
                continue
            deduped.append(detection)
        return deduped

    def _preview_value(self, value: str) -> str:
        if len(value) <= _PREVIEW_KEEP * 2:
            return "*" * len(value)
        return f"{value[:_PREVIEW_KEEP]}***{value[-_PREVIEW_KEEP:]}"
