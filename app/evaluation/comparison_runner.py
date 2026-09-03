from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from app.evaluation.comparison import compare_candidates
from app.evaluation.comparison_loader import load_comparison
from app.evaluation.schemas import EvaluationInputError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two normalized evaluation candidates.",
    )
    parser.add_argument("--root", required=True)
    parser.add_argument("--comparison", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        loaded = load_comparison(args.root, args.comparison)
        report = compare_candidates(
            loaded.manifest,
            loaded.suite,
            loaded.baseline_results,
            loaded.challenger_results,
        )
    except EvaluationInputError as exc:
        print(
            f"evaluation comparison input error: {exc}",
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
    return 0 if report.gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
