"""python run.py --config config.example.json --dry-run"""
import argparse
import json
import sys
from pathlib import Path

if __package__:
    from .api import run_module
else:
    from api import run_module


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="逐工作流异步投递模板")
    parser.add_argument("--config", "-c", type=Path, required=True)
    parser.add_argument("--env", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--front", action="store_true")
    parser.add_argument("--save-prompt", type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        result = run_module(config, dry_run=args.dry_run, front=args.front,
                            environment_path=args.env, save_prompt_path=args.save_prompt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in ("submit_failed", "submission_unknown") else 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
