# ADR-0019: Amazon Bedrock as a Phase 2 LLM Provider

Status: Accepted (implemented 2026-06-22)

## Context

Phase 1 providers (`RuleBasedProvider`, `LocalLLMProvider`) produce either template-based
or on-machine (Ollama) narrative. With Kiro IDE access the project now has AWS credentials
available in the environment. Amazon Bedrock's **Converse API** exposes Claude 3.x, Titan,
Mistral, and other hosted models under those same credentials — no new API key setup required.

The investigation showed that `kiro chat` opens the GUI IDE (VS Code fork) and produces no
stdout; it cannot be used as a headless subprocess. The underlying model access is Amazon
Q Developer / Bedrock via AWS SSO. Calling Bedrock directly via boto3 is the correct
Python integration path.

## Decision

Add `BedrockProvider` as an optional, **Phase 2** provider that:

- Calls the **Bedrock Converse API** (`bedrock-runtime.converse`) via boto3.
- Is model-agnostic — the `modelId` is a config string, no code change to switch models.
- Follows the identical guardrail chain as every other provider (ADR-0009):
  `converse()` → `parse_with_repair` (1 repair retry) → `ProviderValidationError`
  → `RuleBasedProvider` fallback in `BaseAssessor.reason`.
- Is installed as an optional dependency group: `pip install rrr[bedrock]` (adds boto3).
- boto3 is imported lazily inside `__init__` so the package remains importable without it.

**Default model:** `anthropic.claude-3-5-sonnet-20241022-v2:0` (overridable in config).

## Consequences

**Enables:**
- Frontier-model narrative quality without a local GPU or Ollama install.
- Model flexibility: swap `modelId` in YAML to change models with no code change.
- Uses the existing AWS credential chain (IAM role, `aws configure`, SSO token, env vars).

**Forecloses / trade-offs:**
- Breaks ADR-0010 local-first constraint — Bedrock makes external network calls to
  `bedrock-runtime.<region>.amazonaws.com`. This is intentional and identical to
  `ClaudeProvider`'s status (Phase 2 external scale-out only).
- Requires AWS credentials in the runtime environment; misconfigured credentials degrade
  gracefully to `RuleBasedProvider` via the existing fallback path.
- boto3 is not pinned strictly — the optional group uses a lower-bound (`>=1.35`).

## Implementation note

2026-06-22 — `BedrockProvider` implemented in `src/rrr/providers/bedrock.py`.
`ProviderType.BEDROCK` added to `config/schema.py`. Wired into `pipeline.build_provider()`.
12 unit tests added in `tests/unit/test_bedrock_provider.py`.
