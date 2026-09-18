// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.
// Source: contracts/schema/snapshot.schema.json
// SHA-256: d270e12b39399ec44cd07d0f7706d8cf0c6a76f8f894035d5fd8b71c43aab595

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
export type PolicyDecisionBrief = {
  [k: string]: unknown;
} | null;
export type Problem = string;
export type Product = string;
export type Cause = string | null;
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
export type AutoAllowed = boolean;
export type ClauseId = string;
export type DocVersion = string;
export type PolicyVersion = string;
export type SourceDoc = string;
export type SourceUrl = string | null;
export type Text1 = string;
export type Clauses = Clause[];
export type Met = boolean;
export type Name1 = string;
export type Conditions = PolicyCondition[];
export type CostBearer = ('company' | 'customer' | 'shared') | null;
export type Action = 'replacement.create';
export type ActionsVersion = string;
export type WorkingDays = number;
export type OptionId = string;
export type Remedy = 'parts' | 'repair' | 'replace' | 'refund' | 'paid_repair' | 'none';
export type Source = 'policy' | 'human';
export type Title = string;
export type RecommendedOptions = ProposalOption[];
export type Feedback = 'solved' | 'not_solved' | 'cannot_do';
/**
 * 该步骤记录到的观察结果（选项文字）
 */
export type Observed = string[];
export type StepId = string;
export type Title1 = string;
export type Steps = ExecutedStep[];
export type TaskQueue = {
  [k: string]: unknown;
}[];
export type SummaryId = string;
export type UpdatedAt = string;
export type LatestSummaries = SummaryItem[];
export type CardId1 = string;
export type InputToken = string;
export type IssueId1 = string | null;
export type Kind1 =
  | 'select_product'
  | 'step_feedback'
  | 'answer_observation'
  | 'upload_receipt'
  | 'confirm_receipt'
  | 'confirm_context'
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
export type Kind2 = 'user_message';
export type LastSeq1 = number;
export type Text2 = string;
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
export type Text3 = string;
export type At6 = string | null;
export type FirstSeq4 = number;
export type IssueId5 = string | null;
export type Kind5 = 'tool';
export type LastSeq4 = number;
export type Name2 = string;
export type Status2 = 'started' | 'finished' | 'failed';
export type Summary = string | null;
export type ToolId = string;
export type At7 = string | null;
export type Category = string;
export type Image = string | null;
export type InScope = boolean;
export type Name3 = string;
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
export type ObservationId = string;
export type OptionId1 = string;
export type ObservationAnswers = ObservationAnswer[];
export type Seen = string | null;
export type Caution = string | null;
export type EvidenceIds = string[];
export type ExpectedResult = string;
export type Instruction = string;
export type ObservationId1 = string;
/**
 * @minItems 2
 */
export type Options = [ObservationOption, ObservationOption, ...ObservationOption[]];
export type Kind8 = 'finding' | 'unknown';
export type Label1 = string;
export type OptionId2 = string;
export type Question = string;
export type Observations1 = StepObservation[];
export type PlanId = string;
export type PlanVersion = number;
export type PrimaryEvidenceId = string | null;
export type StepId1 = string;
export type StepNo = number;
export type Title2 = string;
export type Version2 = number;
export type At9 = string | null;
export type Attempt = number;
export type CardId4 = string;
export type ChosenOptionId = string | null;
export type FirstSeq7 = number;
export type IssueId8 = string | null;
export type Kind9 = 'observation_card';
export type LastSeq7 = number;
export type PlanId1 = string;
export type Version3 = number;
export type At10 = string | null;
export type CardId5 = string;
export type Amount = string | null;
export type Channel = string | null;
export type OrderNo = string | null;
export type PurchaseDate = string | null;
export type FirstSeq8 = number;
export type IssueId9 = string | null;
export type Kind10 = 'receipt_card';
export type LastSeq8 = number;
export type SkippedReason = ('none' | 'unreadable' | 'later') | null;
export type Unreadable = string[];
export type Version4 = number;
export type At11 = string | null;
export type FirstSeq9 = number;
export type IssueId10 = string | null;
export type ChunkId = string;
export type DocId = string;
export type DocVersion1 = string;
export type EvidenceId = string;
export type Score = number;
export type Snippet = string;
export type Source1 = string;
export type Status3 = 'ok' | 'replay';
export type Items = EvidenceItem[];
export type Kind11 = 'evidence';
export type LastSeq9 = number;
export type At12 = string | null;
export type CardId6 = string;
export type ConfirmedFields = {
  [k: string]: string;
} | null;
export type Fields = string[];
export type FirstSeq10 = number;
export type IssueId11 = string | null;
export type Kind12 = 'context_card';
export type LastSeq10 = number;
export type Version5 = number;
export type At13 = string | null;
export type CardId7 = string;
export type ChosenOptionId1 = string | null;
export type DecisionSummary = string;
export type DeclinedReason = string | null;
export type FirstSeq11 = number;
export type IssueId12 = string | null;
export type Kind13 = 'proposal_card';
export type LastSeq11 = number;
export type Options1 = ProposalOption[];
export type PolicyVersion1 = string;
export type Retry = boolean;
export type Version6 = number;
export type ActionKind1 = string;
export type At14 = string | null;
export type CardId8 = string;
export type ExecutionId = string;
export type FirstSeq12 = number;
export type IdempotencyKey = string;
export type IssueId13 = string | null;
export type Kind14 = 'execution_card';
export type LastSeq12 = number;
export type EtaDays = number | null;
export type NextStep1 = string;
export type OrderNo1 = string | null;
export type ServiceOrderNo = string | null;
export type Source2 = string;
export type Status4 = string;
export type TrackingNo = string | null;
export type UpdatedAt1 = string | null;
export type Status5 = 'succeeded' | 'failed';
export type Version7 = number;
export type At15 = string | null;
export type CardId9 = string;
export type FirstSeq13 = number;
export type Guidance = string[];
export type IssueId14 = string | null;
export type Kind15 = 'retake_card';
export type LastSeq13 = number;
export type Reasons = string[];
export type Skipped = boolean;
export type Version8 = number;
export type At16 = string | null;
export type CardId10 = string;
export type CaseId1 = string | null;
export type FirstSeq14 = number;
export type IssueId15 = string | null;
export type Kind16 = 'rating_card';
export type LastSeq14 = number;
export type Score1 = number | null;
export type Version9 = number;
export type At17 = string | null;
export type CardId11 = string;
export type CaseId2 = string;
export type ComplaintRisk = boolean;
export type FirstSeq15 = number;
export type IssueId16 = string | null;
export type Kind17 = 'case_changed';
export type LastSeq15 = number;
export type Owner = string | null;
export type Priority = 'normal' | 'high';
export type Reason = string;
export type Status6 =
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
export type Version10 = number;
export type Timeline = (
  | UserMessageItem
  | ActionItem
  | AssistantMessageItem
  | ToolItem
  | ProductCardItem
  | StepCardItem
  | ObservationCardItem
  | ReceiptCardItem
  | EvidenceItemGroup
  | SummaryItem
  | ContextCardItem
  | ProposalCardItem
  | ExecutionCardItem
  | RetakeCardItem
  | RatingCardItem
  | CaseStatusItem
)[];
export type Version11 = number;

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
  version: Version11;
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
  case_id?: CaseId;
  draft_reply?: DraftReply;
  emotion: Emotion;
  emotion_track?: EmotionTrack;
  gate_result?: GateResult | null;
  hypotheses?: Hypotheses;
  model_trace?: ModelTrace;
  observations?: Observations;
  policy_decision_brief?: PolicyDecisionBrief;
  problem: Problem;
  product: Product;
  reason: EscalationReason;
  receipt: ReceiptOutcome;
  recommended_options?: RecommendedOptions;
  steps?: Steps;
  task_queue?: TaskQueue;
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
  status: Status;
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
  auto_allowed?: AutoAllowed;
  clauses?: Clauses;
  conditions?: Conditions;
  cost_bearer?: CostBearer;
  dispatch_estimate?: DispatchEstimate | null;
  option_id: OptionId;
  remedy: Remedy;
  source?: Source;
  title: Title;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "Clause".
 */
export interface Clause {
  clause_id: ClauseId;
  doc_version: DocVersion;
  policy_version: PolicyVersion;
  source_doc: SourceDoc;
  source_url?: SourceUrl;
  text: Text1;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "PolicyCondition".
 */
export interface PolicyCondition {
  actual: Actual;
  expected: Expected;
  met: Met;
  name: Name1;
}
export interface Actual {
  [k: string]: unknown;
}
export interface Expected {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "DispatchEstimate".
 */
export interface DispatchEstimate {
  action?: Action;
  actions_version: ActionsVersion;
  working_days: WorkingDays;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ExecutedStep".
 */
export interface ExecutedStep {
  feedback: Feedback;
  observed?: Observed;
  step_id: StepId;
  title: Title1;
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
  text: Text2;
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
  text: Text3;
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
  name: Name2;
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
  name: Name3;
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
  observation_answers?: ObservationAnswers;
  seen?: Seen;
  step: TroubleshootStep;
  version: Version2;
}
/**
 * 用户对某个步骤观察的选择；option_id 必须是该步骤声明过的选项。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ObservationAnswer".
 */
export interface ObservationAnswer {
  observation_id: ObservationId;
  option_id: OptionId1;
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
  observations?: Observations1;
  plan_id: PlanId;
  plan_version: PlanVersion;
  primary_evidence_id?: PrimaryEvidenceId;
  step_id: StepId1;
  step_no: StepNo;
  title: Title2;
}
/**
 * 步骤要收集的检查结果：一个问题与有限选项。功能是否恢复仍由 feedback 三态表达。
 *
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "StepObservation".
 */
export interface StepObservation {
  observation_id: ObservationId1;
  options: Options;
  question: Question;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ObservationOption".
 */
export interface ObservationOption {
  kind?: Kind8;
  label: Label1;
  option_id: OptionId2;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ObservationCardItem".
 */
export interface ObservationCardItem {
  at?: At9;
  attempt: Attempt;
  card_id: CardId4;
  chosen_option_id?: ChosenOptionId;
  first_seq?: FirstSeq7;
  issue_id?: IssueId8;
  kind: Kind9;
  last_seq?: LastSeq7;
  observation: StepObservation;
  plan_id: PlanId1;
  version: Version3;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ReceiptCardItem".
 */
export interface ReceiptCardItem {
  at?: At10;
  card_id: CardId5;
  confidence?: Confidence;
  confirmed_fields?: ReceiptFields | null;
  fields: ReceiptFields;
  first_seq?: FirstSeq8;
  issue_id?: IssueId9;
  kind: Kind10;
  last_seq?: LastSeq8;
  skipped_reason?: SkippedReason;
  unreadable?: Unreadable;
  version: Version4;
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
  at?: At11;
  first_seq?: FirstSeq9;
  issue_id?: IssueId10;
  items: Items;
  kind: Kind11;
  last_seq?: LastSeq9;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "EvidenceItem".
 */
export interface EvidenceItem {
  chunk_id: ChunkId;
  doc_id: DocId;
  doc_version: DocVersion1;
  evidence_id: EvidenceId;
  score: Score;
  snippet: Snippet;
  source: Source1;
  status?: Status3;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ContextCardItem".
 */
export interface ContextCardItem {
  at?: At12;
  card_id: CardId6;
  choices?: Choices;
  confirmed_fields?: ConfirmedFields;
  fields: Fields;
  first_seq?: FirstSeq10;
  issue_id?: IssueId11;
  kind: Kind12;
  last_seq?: LastSeq10;
  prefilled?: Prefilled;
  sources?: Sources;
  version: Version5;
}
export interface Choices {
  [k: string]: string[];
}
export interface Prefilled {
  [k: string]: string;
}
export interface Sources {
  [k: string]: string;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ProposalCardItem".
 */
export interface ProposalCardItem {
  at?: At13;
  card_id: CardId7;
  chosen_option_id?: ChosenOptionId1;
  decision_summary: DecisionSummary;
  declined_reason?: DeclinedReason;
  first_seq?: FirstSeq11;
  issue_id?: IssueId12;
  kind: Kind13;
  last_seq?: LastSeq11;
  options: Options1;
  policy_version: PolicyVersion1;
  retry?: Retry;
  version: Version6;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "ExecutionCardItem".
 */
export interface ExecutionCardItem {
  action_kind: ActionKind1;
  at?: At14;
  card_id: CardId8;
  execution_id: ExecutionId;
  first_seq?: FirstSeq12;
  idempotency_key: IdempotencyKey;
  issue_id?: IssueId13;
  kind: Kind14;
  last_seq?: LastSeq12;
  receipt: Receipt;
  status: Status5;
  version: Version7;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "Receipt".
 */
export interface Receipt {
  data?: Data;
  eta_days?: EtaDays;
  next_step?: NextStep1;
  order_no?: OrderNo1;
  service_order_no?: ServiceOrderNo;
  source?: Source2;
  status: Status4;
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
  at?: At15;
  card_id: CardId9;
  first_seq?: FirstSeq13;
  guidance: Guidance;
  issue_id?: IssueId14;
  kind: Kind15;
  last_seq?: LastSeq13;
  reasons: Reasons;
  skipped?: Skipped;
  version: Version8;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "RatingCardItem".
 */
export interface RatingCardItem {
  at?: At16;
  card_id: CardId10;
  case_id?: CaseId1;
  first_seq?: FirstSeq14;
  issue_id?: IssueId15;
  kind: Kind16;
  last_seq?: LastSeq14;
  score?: Score1;
  version: Version9;
}
/**
 * This interface was referenced by `SessionSnapshotSchema`'s JSON-Schema
 * via the `definition` "CaseStatusItem".
 */
export interface CaseStatusItem {
  at?: At17;
  card_id: CardId11;
  case_id: CaseId2;
  complaint_risk?: ComplaintRisk;
  external_refs?: ExternalRefs;
  first_seq?: FirstSeq15;
  issue_id?: IssueId16;
  kind: Kind17;
  last_seq?: LastSeq15;
  owner?: Owner;
  priority?: Priority;
  reason: Reason;
  status: Status6;
  updated_at: UpdatedAt2;
  version: Version10;
}
export interface ExternalRefs {
  [k: string]: string;
}

export type TimelineItem = NonNullable<SessionSnapshot['timeline']>[number];
