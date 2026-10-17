"""Run from the starter directory: python -m harnessui --help."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .client import Client, HarnessError
from .core import build, collect, inspect_service, read_json, status, submit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="HarnessUI：可移植 ComfyUI 最小调用模板")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--env", default="config/environment.local.json")
    parser.add_argument("--registry", default="resources/registry.local.json")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "build", "submit"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--task", required=name != "inspect")
        if name == "submit":
            cmd.add_argument("--retry-of")
    for name in ("status", "collect"):
        commands.add_parser(name).add_argument("--run", required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        client = None
        task = read_json(root / args.task) if getattr(args, "task", None) else None
        registry = read_json(root / args.registry) if task else None
        if args.command in ("inspect", "submit"):
            env = read_json(root / args.env)
            client = Client(env["base_url"], env.get("timeout_seconds", 30))
        if args.command == "build":
            result = build(root, task, registry)
        elif args.command == "inspect":
            result = inspect_service(client, build(root, task, registry) if task else None)
        elif args.command == "submit":
            result = submit(root, task, registry, client, args.retry_of, environment=env)
        elif args.command == "status":
            result = status(root, args.run)
        else:
            result = collect(root, args.run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        failed = result.get("execution_status") in ("prepared", "submitting", "failed", "submit_failed", "submission_unknown", "unknown")
        return 1 if failed or result.get("dependency_errors") or result.get("collection_status") == "validation_failed" else 0
    except (HarnessError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
