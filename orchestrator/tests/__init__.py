import os

# 单测默认不发模型请求：图节点里的 ModelRouter 取用返回 None，走降级路径。需要真实模型的测试自行 set_model_router。
os.environ.setdefault("HAIKE_LLM", "off")
# 同理，知识适配器默认关闭（tool_call failed 路径）；需要时 set_knowledge_adapter 注入假适配器。
os.environ.setdefault("HAIKE_KNOWLEDGE", "off")
