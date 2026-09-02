# Offline LLM Evaluation

This directory contains deterministic repository-owned evaluation fixtures for the AI decision surfaces in the Reliable AI Support Operations Platform.

## V1 scope

The v1 suite evaluates normalized outputs for:

- Grounded RAG
- Tool choice

It does **not** call OpenAI, execute Tools, access PostgreSQL, approve actions, or use an LLM-as-Judge.

## Important baseline interpretation

`baseline_results.jsonl` is a deterministic scorer fixture, **not a measured live-model score**.

A 100% baseline fixture proves that:

- the committed cases are valid;
- the scorer behaves deterministically;
- the known-good result format passes the configured gate.

It does not prove that any live model achieves 100%.

## Run

```powershell
python -m app.evaluation.runner --suite evals/suites/v1/suite.json --results evals/suites/v1/baseline_results.jsonl --candidate baseline-v1
```

Exit codes:

- `0`: valid evaluation and thresholds pass
- `1`: valid evaluation but thresholds fail
- `2`: malformed/invalid evaluation input or CLI usage

## Metric limits

V1 checks deterministic contract/safety properties such as answerability, citation integrity, required evidence coverage, Tool decision, exact Tool name/arguments, and unauthorized Tool selection.

Required answer fragments are coarse factual smoke checks. They are not full semantic equivalence.

V1 intentionally does not use BLEU/ROUGE as a factuality score.

## Prompt identity

The suite pins stable Prompt IDs and SHA-256 fingerprints for the grounded-answer and Tool-choice instruction text.

If those Product prompts change, the suite fingerprint must be intentionally reviewed and updated. Silent Prompt drift fails the loader.

## Data policy

All committed v1 cases are synthetic.

Do not add production documents, real access tokens, secrets, or private user/support data.


## security-v1 suite

The `security-v1` suite reuses the exact same #017 evaluation loader, schemas, prompt fingerprints, scorer, report, and threshold semantics.

It adds synthetic adversarial cases for:

- prompt injection in retrieved evidence;
- citation forgery;
- insufficient-evidence pressure;
- hallucinated shell / SQL / URL-fetch Tools;
- admin / role argument injection;
- invented Tool schemas;
- Human Approval bypass attempts;
- hidden unauthorized Tool selection.

Run it with:

```powershell
python -m app.evaluation.runner --suite evals/suites/security-v1/suite.json --results evals/suites/security-v1/baseline_results.jsonl --candidate security-baseline-v1
```

The committed security baseline is still only a **deterministic scorer fixture**. A 100% fixture score does not prove that any live model resisted these attacks.

The security suite never executes the attack strings as shell commands, SQL, URLs, Python, or Tool actions. They remain untrusted test data.
