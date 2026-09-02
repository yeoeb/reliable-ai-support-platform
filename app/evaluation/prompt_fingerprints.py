from __future__ import annotations

from app.evaluation.schemas import (
    EvaluationInputError,
    PromptFingerprint,
    PromptFingerprintSet,
)
from app.integrations.llm import (
    OpenAIGroundedAnswerProvider,
    OpenAIToolCallingProvider,
)


def current_prompt_fingerprints() -> PromptFingerprintSet:
    return PromptFingerprintSet(
        rag_grounded=PromptFingerprint(
            prompt_id=OpenAIGroundedAnswerProvider.prompt_id,
            sha256=(
                OpenAIGroundedAnswerProvider
                .prompt_fingerprint()
            ),
        ),
        tool_choice=PromptFingerprint(
            prompt_id=OpenAIToolCallingProvider.choice_prompt_id,
            sha256=(
                OpenAIToolCallingProvider
                .choice_prompt_fingerprint()
            ),
        ),
    )


def verify_prompt_fingerprints(
    expected: PromptFingerprintSet,
) -> None:
    current = current_prompt_fingerprints()
    if expected != current:
        raise EvaluationInputError(
            "Evaluation prompt fingerprint mismatch"
        )
