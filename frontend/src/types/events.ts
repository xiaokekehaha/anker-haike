// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.
// Source: contracts/schema/events.schema.json
// SHA-256: fbe7af9cc58280c64bbd71266a0e3b0e8cee1ede7f5c834ee05877d2f27ad7ac

export type ServerEvent =
  | RunStarted
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
  | Done;
/**
 * 本 run 故障时的最大总时长；前端硬上限 = deadline + 5 s
 */
export type DeadlineMs = number;
export type Resumed = boolean;
export type RunId = string;
/**
 * 会话内单调递增
 */
export type Seq = number;
export type Type = 'run_started';
export type RunId1 = string;
/**
 * 会话内单调递增
 */
export type Seq1 = number;
export type Type1 = 'ping';
export type RunId2 = string;
/**
 * 会话内单调递增
 */
export type Seq2 = number;
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
export type Type2 = 'progress';
export type Name = string;
export type RunId3 = string;
/**
 * 会话内单调递增
 */
export type Seq3 = number;
export type Status = 'started' | 'finished' | 'failed';
export type Summary = string | null;
export type ToolId = string;
export type Type3 = 'tool_call';
export type MessageId = string;
/**
 * 替换先前中断的消息
 */
export type Replaces = string | null;
export type RunId4 = string;
/**
 * 会话内单调递增
 */
export type Seq4 = number;
export type Type4 = 'message_start';
export type Delta = string;
export type MessageId1 = string;
export type RunId5 = string;
/**
 * 会话内单调递增
 */
export type Seq5 = number;
export type Type5 = 'message';
export type MessageId2 = string;
export type ModelTier = ('primary' | 'fallback') | null;
export type RunId6 = string;
/**
 * 会话内单调递增
 */
export type Seq6 = number;
export type Status1 = 'completed' | 'aborted';
export type Type6 = 'message_end';
/**
 * @minItems 1
 */
export type Candidates = [ProductCandidate, ...ProductCandidate[]];
export type Category = string;
export type Image = string | null;
export type InScope = boolean;
export type Name1 = string;
export type Sku = string;
export type CardId = string;
export type RunId7 = string;
/**
 * 会话内单调递增
 */
export type Seq7 = number;
export type Type7 = 'product_card';
export type Version = number;
export type CardId1 = string;
export type RunId8 = string;
/**
 * 会话内单调递增
 */
export type Seq8 = number;
export type Caution = string | null;
export type EvidenceIds = string[];
export type ExpectedResult = string;
export type Instruction = string;
export type PlanId = string;
export type PlanVersion = number;
export type StepId = string;
export type StepNo = number;
export type Title = string;
export type Type8 = 'step_card';
export type Version1 = number;
export type ChunkId = string;
export type DocId = string;
export type DocVersion = string;
export type EvidenceId = string;
export type Score = number;
export type Snippet = string;
export type Source = string;
export type Status2 = 'ok' | 'replay';
export type Items = EvidenceItem[];
export type RunId9 = string;
/**
 * 会话内单调递增
 */
export type Seq9 = number;
export type Type9 = 'evidence';
export type CardId2 = string;
export type Amount = string | null;
export type Channel = string | null;
export type OrderNo = string | null;
export type PurchaseDate = string | null;
export type RunId10 = string;
/**
 * 会话内单调递增
 */
export type Seq10 = number;
export type Type10 = 'receipt_card';
export type Unreadable = string[];
export type Version2 = number;
export type CardId3 = string;
export type InterruptId = string;
export type Kind = 'select_product' | 'step_feedback' | 'upload_receipt' | 'confirm_receipt';
export type RunId11 = string;
/**
 * 会话内单调递增
 */
export type Seq11 = number;
export type Type11 = 'awaiting_input';
export type Version3 = number;
export type CardId4 = string;
export type RunId12 = string;
/**
 * 会话内单调递增
 */
export type Seq12 = number;
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
export type Status3 =
  | 'not_collected'
  | 'insufficient'
  | 'order_verified'
  | 'order_product_mismatch'
  | 'needs_manual_check'
  | 'channel_in_directory'
  | 'channel_unknown';
export type Feedback = 'solved' | 'not_solved' | 'cannot_do';
export type StepId1 = string;
export type Title1 = string;
export type Steps = ExecutedStep[];
export type Type12 = 'escalation_summary';
export type Code = string;
export type Message1 = string;
export type Recoverable = boolean;
export type RetryWithSameAction = boolean;
export type RunId13 = string;
/**
 * 会话内单调递增
 */
export type Seq13 = number;
export type Type13 = 'error';
export type Reason = 'completed' | 'awaiting_input' | 'error' | 'cancelled';
export type RunId14 = string;
/**
 * 会话内单调递增
 */
export type Seq14 = number;
export type Type14 = 'done';
/**
 * 本 run 结束后的会话版本
 */
export type Version4 = number;

export interface RunStarted {
  deadline_ms: DeadlineMs;
  resumed: Resumed;
  run_id: RunId;
  seq: Seq;
  type: Type;
}
export interface Ping {
  run_id: RunId1;
  seq: Seq1;
  type: Type1;
}
export interface Progress {
  run_id: RunId2;
  seq: Seq2;
  stage: Stage;
  substage?: Substage;
  type: Type2;
}
export interface ToolCall {
  name: Name;
  run_id: RunId3;
  seq: Seq3;
  status: Status;
  summary?: Summary;
  tool_id: ToolId;
  type: Type3;
}
export interface MessageStart {
  message_id: MessageId;
  replaces?: Replaces;
  run_id: RunId4;
  seq: Seq4;
  type: Type4;
}
export interface Message {
  delta: Delta;
  message_id: MessageId1;
  run_id: RunId5;
  seq: Seq5;
  type: Type5;
}
export interface MessageEnd {
  message_id: MessageId2;
  model_tier?: ModelTier;
  run_id: RunId6;
  seq: Seq6;
  status: Status1;
  type: Type6;
}
export interface ProductCard {
  candidates: Candidates;
  card_id: CardId;
  run_id: RunId7;
  seq: Seq7;
  type: Type7;
  version: Version;
}
export interface ProductCandidate {
  category: Category;
  image?: Image;
  in_scope: InScope;
  name: Name1;
  sku: Sku;
}
export interface StepCard {
  card_id: CardId1;
  run_id: RunId8;
  seq: Seq8;
  step: TroubleshootStep;
  type: Type8;
  version: Version1;
}
/**
 * step_card 的唯一层级：step 对象（08 §5）。
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
export interface Evidence {
  items: Items;
  run_id: RunId9;
  seq: Seq9;
  type: Type9;
}
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
export interface ReceiptCard {
  card_id: CardId2;
  confidence?: Confidence;
  fields: ReceiptFields;
  run_id: RunId10;
  seq: Seq10;
  type: Type10;
  unreadable?: Unreadable;
  version: Version2;
}
export interface Confidence {
  [k: string]: number;
}
export interface ReceiptFields {
  amount?: Amount;
  channel?: Channel;
  order_no?: OrderNo;
  purchase_date?: PurchaseDate;
}
export interface AwaitingInput {
  card_id: CardId3;
  interrupt_id: InterruptId;
  kind: Kind;
  run_id: RunId11;
  seq: Seq11;
  type: Type11;
  version: Version3;
}
export interface EscalationSummaryEvent {
  card_id: CardId4;
  run_id: RunId12;
  seq: Seq12;
  summary: EscalationSummary;
  type: Type12;
}
/**
 * escalation_summary 的唯一层级：summary 对象（08 §5）。
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
export interface Emotion {
  level: Level;
  strategy: Strategy;
}
export interface ModelTraceItem {
  attempts: Attempts;
  lane: Lane;
  model_used: ModelUsed;
  task: Task;
}
export interface EscalationReason {
  rule_id: RuleId;
  text: Text;
}
/**
 * 凭证核对结果：只有已核实事实与下一步，不含质保资格结论（D16，09 §5.2）。
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
export interface ExecutedStep {
  feedback: Feedback;
  step_id: StepId1;
  title: Title1;
}
export interface Error {
  code: Code;
  message: Message1;
  recoverable: Recoverable;
  retry_with_same_action?: RetryWithSameAction;
  run_id: RunId13;
  seq: Seq13;
  type: Type13;
}
export interface Done {
  reason: Reason;
  run_id: RunId14;
  seq: Seq14;
  type: Type14;
  version: Version4;
}

export type PendingKind = Extract<ServerEvent, { type: 'awaiting_input' }>['kind'];
