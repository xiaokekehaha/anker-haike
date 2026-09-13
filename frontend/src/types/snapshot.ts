// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.
// Source: contracts/schema/snapshot.schema.json
// SHA-256: c56aaeea8f0de25c56f22e1d7f18e704592ea959e3485c47dc9adfecd0ca5d97

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
export type Text = string;
export type Conflicts = string[];
export type NextStep = string | null;
export type Status =
  | 'not_collected'
  | 'insufficient'
  | 'order_verified'
  | 'order_product_mismatch'
  | 'needs_manual_check'
  | 'channel_in_directory'
  | 'channel_unknown';
export type Feedback = 'solved' | 'not_solved' | 'cannot_do';
export type StepId = string;
export type Title = string;
export type Steps = ExecutedStep[];
export type SummaryId = string;
export type UpdatedAt = string;
export type LatestSummaries = SummaryItem[];
export type CardId1 = string;
export type InputToken = string;
export type IssueId1 = string | null;
export type Kind1 = 'select_product' | 'step_feedback' | 'upload_receipt' | 'confirm_receipt';
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
export type Kind2 = 'user_message';
export type LastSeq1 = number;
export type Text1 = string;
export type ActionKind = string;
export type At4 = string | null;
export type FirstSeq2 = number;
export type Id1 = string;
export type IssueId3 = string | null;
export type Kind3 = 'action';
export type Label = string;
export type LastSeq2 = number;
export type At5 = string | null;
export type FirstSeq3 = number;
export type IssueId4 = string | null;
export type Kind4 = 'assistant_message';
export type LastSeq3 = number;
export type MessageId = string;
export type ModelTier = ('primary' | 'fallback') | null;
export type Replaces = string | null;
export type ReplyToInputId = string | null;
export type Status1 = 'completed' | 'aborted' | 'streaming' | 'replaced';
export type Text2 = string;
export type At6 = string | null;
export type FirstSeq4 = number;
export type IssueId5 = string | null;
export type Kind5 = 'tool';
export type LastSeq4 = number;
export type Name = string;
export type Status2 = 'started' | 'finished' | 'failed';
export type Summary = string | null;
export type ToolId = string;
export type At7 = string | null;
export type Category = string;
export type Image = string | null;
export type InScope = boolean;
export type Name1 = string;
export type Sku = string;
export type Candidates = ProductCandidate[];
export type CardId2 = string;
export type FirstSeq5 = number;
export type IssueId6 = string | null;
export type Kind6 = 'product_card';
export type LastSeq5 = number;
/**
 * 用户已选结果
 */
export type SelectedSku = string | null;
export type Version1 = number;
export type At8 = string | null;
export type CardId3 = string;
export type Feedback1 = ('solved' | 'not_solved' | 'cannot_do') | null;
export type FirstSeq6 = number;
export type IssueId7 = string | null;
export type Kind7 = 'step_card';
export type LastSeq6 = number;
export type Note = string | null;
export type Caution = string | null;
export type EvidenceIds = string[];
export type ExpectedResult = string;
export type Instruction = string;
export type PlanId = string;
export type PlanVersion = number;
export type StepId1 = string;
export type StepNo = number;
export type Title1 = string;
export type Version2 = number;
export type At9 = string | null;
export type CardId4 = string;
export type Amount = string | null;
export type Channel = string | null;
export type OrderNo = string | null;
export type PurchaseDate = string | null;
export type FirstSeq7 = number;
export type IssueId8 = string | null;
export type Kind8 = 'receipt_card';
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
export type Source = string;
export type Status3 = 'ok' | 'replay';
export type Items = EvidenceItem[];
export type Kind9 = 'evidence';
export type LastSeq8 = number;
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
)[];
export type Version4 = number;

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
  version: Version4;
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
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "Emotion".
 */
export interface Emotion {
  level: Level;
  strategy: Strategy;
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
  status: Status;
  verified_facts?: VerifiedFacts;
}
export interface VerifiedFacts {
  [k: string]: string;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ExecutedStep".
 */
export interface ExecutedStep {
  feedback: Feedback;
  step_id: StepId;
  title: Title;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "PendingInput".
 */
export interface PendingInput {
  card_id: CardId1;
  input_token: InputToken;
  issue_id?: IssueId1;
  kind: Kind1;
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
  kind: Kind2;
  last_seq?: LastSeq1;
  text: Text1;
}
/**
 * 会话期图片引用（票 29）：只有引用与摘要，字节在 session_images，1 小时后清理。
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
  kind: Kind3;
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
  kind: Kind4;
  last_seq?: LastSeq3;
  message_id: MessageId;
  model_tier?: ModelTier;
  replaces?: Replaces;
  reply_to_input_id?: ReplyToInputId;
  status: Status1;
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
  kind: Kind5;
  last_seq?: LastSeq4;
  name: Name;
  status: Status2;
  summary?: Summary;
  tool_id: ToolId;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ProductCardItem".
 */
export interface ProductCardItem {
  at?: At7;
  candidates: Candidates;
  card_id: CardId2;
  first_seq?: FirstSeq5;
  issue_id?: IssueId6;
  kind: Kind6;
  last_seq?: LastSeq5;
  selected_sku?: SelectedSku;
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
  name: Name1;
  sku: Sku;
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
  kind: Kind7;
  last_seq?: LastSeq6;
  note?: Note;
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
  plan_id: PlanId;
  plan_version: PlanVersion;
  step_id: StepId1;
  step_no: StepNo;
  title: Title1;
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
  kind: Kind8;
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
  channel?: Channel;
  order_no?: OrderNo;
  purchase_date?: PurchaseDate;
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
  kind: Kind9;
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
  source: Source;
  status?: Status3;
}

export type TimelineItem = NonNullable<SessionSnapshot['timeline']>[number];
