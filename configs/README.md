# configs/

Reference configuration files for different deployment contexts. Each file is a **partial**
override — it is deep-merged over the bundled `default_config.yaml`, so only the keys
that differ from defaults need to be present.

---

## Files

| File | Provider | Value stream | Purpose |
|---|---|---|---|
| `demo.yaml` | MockLLMProvider | demo | Fully offline demo — no real data or model required |
| `osm.yaml` | RuleBasedProvider | OSM / Retirement-Services | Production baseline for OSM programme |
| `claude.yaml` | ClaudeProvider | — | Override to use Anthropic Claude (`claude-sonnet-4-6`) |
| `bedrock.yaml` | BedrockProvider | — | Override to use AWS Bedrock Converse API |

---

## `demo.yaml`

Uses `MockLLMProvider` with the bundled fixture responses. Run without any real brain
data or API keys:

```powershell
rrr --release "Launch 36 - Unified Onboarding" --config configs/demo.yaml
```

---

## `osm.yaml`

Production settings for the OSM / Retirement-Services value stream. Sets brain dir,
value stream name, and the sources for all configured dimensions. Use this as the
starting point for a real programme deployment.

---

## `claude.yaml`

Switch to the Anthropic Claude provider for richer LLM rationale:

```powershell
pip install -e ".[cloud]"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
rrr --release "RetirePlus RC" --config configs/claude.yaml
```

---

## `bedrock.yaml`

Use Amazon Bedrock (requires AWS credentials in environment):

```powershell
pip install -e ".[bedrock]"
$env:AWS_ACCESS_KEY_ID     = "..."
$env:AWS_SECRET_ACCESS_KEY = "..."
rrr --release "RetirePlus RC" --config configs/bedrock.yaml
```

---

## Creating your own config

Start from the closest reference config and override only what you need:

```yaml
# my_programme.yaml
sources:
  brain:
    dir: "./brain"
    value_stream: "My-Programme"
  environment: { type: file, path: "./data/environment.json" }
  dependency:  { type: file, path: "./data/dependency.json" }
  operability: { type: file, path: "./data/operability.json" }
  security:    { type: file, path: "./data/security.json" }

thresholds:
  go: 0.85   # stricter than default 0.80
```

Then: `rrr --release "..." --config my_programme.yaml`
