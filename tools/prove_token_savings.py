#!/usr/bin/env python3
"""Validate JSON/JSONL matched-pair evidence and emit token-savings proofs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from taedri_codegraph.token_savings import (  # noqa: E402
    TokenSavingsError,
    evaluate_token_savings_file,
    measure_prompt_interception_campaign_file,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build fail-closed token-savings proofs from JSON or JSONL evidence."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        help="write the exact JSON proof or measurement to this file",
    )
    parser.add_argument(
        "--prompt-interception-campaign",
        "--campaign",
        action="store_true",
        help=(
            "validate serialized campaign receipts and emit an operator-captured "
            "provider-response, "
            "non-claimable measurement"
        ),
    )
    args = parser.parse_args(argv)
    try:
        if args.prompt_interception_campaign:
            value: object = measure_prompt_interception_campaign_file(
                args.input
            ).to_dict()
        else:
            proofs = evaluate_token_savings_file(args.input)
            value = (
                proofs[0].to_dict()
                if len(proofs) == 1
                else [item.to_dict() for item in proofs]
            )
    except TokenSavingsError as exc:
        parser.exit(2, f"token-savings proof rejected: {exc}\n")
    encoded = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if args.compact
        else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    ) + "\n"
    if args.output is None:
        sys.stdout.write(encoded)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
