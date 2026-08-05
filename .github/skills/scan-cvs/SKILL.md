---
name: scan-cvs
description: Run Kriterion CV screening with the non-interactive foreground launcher and open the evidence-backed dashboard. Use for requests to scan or screen CVs, run Kriterion, analyze candidates or resumes, or open the screening dashboard.
---

## Goal

Run one Kriterion screening command and keep its local dashboard server attached to the foreground terminal.

## Inputs

Use these defaults without asking:

- `--cvs-dir`: `./cvs`
- `--profile`: `./profiles/profile.yaml`
- `--output-dir`: `.`

Use a path flag only when the user supplies a non-default path. Accept relative or absolute paths. Forward other launcher options only when requested.

## Run

Run from the repository root. For all defaults:

```bash
./kriterion.sh
```

For custom paths:

```bash
./kriterion.sh --cvs-dir "{cv_dir}" --profile "{profile_path}" --output-dir "{output_dir}"
```

Do not activate `.venv`, install requirements, call `kriterion.py` directly, or use positional arguments. `setup.sh` is a separate installation action, not part of screening.

The launcher uses `exec`, opens the dashboard by default, and remains active as the foreground webserver. Keep the process running. Ctrl+C is the normal shutdown mechanism.

## Report

After Kriterion prints its dashboard URL:

- Report the URL and the generated role/date output directory.
- Report PASS, FAIL, and AMBIGUOUS counts from command output.
- Explain that only ambiguous candidates receive automatic AI recommendations.
- Explain that AI evidence is restricted to parsed work experience and the unresolved criteria.
- Remind the user that the human reviewer makes the final PASS/FAIL decision.

Do not inspect or invent candidate results when the command output already provides them.

## Errors

- Missing `.venv` or dependencies: tell the user to run `./setup.sh`; do not install automatically.
- Missing profile: offer to create `./profiles/profile.yaml` with the create-profile skill.
- Missing or empty CV directory: report the exact path and ask the user to correct it.
- Copilot unavailable: report the Kriterion error; deterministic screening and static report files remain valid.

## Examples

- “Run screening” → `./kriterion.sh`
- “Scan `~/candidates/batch2`” → `./kriterion.sh --cvs-dir "$HOME/candidates/batch2"`
- “Use `profiles/backend.yaml`” → `./kriterion.sh --profile ./profiles/backend.yaml`
- “Generate under `./reports` without opening a browser” → `./kriterion.sh --output-dir ./reports --no-open`
