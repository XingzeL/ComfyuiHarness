"""投递前检查占位入口。检查服务是否就绪、所选工作流依赖及最近输出；失败时不入队。

当前未实现；目标电脑 Agent 按项目规则补齐，不以文件存在表示功能就绪。
"""
import json
import sys


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({
        "action": "preflight_submit",
        "status": "unimplemented",
        "message": "投递前检查尚未实现，请由目标电脑 Agent 按对应规则补齐。"
    }, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
