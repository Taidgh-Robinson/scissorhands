"""Command-line interface for Scissorhands."""

from __future__ import annotations

import asyncio

from scissorhands.application import RunRequest, RunService
from scissorhands.cli.arguments import build_parser
from scissorhands.cli.reporting import (
    TerminalReporter,
    print_preview,
    report_run_result,
)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = RunService(args.root, observer=TerminalReporter())
    request = RunRequest(
        work_item_path=args.work_item,
        agent=args.agent,
        max_iterations=args.max_iterations,
        model=args.model,
        executable=args.executable,
        auto_approve=args.auto_approve,
        contract_path=args.contract,
    )
    try:
        if args.dry_run:
            print_preview(service.preview(request))
            return 0
        result = asyncio.run(service.run(request))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    return report_run_result(result)
