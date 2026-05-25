from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ops_logging import filter_events, read_summary, write_event, write_summary


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def command_record(args: argparse.Namespace) -> int:
    details = json.loads(args.details_json)
    event = write_event(
        args.run_root,
        level=args.level,
        event_type=args.event_type,
        stage=args.stage,
        model=args.model,
        message=args.message,
        details=details,
        source=args.source,
    )
    print_json(event)
    return 0


def command_summary(args: argparse.Namespace) -> int:
    summary = read_summary(args.run_root) or write_summary(args.run_root)
    print_json(summary)
    return 0


def command_events(args: argparse.Namespace) -> int:
    rows = filter_events(args.run_root, level=args.level, event_type=args.event_type, model=args.model)
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


def _has_rate_limit_signal(summary: dict[str, object]) -> bool:
    text = json.dumps(
        {
            "issues": summary.get("issues") or [],
            "recommended_actions": summary.get("recommended_actions") or [],
        },
        ensure_ascii=False,
    ).lower()
    return "429" in text or "rate limit" in text or "too many requests" in text


def command_doctor(args: argparse.Namespace) -> int:
    summary = write_summary(args.run_root)
    print(f"status: {summary['status']}")
    print(f"current_stage: {summary['current_stage'] or '-'}")
    print("")
    print("issues:")
    if summary["issues"]:
        for issue in summary["issues"]:
            print(f"- {issue}")
    else:
        print("- none")
    if _has_rate_limit_signal(summary):
        print("- Rate limit detected")
    print("")
    print("recommended_actions:")
    if summary["recommended_actions"]:
        for action in summary["recommended_actions"]:
            print(f"- {action}")
    else:
        print("- none")
    print("")
    print("key_files:")
    for key, value in summary["key_files"].items():
        print(f"- {key}: {value}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect local operations logs for a GEO run root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record")
    record.add_argument("--run-root", required=True)
    record.add_argument("--level", default="info")
    record.add_argument("--event-type", required=True)
    record.add_argument("--stage", default="")
    record.add_argument("--model", default="")
    record.add_argument("--message", default="")
    record.add_argument("--details-json", default="{}")
    record.add_argument("--source", default="scripts/ops_logs.py")
    record.set_defaults(func=command_record)

    summary = subparsers.add_parser("summary")
    summary.add_argument("--run-root", required=True)
    summary.set_defaults(func=command_summary)

    events = subparsers.add_parser("events")
    events.add_argument("--run-root", required=True)
    events.add_argument("--level", default="")
    events.add_argument("--event-type", default="")
    events.add_argument("--model", default="")
    events.set_defaults(func=command_events)

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--run-root", required=True)
    doctor.set_defaults(func=command_doctor)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
