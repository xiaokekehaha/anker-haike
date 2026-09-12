// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.
// Source: contracts/schema/snapshot.schema.json
// SHA-256: 56a70111a027ceb717b14b94a4f15ea6560a2924c0ad42035ea5e9a63d064ff3

export type DeadlineAt = string;
export type RunId = string;
export type StartedAt = string;
export type At = string;
export type RunId1 = string;
export type At1 = string;
export type Code = string;
export type CardId = string;
export type InterruptId = string;
export type Kind = 'select_product' | 'step_feedback' | 'upload_receipt' | 'confirm_receipt';
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
  | 'done';
export type Substage = string | null;
export type At2 = string;
export type Id = string;
export type ImageIds = string[];
export type Kind1 = 'user_message';
export type Text = string;
export type Kind2 = 'assistant_message';
export type MessageId = string;
export type ModelTier = ('primary' | 'fallback') | null;
export type Replaces = string | null;
export type Status = 'completed' | 'aborted' | 'streaming';
export type Text1 = string;
export type Kind3 = 'tool';
export type Name = string;
export type Status1 = 'started' | 'finished' | 'failed';
export type Summary = string | null;
export type ToolId = string;
export type Category = string;
export type Image = string | null;
export type InScope = boolean;
export type Name1 = string;
export type Sku = string;
export type Candidates = ProductCandidate[];
export type CardId1 = string;
export type Kind4 = 'product_card';
/**
 * 用户已选结果
 */
export type SelectedSku = string | null;
export type Version1 = number;
export type CardId2 = string;
export type Feedback = ('solved' | 'not_solved' | 'cannot_do') | null;
export type Kind5 = 'step_card';
export type Note = string | null;
export type Caution = string | null;
export type EvidenceIds = string[];
export type ExpectedResult = string;
export type Instruction = string;
export type PlanId = string;
export type PlanVersion = number;
export type StepId = string;
export type StepNo = number;
export type Title = string;
export type Version2 = number;
export type CardId3 = string;
export type Amount = string | null;
export type Channel = string | null;
export type OrderNo = string | null;
export type PurchaseDate = string | null;
export type Kind6 = 'receipt_card';
export type SkippedReason = ('none' | 'unreadable' | 'later') | null;
export type Unreadable = string[];
export type Version3 = number;
export type ChunkId = string;
export type DocId = string;
export type DocVersion = string;
export type EvidenceId = string;
export type Score = number;
export type Snippet = string;
export type Source = string;
export type Status2 = 'ok' | 'replay';
export type Items = EvidenceItem[];
export type Kind7 = 'evidence';
export type CardId4 = string;
export type Kind8 = 'escalation_summary';
export type Level = 'calm' | 'anxious' | 'angry';
export type Strategy = 'normal' | 'reassure_first' | 'reassure_and_shorten';
export type Hypotheses = string[];
export type Attempts = number;
export type Lane = string;
export type ModelUsed = string;
export type Task = string;
export type ModelTrace = ModelTraceItem[];
export type Observations = string[];
export type Problem = string;
export type Product = string;
export type RuleId = string;
export type Text2 = string;
export type Conflicts = string[];
export type NextStep = string | null;
export type Status3 =
  | 'not_collected'
  | 'insufficient'
  | 'order_verified'
  | 'order_product_mismatch'
  | 'needs_manual_check'
  | 'channel_in_directory'
  | 'channel_unknown';
export type Feedback1 = 'solved' | 'not_solved' | 'cannot_do';
export type StepId1 = string;
export type Title1 = string;
export type Steps = ExecutedStep[];
export type Timeline = (
  | UserMessageItem
  | AssistantMessageItem
  | ToolItem
  | ProductCardItem
  | StepCardItem
  | ReceiptCardItem
  | EvidenceItemGroup
  | SummaryItem
)[];
export type Version4 = number;

export interface SessionSnapshot {
  active_run?: ActiveRun | null;
  cancelled_run?: CancelledRun | null;
  last_error?: LastError | null;
  pending_input?: PendingInput | null;
  session_id: SessionId;
  stage: Stage;
  substage?: Substage;
  timeline?: Timeline;
  version: Version4;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "ActiveRun".
 */
export interface ActiveRun {
  deadline_at: DeadlineAt;
  run_id: RunId;
  started_at: StartedAt;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "CancelledRun".
 */
export interface CancelledRun {
  at: At;
  run_id: RunId1;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "LastError".
 */
export interface LastError {
  at: At1;
  code: Code;
}
/**
 * 当前唯一允许的用户输入；与 awaiting_input 事件同结构（08 §1、§6）。
 *
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "PendingInput".
 */
export interface PendingInput {
  card_id: CardId;
  interrupt_id: InterruptId;
  kind: Kind;
  version: Version;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "UserMessageItem".
 */
export interface UserMessageItem {
  at: At2;
  id: Id;
  image_ids?: ImageIds;
  kind: Kind1;
  text: Text;
}
/**
 * message_start / message / message_end 折叠后的完整文本。
 *
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "AssistantMessageItem".
 */
export interface AssistantMessageItem {
  kind: Kind2;
  message_id: MessageId;
  model_tier?: ModelTier;
  replaces?: Replaces;
  status: Status;
  text: Text1;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "ToolItem".
 */
export interface ToolItem {
  kind: Kind3;
  name: Name;
  status: Status1;
  summary?: Summary;
  tool_id: ToolId;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "ProductCardItem".
 */
export interface ProductCardItem {
  candidates: Candidates;
  card_id: CardId1;
  kind: Kind4;
  selected_sku?: SelectedSku;
  version: Version1;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
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
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "StepCardItem".
 */
export interface StepCardItem {
  card_id: CardId2;
  feedback?: Feedback;
  kind: Kind5;
  note?: Note;
  step: TroubleshootStep;
  version: Version2;
}
/**
 * step_card 的唯一层级：step 对象（08 §5）。
 *
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "TroubleshootStep".
 */
export interface TroubleshootStep {
  caution?: Caution;
  evidence_ids?: EvidenceIds;
  expected_result: ExpectedResult;
  instruction: Instruction;
  plan_id: PlanId;
  plan_version: PlanVersion;
  step_id: StepId;
  step_no: StepNo;
  title: Title;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "ReceiptCardItem".
 */
export interface ReceiptCardItem {
  card_id: CardId3;
  confidence?: Confidence;
  confirmed_fields?: ReceiptFields | null;
  fields: ReceiptFields;
  kind: Kind6;
  skipped_reason?: SkippedReason;
  unreadable?: Unreadable;
  version: Version3;
}
export interface Confidence {
  [k: string]: number;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "ReceiptFields".
 */
export interface ReceiptFields {
  amount?: Amount;
  channel?: Channel;
  order_no?: OrderNo;
  purchase_date?: PurchaseDate;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "EvidenceItemGroup".
 */
export interface EvidenceItemGroup {
  items: Items;
  kind: Kind7;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
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
  status?: Status2;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "SummaryItem".
 */
export interface SummaryItem {
  card_id: CardId4;
  kind: Kind8;
  summary: EscalationSummary;
}
/**
 * escalation_summary 的唯一层级：summary 对象（08 §5）。
 *
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "EscalationSummary".
 */
export interface EscalationSummary {
  emotion: Emotion;
  hypotheses?: Hypotheses;
  model_trace?: ModelTrace;
  observations?: Observations;
  problem: Problem;
  product: Product;
  reason: EscalationReason;
  receipt: ReceiptOutcome;
  steps?: Steps;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "Emotion".
 */
export interface Emotion {
  level: Level;
  strategy: Strategy;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "ModelTraceItem".
 */
export interface ModelTraceItem {
  attempts: Attempts;
  lane: Lane;
  model_used: ModelUsed;
  task: Task;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "EscalationReason".
 */
export interface EscalationReason {
  rule_id: RuleId;
  text: Text2;
}
/**
 * 凭证核对结果：只有已核实事实与下一步，不含质保资格结论（D16，09 §5.2）。
 *
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "ReceiptOutcome".
 */
export interface ReceiptOutcome {
  conflicts?: Conflicts;
  next_step?: NextStep;
  status: Status3;
  verified_facts?: VerifiedFacts;
}
export interface VerifiedFacts {
  [k: string]: string;
}
/**
 * This interface was referenced by `SessionSnapshot`'s JSON-Schema
 * via the `definition` "ExecutedStep".
 */
export interface ExecutedStep {
  feedback: Feedback1;
  step_id: StepId1;
  title: Title1;
}

export type TimelineItem = NonNullable<SessionSnapshot['timeline']>[number];
