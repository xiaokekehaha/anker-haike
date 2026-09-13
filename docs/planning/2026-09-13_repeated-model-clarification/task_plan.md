# 重复询问型号排查

## Goal
定位会话 eb21876242c644fe915e3250e4f84b22 回复 00001 后重复询问型号、未检索的原因，建立复现并修复确认的问题。

## Phases
1. 采集真实会话、事件及调用证据，构建可运行复现。**Status:** complete
2. 对比假设，定位上下文/型号识别/流程分支根因。**Status:** complete
3. 必要修复与针对性回归验证。**Status:** complete
4. 记录根因、验证和局限。**Status:** complete

## Next Step
诊断和源码修复完成；运行容器尚未部署本次修复，后续部署后可用独立会话验证真实模型与知识服务。

## Constraints
保留现有工作区改动；本项目数据库可读写，其他库只读；证据不记录密钥。

## Errors Encountered
- config/catalog.yaml 不存在：改读实际 config/products.yaml。
- 原回归第一次失败：准确捕获用户重复型号追问，作为修复前红灯。
- 测试文件格式检查未通过：已用 ruff format 修正，lint 无问题。
- 运行容器文件路径 /srv/orchestrator/app 不存在：按 Dockerfile 修正为 /srv/app。
