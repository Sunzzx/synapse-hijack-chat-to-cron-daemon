"""
synapse_hijack.cli
==================
Command line interface for synapse-hijack-chat-to-cron-daemon.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cron_bridge import CronBridge, CronJobDefinition
from .daemon import SynapseDaemon
from .intent_extractor import IntentExtractor
from .self_healing_engine import SelfHealingEngine


def main():
    parser = argparse.ArgumentParser(
        prog="synapse-hijack",
        description="Autonomous omni-intent extraction, self-healing execution loops, and chat-to-cron daemon.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Sub-commands")

    # parse
    parse_p = subparsers.add_parser("parse", help="Parse text for actionable intents")
    parse_p.add_argument("--text", "-t", type=str, help="Raw chat text or message string")
    parse_p.add_argument("--file", "-f", type=Path, help="Path to text or chat transcript file")
    parse_p.add_argument("--json", action="store_true", help="Output in JSON format")

    # execute
    exec_p = subparsers.add_parser("execute", help="Run a command through 3-tier self-healing loop")
    exec_p.add_argument("cmd", nargs="+", help="Command and arguments to execute")
    exec_p.add_argument("--timeout", type=int, default=30, help="Per-strategy timeout in seconds")

    # cron-list
    subparsers.add_parser("cron-list", help="List active Hermes cron jobs")

    # daemon
    daemon_p = subparsers.add_parser("daemon", help="Run the synapse background daemon")
    daemon_p.add_argument("--foreground", action="store_true", default=True, help="Run in foreground")

    # status
    subparsers.add_parser("status", help="Show system status and health")

    args = parser.parse_args()

    if not args.subcommand or args.subcommand == "status":
        bridge = CronBridge()
        jobs = bridge.load_jobs()
        print("⚡ SYNAPSE-HIJACK OMNI-EXECUTION DAEMON")
        print("Status: Active | Architecture: Multi-tier Self-Healing + Zero-Touch Chat Parsing")
        print(f"Connected Hermes Cron Jobs: {len(jobs)}")
        for j in jobs[:5]:
            print(f"  • {j.get('name')}: {j.get('schedule_display', 'interval')} [status: {j.get('last_status')}]")
        if len(jobs) > 5:
            print(f"  ... and {len(jobs) - 5} more jobs.")
        sys.exit(0)

    if args.subcommand == "parse":
        text = args.text or ""
        if args.file and args.file.exists():
            text = args.file.read_text(encoding="utf-8", errors="ignore")
        if not text:
            print("Error: No text provided. Use --text or --file.", file=sys.stderr)
            sys.exit(1)

        extractor = IntentExtractor()
        intents = extractor.parse(text)
        if args.json:
            print(json.dumps([i.to_dict() for i in intents], indent=2))
        else:
            print(f"Extracted {len(intents)} intent(s):")
            for idx, intent in enumerate(intents, 1):
                print(f"[{idx}] Kind: {intent.kind.value} | Target: {intent.target} | Action: {intent.action}")
                if intent.schedule:
                    print(f"    Schedule: {intent.schedule}")
                if intent.suggested_repo_name:
                    print(f"    Suggested Crazy Repo: {intent.suggested_repo_name}")
                print(f"    Snippet: \"{intent.raw_snippet}\"")

    elif args.subcommand == "execute":
        engine = SelfHealingEngine(timeout_per_strategy=args.timeout)
        cmd = " ".join(args.cmd)
        print(f"[*] Executing with 3-tier self-healing verification: {cmd}")
        res = engine.execute_command(cmd)
        print(res.summary())
        if res.output:
            print(f"--- OUTPUT ---\n{res.output}")
        if res.error:
            print(f"--- ERROR ---\n{res.error}", file=sys.stderr)
        sys.exit(0 if res.overall_success else 1)

    elif args.subcommand == "cron-list":
        bridge = CronBridge()
        jobs = bridge.load_jobs()
        print(f"Hermes Registered Cron Jobs ({len(jobs)} total):")
        for j in jobs:
            print(f"  [{j.get('id')}] {j.get('name')}: {j.get('schedule_display')} | script: {j.get('script')} | enabled: {j.get('enabled')}")

    elif args.subcommand == "daemon":
        daemon = SynapseDaemon()
        daemon.start_foreground()


if __name__ == "__main__":
    main()
