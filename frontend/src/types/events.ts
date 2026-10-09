// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.
// Source: contracts/schema/events.schema.json
// SHA-256: 6484013c97bdbb3385bea7ccc4b03d86cc7aed488096043b680e94755a7e3f92

/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ServerEvent".
 */
export type ServerEvent =
  | RunStarted
  | InputReceived
  | IssueChanged
  | PendingChanged
  | SummaryUpdated
  | Ping
  | Progress
  | ToolCall
  | MessageStart
  | Message
  | MessageEnd
  | ProductCard
  | StepCard
  | Evidence
  | ReceiptCard
  | AwaitingInput
  | EscalationSummaryEvent
  | Error
  | Done
  | ProposalCardEvent
  | ExecutionCardEvent
  | RetakeCardEvent
  | RatingCardEvent
  | CaseStatusEvent;
/**
 * 本 run 故障时的最大总时长；前端硬上限 = deadline + 5 s
 */
export type DeadlineMs = number;
export type EventId = string;
export type RecordedAt = string;
export type Resumed = boolean;
export type RunId = string;
/**
 * 会话内单调递增
 */
export type Seq = number;
export type Type = 'run_started';
export type EventId1 = string;
export type InputId = string;
export type InputKind = 'message' | 'action' | 'human_decision';
export type IssueId = string | null;
export type RecordedAt1 = string;
export type RunId1 = string;
/**
 * 会话内单调递增
 */
export type Seq1 = number;
export type Type1 = 'input_received';
export type ActiveIssueId = string;
export type EventId2 = string;
export type InputId1 = string;
export type Issues = {
  [k: string]: unknown;
}[];
export type RecordedAt2 = string;
export type ResolvedIssueId = string;
export type RunId2 = string;
/**
 * 会话内单调递增
 */
export type Seq2 = number;
export type Type2 = 'issue_changed';
export type Version = number;
export type EventId3 = string;
export type IssueId1 = string;
export type PendingId = string;
export type Reason = string;
export type RecordedAt3 = string;
export type RunId3 = string;
/**
 * 会话内单调递增
 */
export type Seq3 = number;
export type Status = 'active' | 'suspended' | 'consumed' | 'invalidated';
export type SupersededBy = string | null;
export type Type3 = 'pending_changed';
export type Version1 = number;
export type CardId = string;
export type EventId4 = string;
export type IssueId2 = string;
export type PreviousCardId = string | null;
export type RecordedAt4 = string;
export type Revision = number;
export type RunId4 = string;
/**
 * 会话内单调递增
 */
export type Seq4 = number;
export type SourceThroughSeq = number;
export type SummaryId = string;
export type Type4 = 'summary_updated';
export type UpdatedAt = string;
export type EventId5 = string;
export type RecordedAt5 = string;
export type RunId5 = string;
/**
 * 会话内单调递增
 */
export type Seq5 = number;
export type Type5 = 'ping';
export type EventId6 = string;
export type RecordedAt6 = string;
export type RunId6 = string;
/**
 * 会话内单调递增
 */
export type Seq6 = number;
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
export type Type6 = 'progress';
export type EventId7 = string;
export type Name = string;
export type RecordedAt7 = string;
export type RunId7 = string;
/**
 * 会话内单调递增
 */
export type Seq7 = number;
export type Status1 = 'started' | 'finished' | 'failed';
export type Summary = string | null;
export type ToolId = string;
export type Type7 = 'tool_call';
export type EventId8 = string;
export type IssueId3 = string | null;
export type MessageId = string;
export type RecordedAt8 = string;
/**
 * 替换先前中断的消息
 */
export type Replaces = string | null;
export type ReplyToInputId = string | null;
export type RunId8 = string;
/**
 * 会话内单调递增
 */
export type Seq8 = number;
export type Type8 = 'message_start';
export type Delta = string;
export type EventId9 = string;
export type MessageId1 = string;
export type RecordedAt9 = string;
export type RunId9 = string;
/**
 * 会话内单调递增
 */
export type Seq9 = number;
export type Type9 = 'message';
export type Citations = string[];
export type EventId10 = string;
export type MessageId2 = string;
export type ModelTier = ('primary' | 'fallback') | null;
export type RecordedAt10 = string;
export type RunId10 = string;
/**
 * 会话内单调递增
 */
export type Seq10 = number;
export type Status2 = 'completed' | 'aborted';
export type Type10 = 'message_end';
export type AllowUnknown = boolean;
/**
 * @minItems 1
 */
export type Candidates = [ProductCandidate, ...ProductCandidate[]];
export type Category = string;
export type Image = string | null;
export type InScope = boolean;
export type Name1 = string;
export type Sku = string;
export type CardId1 = string;
export type EventId11 = string;
export type IssueId4 = string | null;
export type Note = string | null;
export type RecordedAt11 = string;
export type RunId11 = string;
/**
 * 会话内单调递增
 */
export type Seq11 = number;
export type Type11 = 'product_card';
export type Version2 = number;
export type CardId2 = string;
export type EventId12 = string;
export type IssueId5 = string | null;
export type RecordedAt12 = string;
export type RunId12 = string;
export type Seen = string | null;
/**
 * 会话内单调递增
 */
export type Seq12 = number;
export type Caution = string | null;
export type EvidenceIds = string[];
export type ExpectedResult = string;
export type Instruction = string;
export type Kind = 'image' | 'video' | 'link';
export type Url = string;
export type Media = StepMedia[];
export type PlanId = string;
export type PlanVersion = number;
export type PrimaryEvidenceId = string | null;
export type StepId = string;
export type StepNo = number;
export type Title = string;
export type Type12 = 'step_card';
export type Version3 = number;
export type EventId13 = string;
export type ChunkId = string;
export type DocId = string;
export type DocVersion = string;
export type EvidenceId = string;
export type Score = number;
export type Snippet = string;
export type Source = string;
export type Status3 = 'ok' | 'replay';
export type Items = EvidenceItem[];
export type RecordedAt13 = string;
export type RunId13 = string;
/**
 * 会话内单调递增
 */
export type Seq13 = number;
export type Type13 = 'evidence';
export type CardId3 = string;
export type EventId14 = string;
export type Amount = string | null;
export type Country = string | null;
export type OrderNo = string | null;
export type PurchaseDate = string | null;
export type Seller = string | null;
export type IssueId6 = string | null;
export type RecordedAt14 = string;
export type RunId14 = string;
/**
 * 会话内单调递增
 */
export type Seq14 = number;
export type Type14 = 'receipt_card';
export type Unreadable = string[];
export type Version4 = number;
export type CardId4 = string;
export type EventId15 = string;
export type InputToken = string;
export type IssueId7 = string | null;
export type Kind1 =
  | 'select_product'
  | 'step_feedback'
  | 'upload_receipt'
  | 'confirm_receipt'
  | 'confirm_proposal'
  | 'upload_retake'
  | 'rate_satisfaction';
export type RecordedAt15 = string;
export type RunId15 = string;
/**
 * 会话内单调递增
 */
export type Seq15 = number;
export type Type15 = 'awaiting_input';
export type Version5 = number;
export type CardId5 = string;
export type EventId16 = string;
export type HandoffStatus = 'prepared' | 'requested' | 'accepted' | 'failed' | 'cancelled';
export type IssueId8 = string;
export type PreviousCardId1 = string | null;
export type RecordedAt16 = string;
export type Revision1 = number;
export type RunId16 = string;
/**
 * 会话内单调递增
 */
export type Seq16 = number;
export type SourceThroughSeq1 = number;
export type Kind2 =
  'device_fault' | 'order_change' | 'parts_purchase' | 'warranty_review' | 'safety' | 'unknown';
export type Missing = string[];
export type Intent = string;
export type Quote = string;
export type Status4 = string;
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
export type Name2 = string;
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
export type Status5 =
  | 'not_collected'
  | 'insufficient'
  | 'order_verified'
  | 'order_product_mismatch'
  | 'needs_manual_check'
  | 'dealer_authorized'
  | 'dealer_unauthorized';
export type Detail1 = string;
export type OptionId = string;
export type Source1 = 'sop' | 'human';
export type Title1 = string;
export type Type16 = 'replace' | 'refund' | 'reship' | 'carrier_investigation';
export type RecommendedOptions = ProposalOption[];
export type Feedback = 'solved' | 'not_solved' | 'cannot_do';
export type StepId1 = string;
export type Title2 = string;
export type Steps = ExecutedStep[];
export type TaskQueue = {
  [k: string]: unknown;
}[];
export type AsOf = string;
export type Basis = 'order' | 'dealer' | 'none';
export type Country1 = string | null;
export type Dealer = string | null;
export type OrderNo1 = string | null;
export type Reason1 = string;
export type Sku1 = string | null;
export type Status6 = 'in_warranty' | 'out_of_warranty' | 'unauthorized_dealer' | 'unknown';
export type WarrantyEnd = string | null;
export type SummaryId1 = string;
export type Type17 = 'escalation_summary';
export type UpdatedAt1 = string;
export type Code = string;
export type EventId17 = string;
export type Message1 = string;
export type RecordedAt17 = string;
export type Recoverable = boolean;
export type RetryWithSameAction = boolean;
export type RunId17 = string;
/**
 * 会话内单调递增
 */
export type Seq17 = number;
export type Type18 = 'error';
export type EventId18 = string;
export type Reason2 = 'completed' | 'awaiting_input' | 'error' | 'cancelled';
export type RecordedAt18 = string;
export type RunId18 = string;
/**
 * 会话内单调递增
 */
export type Seq18 = number;
export type Type19 = 'done';
/**
 * 本 run 结束后的会话版本
 */
export type Version6 = number;
export type CardId6 = string;
export type DecisionSummary = string;
export type EventId19 = string;
export type IssueId9 = string | null;
export type Options = ProposalOption[];
export type RecordedAt19 = string;
export type Retry = boolean;
export type RunId19 = string;
/**
 * 会话内单调递增
 */
export type Seq19 = number;
export type Type20 = 'proposal_card';
export type Version7 = number;
export type ActionKind = string;
export type CardId7 = string;
export type EventId20 = string;
export type ExecutionId = string;
export type IdempotencyKey = string;
export type IssueId10 = string | null;
export type NextStep1 = string;
export type OrderNo2 = string | null;
export type ServiceOrderNo = string | null;
export type Source2 = string;
export type Status7 = string;
export type TrackingNo = string | null;
export type UpdatedAt2 = string | null;
export type RecordedAt20 = string;
export type RunId20 = string;
/**
 * 会话内单调递增
 */
export type Seq20 = number;
export type Status8 = 'succeeded' | 'failed';
export type Type21 = 'execution_card';
export type Version8 = number;
export type CardId8 = string;
export type EventId21 = string;
export type Guidance = string[];
export type IssueId11 = string | null;
export type Reasons = string[];
export type RecordedAt21 = string;
export type RunId21 = string;
/**
 * 会话内单调递增
 */
export type Seq21 = number;
export type Type22 = 'retake_card';
export type Version9 = number;
export type CardId9 = string;
export type CaseId1 = string | null;
export type EventId22 = string;
export type IssueId12 = string | null;
export type RecordedAt22 = string;
export type RunId22 = string;
/**
 * 会话内单调递增
 */
export type Seq22 = number;
export type Type23 = 'rating_card';
export type Version10 = number;
export type CardId10 = string;
export type CaseId2 = string;
export type ComplaintRisk = boolean;
export type EventId23 = string;
export type IssueId13 = string | null;
export type Owner = string | null;
export type Priority = 'normal' | 'high';
export type Reason3 = string;
export type RecordedAt23 = string;
export type RunId23 = string;
/**
 * 会话内单调递增
 */
export type Seq23 = number;
export type Status9 =
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
export type Type24 = 'case_changed';
export type UpdatedAt3 = string;
export type Version11 = number;
export type ConflictsWithText = string[];
export type ContentKinds = ('fault_photo' | 'document' | 'other')[];
export type Cell =
  ('左上' | '上中' | '右上' | '左中' | '中心' | '右中' | '左下' | '下中' | '右下') | null;
export type Evidence1 = string | null;
export type ImageIndex = number | null;
export type Part = string;
export type Phenomenon = string;
export type Findings = Finding[];
export type Guidance1 = string[];
export type Reasons1 = (
  'blurry' | 'too_dark' | 'too_bright' | 'too_far' | 'wrong_subject' | 'occluded'
)[];
export type Usable = boolean;
export type ModelHint = string | null;
export type ModelHintCell =
  ('左上' | '上中' | '右上' | '左中' | '中心' | '右中' | '左下' | '下中' | '右下') | null;
export type ModelHintImage = number | null;
export type ModelHintReadable = 'full' | 'partial' | 'unreadable';
export type ModelHintVerified = boolean;

export interface ServerEventSchema {
  contract: ServerEvent;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "RunStarted".
 */
export interface RunStarted {
  deadline_ms: DeadlineMs;
  event_id: EventId;
  recorded_at: RecordedAt;
  resumed: Resumed;
  run_id: RunId;
  seq: Seq;
  type: Type;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "InputReceived".
 */
export interface InputReceived {
  event_id: EventId1;
  input_id: InputId;
  input_kind: InputKind;
  issue_id?: IssueId;
  payload: Payload;
  recorded_at: RecordedAt1;
  run_id: RunId1;
  seq: Seq1;
  type: Type1;
}
export interface Payload {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "IssueChanged".
 */
export interface IssueChanged {
  active_issue_id: ActiveIssueId;
  event_id: EventId2;
  input_id: InputId1;
  issues: Issues;
  recorded_at: RecordedAt2;
  resolved_issue_id: ResolvedIssueId;
  run_id: RunId2;
  seq: Seq2;
  type: Type2;
  version: Version;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "PendingChanged".
 */
export interface PendingChanged {
  event_id: EventId3;
  issue_id: IssueId1;
  pending_id: PendingId;
  reason: Reason;
  recorded_at: RecordedAt3;
  run_id: RunId3;
  seq: Seq3;
  status: Status;
  superseded_by?: SupersededBy;
  type: Type3;
  version: Version1;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "SummaryUpdated".
 */
export interface SummaryUpdated {
  card_id: CardId;
  event_id: EventId4;
  issue_id: IssueId2;
  previous_card_id?: PreviousCardId;
  recorded_at: RecordedAt4;
  revision: Revision;
  run_id: RunId4;
  seq: Seq4;
  source_through_seq: SourceThroughSeq;
  summary_id: SummaryId;
  type: Type4;
  updated_at: UpdatedAt;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "Ping".
 */
export interface Ping {
  event_id: EventId5;
  recorded_at: RecordedAt5;
  run_id: RunId5;
  seq: Seq5;
  type: Type5;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "Progress".
 */
export interface Progress {
  event_id: EventId6;
  recorded_at: RecordedAt6;
  run_id: RunId6;
  seq: Seq6;
  stage: Stage;
  substage?: Substage;
  type: Type6;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ToolCall".
 */
export interface ToolCall {
  event_id: EventId7;
  name: Name;
  recorded_at: RecordedAt7;
  run_id: RunId7;
  seq: Seq7;
  status: Status1;
  summary?: Summary;
  tool_id: ToolId;
  type: Type7;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "MessageStart".
 */
export interface MessageStart {
  event_id: EventId8;
  issue_id?: IssueId3;
  message_id: MessageId;
  recorded_at: RecordedAt8;
  replaces?: Replaces;
  reply_to_input_id?: ReplyToInputId;
  run_id: RunId8;
  seq: Seq8;
  type: Type8;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "Message".
 */
export interface Message {
  delta: Delta;
  event_id: EventId9;
  message_id: MessageId1;
  recorded_at: RecordedAt9;
  run_id: RunId9;
  seq: Seq9;
  type: Type9;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "MessageEnd".
 */
export interface MessageEnd {
  citations?: Citations;
  event_id: EventId10;
  message_id: MessageId2;
  model_tier?: ModelTier;
  recorded_at: RecordedAt10;
  run_id: RunId10;
  seq: Seq10;
  status: Status2;
  type: Type10;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ProductCard".
 */
export interface ProductCard {
  allow_unknown?: AllowUnknown;
  candidates: Candidates;
  card_id: CardId1;
  event_id: EventId11;
  issue_id?: IssueId4;
  note?: Note;
  recorded_at: RecordedAt11;
  run_id: RunId11;
  seq: Seq11;
  type: Type11;
  version: Version2;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ProductCandidate".
 */
export interface ProductCandidate {
  category: Category;
  image?: Image;
  in_scope: InScope;
  name: Name1;
  sku: Sku;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "StepCard".
 */
export interface StepCard {
  card_id: CardId2;
  event_id: EventId12;
  issue_id?: IssueId5;
  recorded_at: RecordedAt12;
  run_id: RunId12;
  seen?: Seen;
  seq: Seq12;
  step: TroubleshootStep;
  type: Type12;
  version: Version3;
}
/**
 * step_card 的唯一层级：step 对象（08 §5）。
 *
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
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
  step_id: StepId;
  step_no: StepNo;
  title: Title;
}
/**
 * 官方 Q&A 步骤里附带的图片 / 视频 / 文章链接（原样引用，不进模型上下文）。
 *
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "StepMedia".
 */
export interface StepMedia {
  kind: Kind;
  url: Url;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "Evidence".
 */
export interface Evidence {
  event_id: EventId13;
  items: Items;
  recorded_at: RecordedAt13;
  run_id: RunId13;
  seq: Seq13;
  type: Type13;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "EvidenceItem".
 */
export interface EvidenceItem {
  chunk_id: ChunkId;
  doc_id: DocId;
  doc_version: DocVersion;
  evidence_id: EvidenceId;
  score: Score;
  snippet: Snippet;
  source: Source;
  status?: Status3;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ReceiptCard".
 */
export interface ReceiptCard {
  card_id: CardId3;
  confidence?: Confidence;
  event_id: EventId14;
  fields: ReceiptFields;
  issue_id?: IssueId6;
  recorded_at: RecordedAt14;
  run_id: RunId14;
  seq: Seq14;
  type: Type14;
  unreadable?: Unreadable;
  version: Version4;
}
export interface Confidence {
  [k: string]: number;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ReceiptFields".
 */
export interface ReceiptFields {
  amount?: Amount;
  country?: Country;
  order_no?: OrderNo;
  purchase_date?: PurchaseDate;
  seller?: Seller;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "AwaitingInput".
 */
export interface AwaitingInput {
  card_id: CardId4;
  event_id: EventId15;
  input_token: InputToken;
  issue_id?: IssueId7;
  kind: Kind1;
  recorded_at: RecordedAt15;
  run_id: RunId15;
  seq: Seq15;
  type: Type15;
  version: Version5;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "EscalationSummaryEvent".
 */
export interface EscalationSummaryEvent {
  card_id: CardId5;
  event_id: EventId16;
  handoff_status?: HandoffStatus;
  issue_id: IssueId8;
  previous_card_id?: PreviousCardId1;
  recorded_at: RecordedAt16;
  revision: Revision1;
  run_id: RunId16;
  seq: Seq16;
  source_through_seq: SourceThroughSeq1;
  summary: EscalationSummary;
  summary_id: SummaryId1;
  type: Type17;
  updated_at: UpdatedAt1;
}
/**
 * escalation_summary 的唯一层级：summary 对象（08 §5）。
 *
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
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
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "HandoffBusiness".
 */
export interface HandoffBusiness {
  kind: Kind2;
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
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "PendingRequest".
 */
export interface PendingRequest {
  intent: Intent;
  quote: Quote;
  status: Status4;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "Emotion".
 */
export interface Emotion {
  level: Level;
  strategy: Strategy;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "GateResult".
 */
export interface GateResult {
  checks: Checks;
  fallback?: Fallback;
  passed: Passed1;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "GateCheck".
 */
export interface GateCheck {
  detail: Detail;
  name: Name2;
  passed: Passed;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ModelTraceItem".
 */
export interface ModelTraceItem {
  attempts: Attempts;
  lane: Lane;
  model_used: ModelUsed;
  task: Task;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
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
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ReceiptOutcome".
 */
export interface ReceiptOutcome {
  conflicts?: Conflicts;
  next_step?: NextStep;
  status: Status5;
  verified_facts?: VerifiedFacts;
}
export interface VerifiedFacts {
  [k: string]: string;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ProposalOption".
 */
export interface ProposalOption {
  detail?: Detail1;
  option_id: OptionId;
  source?: Source1;
  title: Title1;
  type: Type16;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ExecutedStep".
 */
export interface ExecutedStep {
  feedback: Feedback;
  step_id: StepId1;
  title: Title2;
}
/**
 * 主办方 SOP「订单质保判断」：有订单看订单质保结束日期；查不到订单看经销商名录（授权 = 购买日起 12 个月）。
 *
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "WarrantyDecision".
 */
export interface WarrantyDecision {
  as_of: AsOf;
  basis: Basis;
  country?: Country1;
  dealer?: Dealer;
  order_no?: OrderNo1;
  reason: Reason1;
  sku?: Sku1;
  status: Status6;
  warranty_end?: WarrantyEnd;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "Error".
 */
export interface Error {
  code: Code;
  event_id: EventId17;
  message: Message1;
  recorded_at: RecordedAt17;
  recoverable: Recoverable;
  retry_with_same_action?: RetryWithSameAction;
  run_id: RunId17;
  seq: Seq17;
  type: Type18;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "Done".
 */
export interface Done {
  event_id: EventId18;
  reason: Reason2;
  recorded_at: RecordedAt18;
  run_id: RunId18;
  seq: Seq18;
  type: Type19;
  version: Version6;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ProposalCardEvent".
 */
export interface ProposalCardEvent {
  card_id: CardId6;
  decision_summary: DecisionSummary;
  event_id: EventId19;
  issue_id?: IssueId9;
  options: Options;
  recorded_at: RecordedAt19;
  retry?: Retry;
  run_id: RunId19;
  seq: Seq19;
  type: Type20;
  version: Version7;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ExecutionCardEvent".
 */
export interface ExecutionCardEvent {
  action_kind: ActionKind;
  card_id: CardId7;
  event_id: EventId20;
  execution_id: ExecutionId;
  idempotency_key: IdempotencyKey;
  issue_id?: IssueId10;
  receipt: Receipt;
  recorded_at: RecordedAt20;
  run_id: RunId20;
  seq: Seq20;
  status: Status8;
  type: Type21;
  version: Version8;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "Receipt".
 */
export interface Receipt {
  data?: Data;
  next_step?: NextStep1;
  order_no?: OrderNo2;
  service_order_no?: ServiceOrderNo;
  source?: Source2;
  status: Status7;
  tracking_no?: TrackingNo;
  updated_at?: UpdatedAt2;
}
export interface Data {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "RetakeCardEvent".
 */
export interface RetakeCardEvent {
  card_id: CardId8;
  event_id: EventId21;
  guidance: Guidance;
  issue_id?: IssueId11;
  reasons: Reasons;
  recorded_at: RecordedAt21;
  run_id: RunId21;
  seq: Seq21;
  type: Type22;
  version: Version9;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "RatingCardEvent".
 */
export interface RatingCardEvent {
  card_id: CardId9;
  case_id?: CaseId1;
  event_id: EventId22;
  issue_id?: IssueId12;
  recorded_at: RecordedAt22;
  run_id: RunId22;
  seq: Seq22;
  type: Type23;
  version: Version10;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "CaseStatusEvent".
 */
export interface CaseStatusEvent {
  card_id: CardId10;
  case_id: CaseId2;
  complaint_risk?: ComplaintRisk;
  event_id: EventId23;
  external_refs?: ExternalRefs;
  issue_id?: IssueId13;
  owner?: Owner;
  priority?: Priority;
  reason: Reason3;
  recorded_at: RecordedAt23;
  run_id: RunId23;
  seq: Seq23;
  status: Status9;
  type: Type24;
  updated_at: UpdatedAt3;
  version: Version11;
}
export interface ExternalRefs {
  [k: string]: string;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "FaultLocalization".
 */
export interface FaultLocalization {
  conflicts_with_text?: ConflictsWithText;
  content_kinds?: ContentKinds;
  findings?: Findings;
  image_quality?: ImageQuality;
  model_hint?: ModelHint;
  model_hint_cell?: ModelHintCell;
  model_hint_image?: ModelHintImage;
  model_hint_readable?: ModelHintReadable;
  model_hint_verified?: ModelHintVerified;
}
/**
 * 一条可见故障结论。字段只保留有下游消费者的：
 * (part, phenomenon) 驱动 signature → plan_id；evidence 是反幻觉锚点；cell 是裁剪复看的坐标。
 * 已移除 severity / location / confidence —— 前两个全仓无消费者，confidence 是模型自评不可用。
 *
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "Finding".
 */
export interface Finding {
  cell?: Cell;
  evidence?: Evidence1;
  image_index?: ImageIndex;
  part: Part;
  phenomenon: Phenomenon;
  raw?: Raw;
}
export interface Raw {
  [k: string]: string;
}
/**
 * This interface was referenced by `ServerEventSchema`'s JSON-Schema
 * via the `definition` "ImageQuality".
 */
export interface ImageQuality {
  guidance?: Guidance1;
  reasons?: Reasons1;
  usable: Usable;
}

export type PendingKind = Extract<ServerEvent, { type: 'awaiting_input' }>['kind'];
