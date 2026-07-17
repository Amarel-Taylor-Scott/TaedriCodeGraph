#!/usr/bin/env python3
"""Run the opt-in matched primitive-interception campaign.

Credentials are accepted only through a named environment variable or one line on
standard input.  They are passed directly to the selected provider and are never
placed in campaign output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from taedri_codegraph.model_providers import (  # noqa: E402
    MistralChatProvider,
    OllamaChatProvider,
    OpenAICompatibleChatProvider,
    OpenRouterChatProvider,
)
from taedri_codegraph.prompt_interception import (  # noqa: E402
    CampaignExecutionPolicy,
    ReleasedPrimitiveCatalog,
    load_natural_primitive_tasks,
    run_prompt_interception_campaign,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare showing the model every released primitive description with "
            "showing it only descriptions selected locally, using the same checked "
            "tasks, model, seeds, and pack verifier."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        choices=("ollama", "openrouter", "mistral", "openai-compatible"),
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--seed", type=int, action="append", dest="seeds")
    parser.add_argument("--max-completion-tokens", type=int, default=128)
    parser.add_argument(
        "--locally-selected-description-limit",
        "--shortlist-limit",
        dest="shortlist_limit",
        type=int,
        default=4,
        help=(
            "maximum descriptions shown after deterministic local retrieval "
            "(legacy option name: --shortlist-limit)"
        ),
    )
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-response-bytes", type=int, default=1_048_576)
    parser.add_argument("--max-provider-calls", type=int, default=100)
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Explicitly activate provider calls; the default is a dry-run schedule.",
    )
    parser.add_argument(
        "--cohort",
        type=Path,
        default=ROOT / "eval/results/data-primitive-cohort-2026-07-16",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        default=ROOT / "fixtures/prompt-interception/natural-tasks.json",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        help="Run only this checked task id; repeat to select several tasks.",
    )
    parser.add_argument(
        "--api-key-env",
        metavar="NAME",
        help="Read the provider credential from this environment variable.",
    )
    parser.add_argument(
        "--api-key-stdin",
        action="store_true",
        help="Read exactly one credential line from standard input.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write exact JSON to this path; omit to write to standard output.",
    )
    parser.add_argument("--compact", action="store_true")
    return parser


def _credential(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str | None:
    if args.api_key_env and args.api_key_stdin:
        parser.error("choose only one of --api-key-env or --api-key-stdin")
    value: str | None = None
    if args.api_key_env:
        value = os.environ.get(args.api_key_env)
        if value is None:
            parser.error(f"credential environment variable is not set: {args.api_key_env}")
    elif args.api_key_stdin:
        value = sys.stdin.readline().rstrip("\r\n")
    if value is not None and (not value or "\r" in value or "\n" in value):
        parser.error("provider credential is empty or malformed")
    if args.provider in {"openrouter", "mistral"} and value is None:
        parser.error(f"{args.provider} requires --api-key-env or --api-key-stdin")
    return value


def _provider(args: argparse.Namespace, credential: str | None):
    bounds = {
        "timeout_seconds": args.timeout_seconds,
        "max_response_bytes": args.max_response_bytes,
    }
    if args.provider == "ollama":
        return OllamaChatProvider(
            args.base_url or "http://127.0.0.1:11434",
            bearer_token=credential,
            **bounds,
        )
    if args.provider == "openrouter":
        return OpenRouterChatProvider(
            args.base_url or "https://openrouter.ai/api/v1",
            api_token=credential,
            **bounds,
        )
    if args.provider == "mistral":
        return MistralChatProvider(
            args.base_url or "https://api.mistral.ai/v1",
            api_token=credential,
            **bounds,
        )
    if not args.base_url:
        raise ValueError("openai-compatible provider requires --base-url")
    return OpenAICompatibleChatProvider(
        args.base_url,
        api_token=credential,
        provider_id="openai-compatible",
        **bounds,
    )


def _emit(value: object, args: argparse.Namespace) -> None:
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


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.max_provider_calls <= 0:
        parser.error("--max-provider-calls must be positive")
    if not 0 < args.timeout_seconds <= 300:
        parser.error("--timeout-seconds must be greater than zero and at most 300")
    if not 1 <= args.max_response_bytes <= 16_777_216:
        parser.error("--max-response-bytes must be between 1 and 16777216")
    if not 1 <= args.max_completion_tokens <= 4_096:
        parser.error("--max-completion-tokens must be between 1 and 4096")
    catalog = ReleasedPrimitiveCatalog.load_checked_cohort(args.cohort)
    if not 1 <= args.shortlist_limit < len(catalog.cards):
        parser.error(
            "--shortlist-limit must be positive and smaller than the checked catalog"
        )
    tasks = load_natural_primitive_tasks(args.tasks)
    if args.task_id:
        selected = set(args.task_id)
        tasks = tuple(item for item in tasks if item.task_id in selected)
        missing = sorted(selected - {item.task_id for item in tasks})
        if missing:
            parser.error("unknown checked task id(s): " + ", ".join(missing))
    seeds = tuple(args.seeds or (0,))
    planned_calls = len(tasks) * len(seeds) * 2
    if planned_calls > args.max_provider_calls:
        parser.error(
            f"planned provider calls ({planned_calls}) exceed --max-provider-calls "
            f"({args.max_provider_calls})"
        )
    live_enabled = args.execute_live or os.environ.get(
        "TAEDRI_LIVE_MODEL_CAMPAIGN"
    ) == "1"
    if not live_enabled:
        execution_policy = CampaignExecutionPolicy.create(
            request_timeout_ms=int(args.timeout_seconds * 1_000),
            max_response_bytes=args.max_response_bytes,
        )
        _emit(
            {
                "schema_version": "1.0.0",
                "mode": "dry_run",
                "activation": (
                    "pass --execute-live or set TAEDRI_LIVE_MODEL_CAMPAIGN=1"
                ),
                "provider_id": args.provider,
                "model_requested": args.model,
                "catalog_digest": catalog.digest,
                "task_steps": [
                    {
                        "trajectory_id": item.trajectory_id,
                        "task_id": item.task_id,
                        "step_index": item.step_index,
                        "request_digest": item.request_digest,
                        "hidden_case_set_digest": item.hidden_case_set_digest,
                    }
                    for item in tasks
                ],
                "seeds": list(seeds),
                "arms_per_task_seed": ["full_catalog", "deterministic_shortlist"],
                "provider_calls_planned": planned_calls,
                "provider_call_cap": args.max_provider_calls,
                "timeout_seconds": str(args.timeout_seconds),
                "max_response_bytes": args.max_response_bytes,
                "max_completion_tokens": args.max_completion_tokens,
                "shortlist_limit": args.shortlist_limit,
                "execution_policy": execution_policy.to_dict(),
                "execution_policy_digest": execution_policy.digest,
            },
            args,
        )
        return 0
    credential = _credential(args, parser)
    try:
        provider = _provider(args, credential)
    except ValueError as exc:
        parser.error(str(exc))
    campaign = run_prompt_interception_campaign(
        catalog=catalog,
        tasks=tasks,
        provider=provider,
        provider_id=args.provider,
        model=args.model,
        seeds=seeds,
        max_completion_tokens=args.max_completion_tokens,
        shortlist_limit=args.shortlist_limit,
        request_timeout_ms=int(args.timeout_seconds * 1_000),
        max_response_bytes=args.max_response_bytes,
    )
    _emit(campaign.to_dict(), args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
