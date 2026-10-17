"""刷新 LoRA 磁盘清单占位入口。读取本机 LoRA 搜索目录，更新 loraInfo/LORA目录.md；不能把资料档案误当成本机已安装文件。

当前未实现；目标电脑 Agent 按项目规则补齐，不以文件存在表示功能就绪。
"""
import json
import sys


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({
        "action": "refresh_lora_catalog",
        "status": "unimplemented",
        "message": "刷新 LoRA 磁盘清单尚未实现，请由目标电脑 Agent 按对应规则补齐。"
    }, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
