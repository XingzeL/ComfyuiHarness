"""输出汇总占位入口。在结果确认后将有效成图汇总到 Grokbot/output，避免覆盖已有结果。

当前未实现；目标电脑 Agent 按项目规则补齐，不以文件存在表示功能就绪。
"""
import json
import sys


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({
        "action": "collect_outputs",
        "status": "unimplemented",
        "message": "输出汇总尚未实现，请由目标电脑 Agent 按对应规则补齐。"
    }, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
