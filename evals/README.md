# Offline LLM Evaluation

This directory contains deterministic repository-owned evaluation fixtures for the AI decision surfaces in the Reliable AI Support Operations Platform.

## Evaluation scope

The evaluation suites assess normalized outputs for:

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

## Suites

- `v1`: 12 original coverage cases (6 RAG, 6 Tool)
- `security-v1`: 16 original adversarial cases (8 RAG, 8 Tool)
- `v2`: 80 expanded coverage cases (40 RAG, 40 Tool)
- `security-v2`: 40 expanded adversarial cases (20 RAG, 20 Tool)

The V2 manifests declare bounded `tag_minimums`. Loading fails closed
when a required family tag is absent or under its minimum. Older
manifests without `tag_minimums` remain valid.

Normal V2 covers ten cases in each of these families:

- single-source, multi-source, insufficient-evidence, and selective-evidence RAG;
- direct answer, platform readiness, support-agent grant, and no-tools-available Tool choice.

Security V2 covers prompt injection, citation forgery,
insufficient-evidence/data-leakage pressure, source-authority confusion,
unauthorized Tool proposals, argument injection, Approval bypass,
invented schemas, and hidden Tool selection. Attack strings remain inert
fixture data.

## Run

```powershell
python -m app.evaluation.runner --suite evals/suites/v1/suite.json --results evals/suites/v1/baseline_results.jsonl --candidate baseline-v1
```

Use the same command with `v2` or `security-v2` paths for the expanded
suites. For example:

```powershell
python -m app.evaluation.runner --suite evals/suites/v2/suite.json --results evals/suites/v2/baseline_results.jsonl --candidate baseline-v2
```

## Compare two candidates

A versioned comparison manifest binds one Suite to exactly two normalized
Candidate result files. It records each Candidate's declared Prompt IDs and
SHA-256 fingerprints as provenance, reports challenger-minus-baseline metric
deltas, and lists improved and regressed Case IDs deterministically.

Run the committed neutral V2 reference comparison with:

```powershell
python -m app.evaluation.comparison_runner --root evals --comparison comparisons/v2-reference.json
```

The reference compares the existing V2 scorer fixture with itself under two
distinct Candidate labels. Its zero-delta passing report proves comparison
behavior only; it is not measured Model or Prompt quality.

All manifest, Suite, and result paths must be relative to the explicit
Evaluation root and remain inside it. The bounded policy can require the
challenger's Suite thresholds and limit Case pass-rate drop, Safety violation
increase, and newly failed Cases. A newly failing Safety Case is always a gate
failure, even when another Safety Case improves and aggregate counts do not
change.

Comparison exit codes:

- `0`: valid comparison and gate pass
- `1`: valid comparison and gate fail
- `2`: malformed comparison input or CLI usage

## Reproduce V2 fixtures

The V2 suite manifests, cases, and scorer baselines are rendered by a
stdlib-only deterministic generator. Writing is explicit; importing the
module does not write files.

```powershell
python scripts/generate_eval_suite_v2.py --write
python scripts/generate_eval_suite_v2.py --check
```

The check command requires every committed V2 fixture to match generated
bytes exactly. The generator uses fixed ordering and fixed-index synthetic
UUID formatting; it does not use randomness, time, network access,
subprocesses, environment secrets, or production data.

Exit codes:

- `0`: valid evaluation and thresholds pass
- `1`: valid evaluation but thresholds fail
- `2`: malformed/invalid evaluation input or CLI usage

## Metric limits

The suites check deterministic contract/safety properties such as answerability, citation integrity, required evidence coverage, Tool decision, exact Tool name/arguments, and unauthorized Tool selection.

Required answer fragments are coarse factual smoke checks. They are not full semantic equivalence.

They intentionally do not use BLEU/ROUGE as a factuality score.

## Prompt identity

The suite pins stable Prompt IDs and SHA-256 fingerprints for the grounded-answer and Tool-choice instruction text.

If those Product prompts change, the suite fingerprint must be intentionally reviewed and updated. Silent Prompt drift fails the loader.

## Data policy

All committed cases are synthetic.

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
