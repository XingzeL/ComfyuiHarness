"""刷新 LoRA HTML 目录占位入口。读取 LoRA README、预览资料及已有分类，更新 loraInfo/index.html；展示细节由本机 Agent 和用户确定。

当前未实现；目标电脑 Agent 按项目规则补齐，不以文件存在表示功能就绪。
"""
import json
import sys


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({
        "action": "refresh_lora_index",
        "status": "unimplemented",
        "message": "刷新 LoRA HTML 目录尚未实现，请由目标电脑 Agent 按对应规则补齐。"
    }, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
