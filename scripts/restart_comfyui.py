"""ComfyUI 重启入口。由目标电脑 Agent 根据 scripts/README.md 生成本机实现。"""
import json
import sys


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({
        "action": "restart",
        "status": "unconfigured",
        "message": "此脚本尚未配置；请由本机 Agent 按 scripts/README.md 补齐重启实现。"
    }, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
