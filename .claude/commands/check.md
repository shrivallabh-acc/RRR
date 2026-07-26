---
description: Run the local quality gate (lint, type-check, tests) and report results
---

Run the project's local quality gate and report what passed and what failed. Do not fix anything
yet unless asked — first report honestly.

```
ruff check src tests
ruff format --check src tests
mypy src
pytest
```

Report: which steps passed, which failed, and the relevant failure output. Distinguish
"not yet implemented / nothing to run" from "ran and failed". Everything must run offline
(local-first) — flag any step that tries to reach the network.
