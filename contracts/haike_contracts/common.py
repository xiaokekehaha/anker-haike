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
    "upload_receipt",
    "confirm_receipt",
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
    "dealer_authorized",
    "dealer_unauthorized",
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


class StepMedia(Strict):
    """官方 Q&A 步骤里附带的图片 / 视频 / 文章链接（原样引用，不进模型上下文）。"""

    url: str
    kind: Literal["image", "video", "link"]


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
    media: list[StepMedia] = Field(default_factory=list)


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
    seller: str | None = None
    country: str | None = None
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


WarrantyStatus = Literal["in_warranty", "out_of_warranty", "unauthorized_dealer", "unknown"]


class WarrantyDecision(Strict):
    """主办方 SOP「订单质保判断」：有订单看订单质保结束日期；查不到订单看经销商名录（授权 = 购买日起 12 个月）。"""

    status: WarrantyStatus
    basis: Literal["order", "dealer", "none"]
    warranty_end: date | None = None
    as_of: date
    order_no: str | None = None
    sku: str | None = None
    dealer: str | None = None
    country: str | None = None
    reason: str


# 服务单类型：主办方只要求「把换货 / 退款 / 补发信息提交到工具，再转人工」；承运商调查对应 D3。
ServiceOrderType = Literal["replace", "refund", "reship", "carrier_investigation"]
SERVICE_ORDER_TYPES: tuple[str, ...] = ("replace", "refund", "reship", "carrier_investigation")


class ProposalOption(Strict):
    option_id: str
    type: ServiceOrderType
    title: str
    detail: str = ""
    source: Literal["sop", "human"] = "sop"


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
    next_step: str = ""
    updated_at: str | None = None
    source: str = "after-sales tool"
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


# 这张图实际是什么。**不是** ImageRefItem.purpose —— 那个字段记的是「上传时系统在等什么」
# （前端按 pendingKind 填），不是图片内容。两者混用过一次：订单截图在普通首问里以 purpose=fault
# 上传，于是既被当故障照片做曝光门控，又被 evidence 记成「故障图片/视频」凑齐了换货证据四件套。
# document = 订单 / 发票 / 收据 / 配送详情等以文字为主的凭证类图片。
ImageContentKind = Literal["fault_photo", "document", "other"]


class FaultLocalization(Strict):
    findings: list[Finding] = Field(default_factory=list)
    image_quality: ImageQuality = Field(default_factory=lambda: ImageQuality(usable=True))
    # 逐图定性（与读图送进去的图同序）。空列表 = 没读图或读图失败，调用方按「未知」处理。
    content_kinds: list[ImageContentKind] = Field(default_factory=list)
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


class PendingRequest(Strict):
    """交接时队列里尚未办结的一项客户诉求。"""

    intent: str
    quote: str
    status: str


class HandoffBusiness(Strict):
    """交接摘要的业务块（2026-10-09 I7 / I8）：按业务类型带具体字段，已知、缺失、待办分别标明。

    kind 决定人工先看什么：订单暂停看订单 / 包裹 / 条件；设备故障看产品 / 症状 / 已做操作；配件采购看型号与部件。
    """

    kind: Literal["device_fault", "order_change", "parts_purchase", "warranty_review", "safety", "unknown"]
    known: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    pending_requests: list[PendingRequest] = Field(default_factory=list)


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
    warranty: WarrantyDecision | None = None
    recommended_options: list[ProposalOption] = Field(default_factory=list)
    gate_result: GateResult | None = None
    task_queue: list[dict] = Field(default_factory=list)
    emotion_track: list[dict] = Field(default_factory=list)
    draft_reply: str | None = None
    business: HandoffBusiness | None = None
