// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.
// Source: contracts/schema/snapshot.schema.json
// SHA-256: d18b331d0fa840d6e57e1f95352e0f6b416a0db6a136aecd9484509dfc47ddea

export type ActiveIssueId = string | null;
export type DeadlineAt = string;
export type RunId = string;
export type StartedAt = string;
export type At = string;
export type RunId1 = string;
export type Issues = {
  [k: string]: unknown;
}[];
export type At1 = string;
export type Code = string;
export type Message = string;
export type Recoverable = boolean;
export type LastEventSeq = number;
export type At2 = string | null;
export type CardId = string;
export type FirstSeq = number;
export type HandoffStatus = 'prepared' | 'requested' | 'accepted' | 'failed' | 'cancelled';
export type IssueId = string | null;
export type Kind = 'escalation_summary';
export type LastSeq = number;
export type PreviousCardId = string | null;
export type Revision = number;
export type SourceThroughSeq = number;
export type Kind1 =
  'device_fault' | 'order_change' | 'parts_purchase' | 'warranty_review' | 'safety' | 'unknown';
export type Missing = string[];
export type Intent = string;
export type Quote = string;
export type Status = string;
export type PendingRequests = PendingRequest[];
export type CaseId = string | null;
export type DraftReply = string | null;
export type Level = ('calm' | 'anxious' | 'dissatisfied' | 'angry' | 'complaint_risk') | null;
export type Strategy =
  | 'normal'
  | 'reassure_first'
  | 'reassure_and_shorten'
  | 'direct_resolution'
  | 'de_escalate_and_offer_human';
export type EmotionTrack = {
  [k: string]: unknown;
}[];
export type Detail = string;
export type Name = string;
export type Passed = boolean;
export type Checks = GateCheck[];
export type Fallback = ('await_human' | 'summarize') | null;
export type Passed1 = boolean;
export type Hypotheses = string[];
export type Attempts = number;
export type Lane = string;
export type ModelUsed = string;
export type Task = string;
export type ModelTrace = ModelTraceItem[];
export type Observations = string[];
export type Problem = string;
export type Product = string;
export type Cause = string | null;
export type RuleId = string;
export type Text = string;
export type Conflicts = string[];
export type NextStep = string | null;
export type Status1 =
  | 'not_collected'
  | 'insufficient'
  | 'order_verified'
  | 'order_product_mismatch'
  | 'needs_manual_check'
  | 'dealer_authorized'
  | 'dealer_unauthorized';
export type Detail1 = string;
export type OptionId = string;
export type Source = 'sop' | 'human';
export type Title = string;
export type Type = 'replace' | 'refund' | 'reship' | 'carrier_investigation';
export type RecommendedOptions = ProposalOption[];
export type Feedback = 'solved' | 'not_solved' | 'cannot_do';
export type StepId = string;
export type Title1 = string;
export type Steps = ExecutedStep[];
export type TaskQueue = {
  [k: string]: unknown;
}[];
export type AsOf = string;
export type Basis = 'order' | 'dealer' | 'none';
export type Country = string | null;
export type Dealer = string | null;
export type OrderNo = string | null;
export type Reason = string;
export type Sku = string | null;
export type Status2 = 'in_warranty' | 'out_of_warranty' | 'unauthorized_dealer' | 'unknown';
export type WarrantyEnd = string | null;
export type SummaryId = string;
export type UpdatedAt = string;
export type LatestSummaries = SummaryItem[];
export type CardId1 = string;
export type InputToken = string;
export type IssueId1 = string | null;
export type Kind2 =
  | 'select_product'
  | 'step_feedback'
  | 'upload_receipt'
  | 'confirm_receipt'
  | 'confirm_proposal'
  | 'upload_retake'
  | 'rate_satisfaction';
export type Version = number;
export type SessionId = string;
export type Stage =
  | 'intake'
  | 'disambiguate'
  | 'out_of_scope'
  | 'diagnose'
  | 'guide'
  | 'verify'
  | 'escalate'
  | 'done'
  | 'consult'
  | 'context'
  | 'propose'
  | 'execute'
  | 'track'
  | 'awaiting_human';
export type Substage = string | null;
export type At3 = string;
export type FirstSeq1 = number;
export type Id = string;
export type ImageIds = string[];
export type ImageId = string;
export type Mime = string;
export type Purpose = 'fault' | 'receipt';
export type Sha256 = string;
export type Size = number;
export type Images = ImageRefItem[];
export type IssueId2 = string | null;
export type Kind3 = 'user_message';
export type LastSeq1 = number;
export type Text1 = string;
export type ActionKind = string;
export type At4 = string | null;
export type FirstSeq2 = number;
export type Id1 = string;
export type IssueId3 = string | null;
export type Kind4 = 'action';
export type Label = string;
export type LastSeq2 = number;
export type At5 = string | null;
export type FirstSeq3 = number;
export type IssueId4 = string | null;
export type Kind5 = 'assistant_message';
export type LastSeq3 = number;
export type MessageId = string;
export type ModelTier = ('primary' | 'fallback') | null;
export type Replaces = string | null;
export type ReplyToInputId = string | null;
export type Status3 = 'completed' | 'aborted' | 'streaming' | 'replaced';
export type Text2 = string;
export type At6 = string | null;
export type FirstSeq4 = number;
export type IssueId5 = string | null;
export type Kind6 = 'tool';
export type LastSeq4 = number;
export type Name1 = string;
export type Status4 = 'started' | 'finished' | 'failed';
export type Summary = string | null;
export type ToolId = string;
export type AllowUnknown = boolean;
export type At7 = string | null;
export type Category = string;
export type Image = string | null;
export type InScope = boolean;
export type Name2 = string;
export type Sku1 = string;
export type Candidates = ProductCandidate[];
export type CardId2 = string;
export type FirstSeq5 = number;
export type IssueId6 = string | null;
export type Kind7 = 'product_card';
export type LastSeq5 = number;
export type Note = string | null;
/**
 * 用户已选结果
 */
export type SelectedSku = string | null;
/**
 * 用户选了「其他型号 / 不确定」
 */
export type SelectedUnknown = boolean;
export type Version1 = number;
export type At8 = string | null;
export type CardId3 = string;
export type Feedback1 = ('solved' | 'not_solved' | 'cannot_do') | null;
export type FirstSeq6 = number;
export type IssueId7 = string | null;
export type Kind8 = 'step_card';
export type LastSeq6 = number;
export type Note1 = string | null;
export type Seen = string | null;
export type Caution = string | null;
export type EvidenceIds = string[];
export type ExpectedResult = string;
export type Instruction = string;
export type Kind9 = 'image' | 'video' | 'link';
export type Url = string;
export type Media = StepMedia[];
export type PlanId = string;
export type PlanVersion = number;
export type PrimaryEvidenceId = string | null;
export type StepId1 = string;
export type StepNo = number;
export type Title2 = string;
export type Version2 = number;
export type At9 = string | null;
export type CardId4 = string;
export type Amount = string | null;
export type Country1 = string | null;
export type OrderNo1 = string | null;
export type PurchaseDate = string | null;
export type Seller = string | null;
export type FirstSeq7 = number;
export type IssueId8 = string | null;
export type Kind10 = 'receipt_card';
export type LastSeq7 = number;
export type SkippedReason = ('none' | 'unreadable' | 'later') | null;
export type Unreadable = string[];
export type Version3 = number;
export type At10 = string | null;
export type FirstSeq8 = number;
export type IssueId9 = string | null;
export type ChunkId = string;
export type DocId = string;
export type DocVersion = string;
export type EvidenceId = string;
export type Score = number;
export type Snippet = string;
export type Source1 = string;
export type Status5 = 'ok' | 'replay';
export type Items = EvidenceItem[];
export type Kind11 = 'evidence';
export type LastSeq8 = number;
export type At11 = string | null;
export type CardId5 = string;
export type ChosenOptionId = string | null;
export type DecisionSummary = string;
export type DeclinedReason = string | null;
export type FirstSeq9 = number;
export type IssueId10 = string | null;
export type Kind12 = 'proposal_card';
export type LastSeq9 = number;
export type Options = ProposalOption[];
export type Retry = boolean;
export type Version4 = number;
export type ActionKind1 = string;
export type At12 = string | null;
export type CardId6 = string;
export type ExecutionId = string;
export type FirstSeq10 = number;
export type IdempotencyKey = string;
export type IssueId11 = string | null;
export type Kind13 = 'execution_card';
export type LastSeq10 = number;
export type NextStep1 = string;
export type OrderNo2 = string | null;
export type ServiceOrderNo = string | null;
export type Source2 = string;
export type Status6 = string;
export type TrackingNo = string | null;
export type UpdatedAt1 = string | null;
export type Status7 = 'succeeded' | 'failed';
export type Version5 = number;
export type At13 = string | null;
export type CardId7 = string;
export type FirstSeq11 = number;
export type Guidance = string[];
export type IssueId12 = string | null;
export type Kind14 = 'retake_card';
export type LastSeq11 = number;
export type Reasons = string[];
export type Skipped = boolean;
export type Version6 = number;
export type At14 = string | null;
export type CardId8 = string;
export type CaseId1 = string | null;
export type FirstSeq12 = number;
export type IssueId13 = string | null;
export type Kind15 = 'rating_card';
export type LastSeq12 = number;
export type Score1 = number | null;
export type Version7 = number;
export type At15 = string | null;
export type CardId9 = string;
export type CaseId2 = string;
export type ComplaintRisk = boolean;
export type FirstSeq13 = number;
export type IssueId14 = string | null;
export type Kind16 = 'case_changed';
export type LastSeq13 = number;
export type Owner = string | null;
export type Priority = 'normal' | 'high';
export type Reason1 = string;
export type Status8 =
  | 'open'
  | 'diagnosing'
  | 'proposing'
  | 'awaiting_confirmation'
  | 'executing'
  | 'executing_failed'
  | 'tracking'
  | 'closed'
  | 'awaiting_approval'
  | 'approved'
  | 'rejected'
  | 'closed_unresolved'
  | 'reopened'
  | 'escalated_summary';
export type UpdatedAt2 = string;
export type Version8 = number;
export type Timeline = (
  | UserMessageItem
  | ActionItem
  | AssistantMessageItem
  | ToolItem
  | ProductCardItem
  | StepCardItem
  | ReceiptCardItem
  | EvidenceItemGroup
  | SummaryItem
  | ProposalCardItem
  | ExecutionCardItem
  | RetakeCardItem
  | RatingCardItem
  | CaseStatusItem
)[];
export type Version9 = number;

export interface SessionSnapshotSchema {
  contract: SessionSnapshot;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "SessionSnapshot".
 */
export interface SessionSnapshot {
  active_issue_id?: ActiveIssueId;
  active_run?: ActiveRun | null;
  cancelled_run?: CancelledRun | null;
  issues?: Issues;
  last_error?: LastError | null;
  last_event_seq?: LastEventSeq;
  latest_summaries?: LatestSummaries;
  pending_input?: PendingInput | null;
  session_id: SessionId;
  stage: Stage;
  substage?: Substage;
  timeline?: Timeline;
  version: Version9;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ActiveRun".
 */
export interface ActiveRun {
  deadline_at: DeadlineAt;
  run_id: RunId;
  started_at: StartedAt;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "CancelledRun".
 */
export interface CancelledRun {
  at: At;
  run_id: RunId1;
}
/**
 * 最近一次运行留下的错误；更早 run 的错误不进快照（只在事件表里供审计）。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "LastError".
 */
export interface LastError {
  at: At1;
  code: Code;
  message?: Message;
  recoverable?: Recoverable;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "SummaryItem".
 */
export interface SummaryItem {
  at?: At2;
  card_id: CardId;
  first_seq?: FirstSeq;
  handoff_status?: HandoffStatus;
  issue_id?: IssueId;
  kind: Kind;
  last_seq?: LastSeq;
  previous_card_id?: PreviousCardId;
  revision: Revision;
  source_through_seq: SourceThroughSeq;
  summary: EscalationSummary;
  summary_id: SummaryId;
  updated_at: UpdatedAt;
}
/**
 * escalation_summary 的唯一层级：summary 对象（08 §5）。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "EscalationSummary".
 */
export interface EscalationSummary {
  business?: HandoffBusiness | null;
  case_id?: CaseId;
  draft_reply?: DraftReply;
  emotion: Emotion;
  emotion_track?: EmotionTrack;
  gate_result?: GateResult | null;
  hypotheses?: Hypotheses;
  model_trace?: ModelTrace;
  observations?: Observations;
  problem: Problem;
  product: Product;
  reason: EscalationReason;
  receipt: ReceiptOutcome;
  recommended_options?: RecommendedOptions;
  steps?: Steps;
  task_queue?: TaskQueue;
  warranty?: WarrantyDecision | null;
}
/**
 * 交接摘要的业务块（2026-10-09 I7 / I8）：按业务类型带具体字段，已知、缺失、待办分别标明。
 *
 * kind 决定人工先看什么：订单暂停看订单 / 包裹 / 条件；设备故障看产品 / 症状 / 已做操作；配件采购看型号与部件。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "HandoffBusiness".
 */
export interface HandoffBusiness {
  kind: Kind1;
  known?: Known;
  missing?: Missing;
  pending_requests?: PendingRequests;
}
export interface Known {
  [k: string]: string;
}
/**
 * 交接时队列里尚未办结的一项客户诉求。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "PendingRequest".
 */
export interface PendingRequest {
  intent: Intent;
  quote: Quote;
  status: Status;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "Emotion".
 */
export interface Emotion {
  level: Level;
  strategy: Strategy;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "GateResult".
 */
export interface GateResult {
  checks: Checks;
  fallback?: Fallback;
  passed: Passed1;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "GateCheck".
 */
export interface GateCheck {
  detail: Detail;
  name: Name;
  passed: Passed;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ModelTraceItem".
 */
export interface ModelTraceItem {
  attempts: Attempts;
  lane: Lane;
  model_used: ModelUsed;
  task: Task;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "EscalationReason".
 */
export interface EscalationReason {
  cause?: Cause;
  rule_id: RuleId;
  text: Text;
}
/**
 * 凭证核对结果：只有已核实事实与下一步，不含质保资格结论（D16，09 §5.2）。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ReceiptOutcome".
 */
export interface ReceiptOutcome {
  conflicts?: Conflicts;
  next_step?: NextStep;
  status: Status1;
  verified_facts?: VerifiedFacts;
}
export interface VerifiedFacts {
  [k: string]: string;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ProposalOption".
 */
export interface ProposalOption {
  detail?: Detail1;
  option_id: OptionId;
  source?: Source;
  title: Title;
  type: Type;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ExecutedStep".
 */
export interface ExecutedStep {
  feedback: Feedback;
  step_id: StepId;
  title: Title1;
}
/**
 * 主办方 SOP「订单质保判断」：有订单看订单质保结束日期；查不到订单看经销商名录（授权 = 购买日起 12 个月）。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "WarrantyDecision".
 */
export interface WarrantyDecision {
  as_of: AsOf;
  basis: Basis;
  country?: Country;
  dealer?: Dealer;
  order_no?: OrderNo;
  reason: Reason;
  sku?: Sku;
  status: Status2;
  warranty_end?: WarrantyEnd;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "PendingInput".
 */
export interface PendingInput {
  card_id: CardId1;
  input_token: InputToken;
  issue_id?: IssueId1;
  kind: Kind2;
  version: Version;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "UserMessageItem".
 */
export interface UserMessageItem {
  at: At3;
  first_seq?: FirstSeq1;
  id: Id;
  image_ids?: ImageIds;
  images?: Images;
  issue_id?: IssueId2;
  kind: Kind3;
  last_seq?: LastSeq1;
  text: Text1;
}
/**
 * 会话期图片引用（票 29）：只有引用与摘要，字节在 session_images，1 小时后清理。
 *
 * purpose 记的是**上传时机**（前端按 pendingKind 填：等凭证时 receipt，其余 fault），
 * 不是图片内容。「这张图实际是什么」由读图定性回答，见 common.ImageContentKind。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ImageRefItem".
 */
export interface ImageRefItem {
  image_id: ImageId;
  mime: Mime;
  purpose: Purpose;
  sha256: Sha256;
  size: Size;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ActionItem".
 */
export interface ActionItem {
  action_kind: ActionKind;
  at?: At4;
  first_seq?: FirstSeq2;
  id: Id1;
  issue_id?: IssueId3;
  kind: Kind4;
  label: Label;
  last_seq?: LastSeq2;
}
/**
 * message_start / message / message_end 折叠后的完整文本。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "AssistantMessageItem".
 */
export interface AssistantMessageItem {
  at?: At5;
  first_seq?: FirstSeq3;
  issue_id?: IssueId4;
  kind: Kind5;
  last_seq?: LastSeq3;
  message_id: MessageId;
  model_tier?: ModelTier;
  replaces?: Replaces;
  reply_to_input_id?: ReplyToInputId;
  status: Status3;
  text: Text2;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ToolItem".
 */
export interface ToolItem {
  at?: At6;
  first_seq?: FirstSeq4;
  issue_id?: IssueId5;
  kind: Kind6;
  last_seq?: LastSeq4;
  name: Name1;
  status: Status4;
  summary?: Summary;
  tool_id: ToolId;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ProductCardItem".
 */
export interface ProductCardItem {
  allow_unknown?: AllowUnknown;
  at?: At7;
  candidates: Candidates;
  card_id: CardId2;
  first_seq?: FirstSeq5;
  issue_id?: IssueId6;
  kind: Kind7;
  last_seq?: LastSeq5;
  note?: Note;
  selected_sku?: SelectedSku;
  selected_unknown?: SelectedUnknown;
  version: Version1;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ProductCandidate".
 */
export interface ProductCandidate {
  category: Category;
  image?: Image;
  in_scope: InScope;
  name: Name2;
  sku: Sku1;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "StepCardItem".
 */
export interface StepCardItem {
  at?: At8;
  card_id: CardId3;
  feedback?: Feedback1;
  first_seq?: FirstSeq6;
  issue_id?: IssueId7;
  kind: Kind8;
  last_seq?: LastSeq6;
  note?: Note1;
  seen?: Seen;
  step: TroubleshootStep;
  version: Version2;
}
/**
 * step_card 的唯一层级：step 对象（08 §5）。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "TroubleshootStep".
 */
export interface TroubleshootStep {
  caution?: Caution;
  evidence_ids?: EvidenceIds;
  expected_result: ExpectedResult;
  instruction: Instruction;
  media?: Media;
  plan_id: PlanId;
  plan_version: PlanVersion;
  primary_evidence_id?: PrimaryEvidenceId;
  step_id: StepId1;
  step_no: StepNo;
  title: Title2;
}
/**
 * 官方 Q&A 步骤里附带的图片 / 视频 / 文章链接（原样引用，不进模型上下文）。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "StepMedia".
 */
export interface StepMedia {
  kind: Kind9;
  url: Url;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ReceiptCardItem".
 */
export interface ReceiptCardItem {
  at?: At9;
  card_id: CardId4;
  confidence?: Confidence;
  confirmed_fields?: ReceiptFields | null;
  fields: ReceiptFields;
  first_seq?: FirstSeq7;
  issue_id?: IssueId8;
  kind: Kind10;
  last_seq?: LastSeq7;
  skipped_reason?: SkippedReason;
  unreadable?: Unreadable;
  version: Version3;
}
export interface Confidence {
  [k: string]: number;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ReceiptFields".
 */
export interface ReceiptFields {
  amount?: Amount;
  country?: Country1;
  order_no?: OrderNo1;
  purchase_date?: PurchaseDate;
  seller?: Seller;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "EvidenceItemGroup".
 */
export interface EvidenceItemGroup {
  at?: At10;
  first_seq?: FirstSeq8;
  issue_id?: IssueId9;
  items: Items;
  kind: Kind11;
  last_seq?: LastSeq8;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "EvidenceItem".
 */
export interface EvidenceItem {
  chunk_id: ChunkId;
  doc_id: DocId;
  doc_version: DocVersion;
  evidence_id: EvidenceId;
  score: Score;
  snippet: Snippet;
  source: Source1;
  status?: Status5;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ProposalCardItem".
 */
export interface ProposalCardItem {
  at?: At11;
  card_id: CardId5;
  chosen_option_id?: ChosenOptionId;
  decision_summary: DecisionSummary;
  declined_reason?: DeclinedReason;
  first_seq?: FirstSeq9;
  issue_id?: IssueId10;
  kind: Kind12;
  last_seq?: LastSeq9;
  options: Options;
  retry?: Retry;
  version: Version4;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ExecutionCardItem".
 */
export interface ExecutionCardItem {
  action_kind: ActionKind1;
  at?: At12;
  card_id: CardId6;
  execution_id: ExecutionId;
  first_seq?: FirstSeq10;
  idempotency_key: IdempotencyKey;
  issue_id?: IssueId11;
  kind: Kind13;
  last_seq?: LastSeq10;
  receipt: Receipt;
  status: Status7;
  version: Version5;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "Receipt".
 */
export interface Receipt {
  data?: Data;
  next_step?: NextStep1;
  order_no?: OrderNo2;
  service_order_no?: ServiceOrderNo;
  source?: Source2;
  status: Status6;
  tracking_no?: TrackingNo;
  updated_at?: UpdatedAt1;
}
export interface Data {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "RetakeCardItem".
 */
export interface RetakeCardItem {
  at?: At13;
  card_id: CardId7;
  first_seq?: FirstSeq11;
  guidance: Guidance;
  issue_id?: IssueId12;
  kind: Kind14;
  last_seq?: LastSeq11;
  reasons: Reasons;
  skipped?: Skipped;
  version: Version6;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "RatingCardItem".
 */
export interface RatingCardItem {
  at?: At14;
  card_id: CardId8;
  case_id?: CaseId1;
  first_seq?: FirstSeq12;
  issue_id?: IssueId13;
  kind: Kind15;
  last_seq?: LastSeq12;
  score?: Score1;
  version: Version7;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "CaseStatusItem".
 */
export interface CaseStatusItem {
  at?: At15;
  card_id: CardId9;
  case_id: CaseId2;
  complaint_risk?: ComplaintRisk;
  external_refs?: ExternalRefs;
  first_seq?: FirstSeq13;
  issue_id?: IssueId14;
  kind: Kind16;
  last_seq?: LastSeq13;
  owner?: Owner;
  priority?: Priority;
  reason: Reason1;
  status: Status8;
  updated_at: UpdatedAt2;
  version: Version8;
}
export interface ExternalRefs {
  [k: string]: string;
}

export type TimelineItem = NonNullable<SessionSnapshot['timeline']>[number];
