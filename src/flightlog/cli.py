"""Command-line interface for flightlog.

Subcommands:
  validate  check a telemetry CSV (data-quality gate)
  process   compute metrics -> metrics.json
  render    draw the flight report -> flight-report.png
  report    do all of the above into an output directory
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flightlog.metrics import compute_metrics
from flightlog.telemetry import ValidationResult, validate_file


def _report_validation(result: ValidationResult) -> None:
    print(f"rows read: {result.total_rows}")
    print(f"valid samples: {len(result.samples)}")
    print(f"dropped rows: {result.dropped_rows}")
    for err in result.errors:
        print(f"error: {err}", file=sys.stderr)


def _load_valid(path: str) -> ValidationResult | None:
    result = validate_file(path)
    if not result.ok:
        _report_validation(result)
        return None
    if result.dropped_rows:
        print(
            f"note: dropped {result.dropped_rows} invalid row(s) of {result.total_rows}",
            file=sys.stderr,
        )
    return result


def cmd_validate(args: argparse.Namespace) -> int:
    result = validate_file(args.path)
    _report_validation(result)
    if result.ok:
        print("OK: log is valid")
        return 0
    return 1


def cmd_process(args: argparse.Namespace) -> int:
    result = _load_valid(args.path)
    if result is None:
        return 1
    metrics = compute_metrics(result.samples)
    Path(args.out).write_text(json.dumps(metrics.to_dict(), indent=2))
    print(json.dumps(metrics.to_dict(), indent=2))
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    result = _load_valid(args.path)
    if result is None:
        return 1
    metrics = compute_metrics(result.samples)
    from flightlog.render import render_report  # lazy: only needed here

    render_report(result.samples, metrics, args.out)
    print(f"wrote {args.out}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    result = _load_valid(args.path)
    if result is None:
        return 1
    metrics = compute_metrics(result.samples)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics.to_dict(), indent=2))

    from flightlog.render import render_report  # lazy

    report_path = out_dir / "flight-report.png"
    render_report(result.samples, metrics, str(report_path))

    print(f"wrote {metrics_path}")
    print(f"wrote {report_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flightlog",
        description="Validate drone telemetry logs and render a visual flight report.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="check a telemetry CSV")
    p_validate.add_argument("path")
    p_validate.set_defaults(func=cmd_validate)

    p_process = sub.add_parser("process", help="compute metrics -> JSON")
    p_process.add_argument("path")
    p_process.add_argument("--out", default="metrics.json")
    p_process.set_defaults(func=cmd_process)

    p_render = sub.add_parser("render", help="draw the flight report -> PNG")
    p_render.add_argument("path")
    p_render.add_argument("--out", default="flight-report.png")
    p_render.set_defaults(func=cmd_render)

    p_report = sub.add_parser("report", help="validate + process + render into a directory")
    p_report.add_argument("path")
    p_report.add_argument("--out-dir", default="out")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
