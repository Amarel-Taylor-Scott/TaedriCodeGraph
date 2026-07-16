#!/usr/bin/env python3
"""Run one bounded Ollama call and print a usage receipt without printing secrets."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from taedri_codegraph.model_providers import (  # noqa: E402
    ChatMessage,
    OllamaChatProvider,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("TAEDRI_OLLAMA_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--model", default=os.environ.get("TAEDRI_OLLAMA_MODEL"), required=os.environ.get("TAEDRI_OLLAMA_MODEL") is None)
    parser.add_argument("--token-env", default="TAEDRI_OLLAMA_TOKEN")
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--receipt-only", action="store_true")
    parser.add_argument("--max-completion-tokens", type=int, default=128)
    args = parser.parse_args()
    prompt = (
        args.prompt_file.read_text("utf-8")
        if args.prompt_file is not None
        else "Return exactly the text TAEDRI_PROVIDER_SMOKE_OK and nothing else."
    )
    result = OllamaChatProvider(
        args.url,
        bearer_token=os.environ.get(args.token_env),
    ).chat(
        args.model,
        (ChatMessage("user", prompt),),
        seed=0,
        temperature="0",
        max_completion_tokens=args.max_completion_tokens,
    )
    output = {"receipt": result.receipt.to_dict()}
    if not args.receipt_only:
        output["content"] = result.content
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
