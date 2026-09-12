"""故障与边界场景巡检（票 45）：`haike-inspect` 一条命令跑完 01 §3.3 / 09 §1.1 / 09 §4.1 的场景并出报告。

- harness.py   进程内运行环境（内存存储 + 按 task 分脚本的假模型 + 脚本知识适配器 + run_metric 捕获）
- scenarios.py 场景定义（boundary / routing / rewrite / concurrency / live）
- report.py    JSON + Markdown 报告，findings.md 回填
- cli.py       命令行入口
"""
