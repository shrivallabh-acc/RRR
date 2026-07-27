# Providers

LLM providers write dimension narratives, risk rationale, and remediation plans.
They **never** influence the numeric score or verdict label — those are always
deterministic code (ADR-0006).

---

## The guardrail chain (ADR-0009)

Every LLM call passes through this chain in order:

```
LLMProvider.reason(request)
  → parse_with_repair(raw, schema)         # validate against Pydantic schema
    → on failure: send repair hint, retry once
      → on second failure: RuleBasedProvider.reason(request)  # deterministic fallback
        → DimensionResult.confidence_cap applied
```

No provider can bypass this chain. Raw LLM output never crosses a module boundary
without Pydantic validation.

---

## Provider inventory

| File | Class | `type` config value | Package | When to use |
|---|---|---|---|---|
| `rule_based.py` | `RuleBasedProvider` | `rule_based` | _(none)_ | Default. CI, air-gapped, no model needed. |
| `local_llm.py` | `LocalLLMProvider` | `local_llm` | `rrr[local-llm]` | On-machine Ollama model. |
| `mock_llm.py` | `MockLLMProvider` | `mock_llm` | _(none)_ | Fixture-backed offline demo and testing. |
| `bedrock.py` | `BedrockProvider` | `bedrock` | `rrr[bedrock]` | AWS Bedrock Converse API. |
| `claude.py` | `ClaudeProvider` | `claude` | `rrr[cloud]` | Anthropic Messages API. |

---

## Configuration

```yaml
provider:
  type: rule_based   # change to local_llm | mock_llm | bedrock | claude

  # LocalLLM (Ollama):
  local_llm:
    endpoint: "http://127.0.0.1:11434"
    model: "llama3.1"

  # MockLLM (tests / demo):
  mock_llm:
    fixture_dir: "tests/fixtures/llm_responses"

  # Bedrock:
  bedrock:
    model_id: "anthropic.claude-3-5-sonnet-20241022-v2:0"
    region: "us-east-1"
    max_tokens: 1024
    temperature: 0.1

  # Claude (Anthropic):
  claude:
    model: "claude-sonnet-4-6"
    max_tokens: 1024
    temperature: 0.1
```

**API keys:** always via environment variables, never in config files.

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."     # ClaudeProvider
$env:AWS_ACCESS_KEY_ID = "..."            # BedrockProvider
$env:AWS_SECRET_ACCESS_KEY = "..."        # BedrockProvider
```

---

## Local-only constraint (ADR-0010, Phase 1)

Phase 1 providers connect only to `127.0.0.1` or `localhost`. The `LocalLLMProvider`
validates the Ollama endpoint against the `allowed_hosts` config list at startup.

`BedrockProvider` and `ClaudeProvider` make outbound API calls — they are Phase 2
opt-in features and must not be wired into Phase 1 pipeline paths.

---

## Injection safety (ADR-0009)

`ReasoningRequest` has two distinct field types:

| Field | Content type | Rules |
|---|---|---|
| `facts` | Data strings from tool results | Safe to include tool output here |
| `summary` / instruction fields | LLM prompt instructions | Never interpolate raw user input or tool output here |

`allowed_classifications` must always be set to bound the label space.

---

## Adding a new provider

1. Create `<name>.py` extending `LLMProvider` (ABC in `base.py`).
2. Implement `reason(request: ReasoningRequest) -> str`.
3. Register in `__init__.py` and `pipeline.py`.
4. Add unit tests in `tests/unit/test_<name>_provider.py` covering normal path, repair
   path (malformed first response), and fallback path (repair exhausted).
5. If the provider makes outbound network calls, ensure the host is in `allowed_hosts`.
