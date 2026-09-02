from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from app.evaluation.loader import load_results, load_suite
from app.evaluation.schemas import EvaluationInputError
from app.evaluation.scorer import evaluate, thresholds_pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic offline LLM evaluation.",
    )
    parser.add_argument("--suite", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--candidate", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        suite = load_suite(args.suite)
        results = load_results(args.results, suite)
        report = evaluate(
            suite,
            results,
            candidate=args.candidate,
        )
    except EvaluationInputError as exc:
        print(
            f"evaluation input error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if thresholds_pass(suite, report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
