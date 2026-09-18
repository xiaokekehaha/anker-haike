"""事件、动作、快照共用的枚举与小对象。"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


class Strict(BaseModel):
    """所有契约模型的基类：拒绝未知字段，保证前后端漂移能被测试与 Schema 比对发现。"""

    model_config = ConfigDict(extra="forbid")


Stage = Literal[
    "intake",
    "disambiguate",
    "out_of_scope",
    "diagnose",
    "guide",
    "verify",
    "escalate",
    "done",
    "consult",
    "context",
    "propose",
    "execute",
    "track",
    "awaiting_human",
]
"""状态机阶段（02 §3）。前端 ProgressBar 把八个阶段折叠为五段展示。"""

EscalateSubstage = Literal["collect_receipt", "extract", "confirm_fields", "lookup", "summarize"]

PendingKind = Literal[
    "select_product",
    "step_feedback",
    "answer_observation",
    "upload_receipt",
    "confirm_receipt",
    "confirm_context",
    "confirm_proposal",
    "upload_retake",
    "rate_satisfaction",
]

Feedback = Literal["solved", "not_solved", "cannot_do"]

ProductState = Literal["confirmed_sku", "category_only", "unknown"]

ReceiptStatus = Literal[
    "not_collected",
    "insufficient",
    "order_verified",
    "order_product_mismatch",
    "needs_manual_check",
    "channel_in_directory",
    "channel_unknown",
]

EmotionLevel = Literal["calm", "anxious", "dissatisfied", "angry", "complaint_risk"]
EmotionStrategy = Literal[
    "normal",
    "reassure_first",
    "reassure_and_shorten",
    "direct_resolution",
    "de_escalate_and_offer_human",
]

ModelTier = Literal["primary", "fallback"]


class PendingInput(Strict):
    issue_id: str | None = None
    """当前唯一允许的用户输入；与 awaiting_input 事件同结构（08 §1、§6）。"""

    kind: PendingKind
    input_token: str
    card_id: str
    version: int = Field(ge=0)


class Emotion(Strict):
    level: EmotionLevel | None
    strategy: EmotionStrategy


class ProductCandidate(Strict):
    sku: str
    name: str
    category: str
    image: str | None = None
    in_scope: bool


class ObservationOption(Strict):
    option_id: str
    label: str
    kind: Literal["finding", "unknown"] = "finding"


class StepObservation(Strict):
    """步骤要收集的检查结果：一个问题与有限选项。功能是否恢复仍由 feedback 三态表达。"""

    observation_id: str
    question: str
    options: list[ObservationOption] = Field(min_length=2)


class ObservationAnswer(Strict):
    """用户对某个步骤观察的选择；option_id 必须是该步骤声明过的选项。"""

    observation_id: str
    option_id: str


class TroubleshootStep(Strict):
    """step_card 的唯一层级：step 对象（08 §5）。"""

    step_id: str
    plan_id: str
    plan_version: int = Field(ge=1)
    step_no: int = Field(ge=1)
    title: str
    instruction: str
    expected_result: str
    caution: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    # 这一步真正的出处。evidence_ids 是同 doc 的宽集合（一步清理滚刷会带上滤网、尘盒的命中），
    # 主引用按 instruction_src 的锚点认出，前端默认只展开它，其余折叠。
    primary_evidence_id: str | None = None
    # 可选：需要判别结果的步骤声明其观察问题；旧客户端忽略该字段仍可只反馈三态
    observations: list[StepObservation] = Field(default_factory=list)


class EvidenceItem(Strict):
    evidence_id: str
    source: str
    doc_id: str
    doc_version: str
    chunk_id: str
    snippet: str
    score: float = Field(ge=0, le=1)
    status: Literal["ok", "replay"] = "ok"


class ReceiptFields(Strict):
    order_no: str | None = None
    channel: str | None = None
    purchase_date: str | None = None
    amount: str | None = None


class ReceiptOutcome(Strict):
    """凭证核对结果：只有已核实事实与下一步，不含质保资格结论（D16，09 §5.2）。"""

    status: ReceiptStatus
    verified_facts: dict[str, str] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)
    next_step: str | None = None


class ExecutedStep(Strict):
    step_id: str
    title: str
    feedback: Feedback
    observed: list[str] = Field(default_factory=list, description="该步骤记录到的观察结果（选项文字）")


class EscalationReason(Strict):
    rule_id: str
    text: str
    # 真实结束原因；rule_id 只是兼容 / 观测层的映射
    cause: str | None = None


class ModelTraceItem(Strict):
    task: str
    model_used: str
    lane: str
    attempts: int = Field(ge=1)


class Clause(Strict):
    clause_id: str
    text: str
    source_doc: str
    doc_version: str
    policy_version: str
    # 条款出处的可点链接。真实政策必须有，演示条款留空；用户可见文本只允许引用有出处的条款。
    source_url: str | None = None


class PolicyCondition(Strict):
    name: str
    expected: Any
    actual: Any
    met: bool


# 官方处置阶梯（anker.com / us.eufy.com 售后政策）：先寄配件，再维修，再换翻新/新机，
# 最后才是按使用时长部分退款；过保另有付费维修。顺序即优先级，propose 按此排序。
Remedy = Literal["parts", "repair", "replace", "refund", "paid_repair", "none"]

REMEDY_LADDER: tuple[str, ...] = ("parts", "repair", "replace", "refund", "paid_repair")


class RemedyDecision(Strict):
    remedy: Remedy
    eligible: bool
    auto_allowed: bool
    cost_bearer: Literal["company", "customer", "shared"] | None = None
    conditions: list[PolicyCondition] = Field(default_factory=list)
    clauses: list[Clause] = Field(default_factory=list)


class PolicyDecision(Strict):
    policy_id: str | None = None
    policy_version: str
    matched: bool = False
    within_warranty: bool | None = None
    warranty_end: date | None = None
    fault_class: Literal["quality", "user_damage", "safety", "unknown"]
    remedies: list[RemedyDecision] = Field(default_factory=list)
    exclusions_hit: list[dict] = Field(default_factory=list)
    needs_human: bool = False
    needs_human_reasons: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    trace_id: str


class DispatchEstimate(Strict):
    working_days: int = Field(gt=0)
    action: Literal["replacement.create"] = "replacement.create"
    actions_version: str


class ProposalOption(Strict):
    option_id: str
    remedy: Remedy
    title: str
    cost_bearer: Literal["company", "customer", "shared"] | None = None
    conditions: list[PolicyCondition] = Field(default_factory=list)
    clauses: list[Clause] = Field(default_factory=list)
    auto_allowed: bool = False
    source: Literal["policy", "human"] = "policy"
    dispatch_estimate: DispatchEstimate | None = None


class GateCheck(Strict):
    name: str
    passed: bool
    detail: str


class GateResult(Strict):
    passed: bool
    checks: list[GateCheck]
    fallback: Literal["await_human", "summarize"] | None = None


class Receipt(Strict):
    status: str
    service_order_no: str | None = None
    tracking_no: str | None = None
    order_no: str | None = None
    eta_days: int | None = None
    next_step: str = ""
    updated_at: str | None = None
    source: str = "业务系统（模拟）"
    data: dict = Field(default_factory=dict)


# 粗定位用九宫格而不是 bbox：各厂商坐标口径互不兼容（OpenAI 不提供、Claude 要绝对像素、
# Qwen 用 0–1000 相对），九宫格是模型无关的最小公分母，且足够支撑「裁剪该格再看一次」。
_CELL_VALUES = ("左上", "上中", "右上", "左中", "中心", "右中", "左下", "下中", "右下")
Cell = Literal["左上", "上中", "右上", "左中", "中心", "右中", "左下", "下中", "右下"]


def _blank_to_none(v: Any) -> Any:
    """模型被要求「没有就留空」时，各家给的是 "" / "无" / "null" 而不是 JSON null。
    这类写法不该让整次调用因 schema 失败而重试 —— 语义就是「没有」，在入口处归一即可。"""
    return None if isinstance(v, str) and v.strip() in ("", "无", "null", "none", "None") else v


# 九宫格字段：空串等价于 None
CellField = Annotated[Cell | None, BeforeValidator(_blank_to_none)]
# 铭牌可读性由代码从 model_hint 派生（含 ? 即 partial，空即 unreadable），不由模型自报：
# 模型自报置信度在错误检测上 AUROC≈0.5（2026-09-14 调研 §A3）。
ModelHintReadable = Literal["full", "partial", "unreadable"]


class Finding(Strict):
    """一条可见故障结论。字段只保留有下游消费者的：
    (part, phenomenon) 驱动 signature → plan_id；evidence 是反幻觉锚点；cell 是裁剪复看的坐标。
    已移除 severity / location / confidence —— 前两个全仓无消费者，confidence 是模型自评不可用。"""

    part: str
    phenomenon: str
    evidence: str | None = None
    cell: CellField = None
    # 第几张图（1 起，对应提示词里的 Image N 标签）。多图时 cell 单独没有意义 ——
    # 「右下」得先知道是哪张图的右下，否则裁剪只能靠猜。
    image_index: int | None = Field(default=None, ge=1)
    raw: dict[str, str] = Field(default_factory=dict)


class ImageQuality(Strict):
    usable: bool
    reasons: list[
        Literal["blurry", "too_dark", "too_bright", "too_far", "wrong_subject", "occluded"]
    ] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)


class FaultLocalization(Strict):
    findings: list[Finding] = Field(default_factory=list)
    image_quality: ImageQuality = Field(default_factory=lambda: ImageQuality(usable=True))
    model_hint: str | None = None
    # 铭牌所在的九宫格，用于「读不清就裁这一格放大再看一次」；定位一个小方块远比读清 14px 小字容易
    model_hint_cell: CellField = None
    model_hint_image: int | None = Field(default=None, ge=1)  # 铭牌在第几张图（1 起）
    model_hint_readable: ModelHintReadable = "unreadable"  # 派生字段，见 ModelHintReadable
    # 型号是否经过第二次独立测量（裁剪放大后复读）确认。只有 True 才允许自动锁 SKU：
    # 未验证的值不该享受已验证的值的权限，否则一个编出来的、恰好在目录里的型号会直接锁错单。
    model_hint_verified: bool = False
    conflicts_with_text: list[str] = Field(default_factory=list)


CaseStatus = Literal[
    "open",
    "diagnosing",
    "proposing",
    "awaiting_confirmation",
    "executing",
    "executing_failed",
    "tracking",
    "closed",
    "awaiting_approval",
    "approved",
    "rejected",
    "closed_unresolved",
    "reopened",
    "escalated_summary",
]


class EscalationSummary(Strict):
    """escalation_summary 的唯一层级：summary 对象（08 §5）。"""

    product: str
    problem: str
    observations: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    steps: list[ExecutedStep] = Field(default_factory=list)
    reason: EscalationReason
    emotion: Emotion
    receipt: ReceiptOutcome
    model_trace: list[ModelTraceItem] = Field(default_factory=list)
    case_id: str | None = None
    policy_decision_brief: dict | None = None
    recommended_options: list[ProposalOption] = Field(default_factory=list)
    gate_result: GateResult | None = None
    task_queue: list[dict] = Field(default_factory=list)
    emotion_track: list[dict] = Field(default_factory=list)
    draft_reply: str | None = None
