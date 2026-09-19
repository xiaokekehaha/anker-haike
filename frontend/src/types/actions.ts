// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.
// Source: contracts/schema/actions.schema.json
// SHA-256: 0a3742e14a8fc23086f7946fb5397bbeb8ca6e90dfc7a6133fcbb3ba88f4db86

/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ActionRequest".
 */
export type ActionRequest =
  | SelectProductAction
  | StepFeedbackAction
  | AnswerObservationAction
  | ConfirmReceiptAction
  | SkipReceiptAction
  | RequestHumanAction
  | NewIssueAction
  | ResumeIssueAction
  | ConfirmContextAction
  | ConfirmProposalAction
  | DeclineProposalAction
  | SkipRetakeAction
  | RateSatisfactionAction;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId = string;
export type CardId = string;
export type ExpectedVersion = number;
export type InputToken = string;
export type Kind = 'select_product';
export type Sku = string | null;
export type TargetIssueId = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId1 = string;
export type CardId1 = string;
export type ExpectedVersion1 = number;
export type InputToken1 = string;
export type Kind1 = 'step_feedback';
export type Feedback = 'solved' | 'not_solved' | 'cannot_do';
export type Note = string | null;
export type ObservationId = string;
export type OptionId = string;
export type Observations = ObservationAnswer[];
export type TargetIssueId1 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId2 = string;
export type CardId2 = string;
export type ExpectedVersion2 = number;
export type InputToken2 = string;
export type Kind2 = 'answer_observation';
export type ObservationId1 = string;
export type OptionId1 = string;
export type TargetIssueId2 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId3 = string;
export type CardId3 = string;
export type ExpectedVersion3 = number;
export type InputToken3 = string;
export type Kind3 = 'confirm_receipt';
export type Edited = ('order_no' | 'channel' | 'purchase_date' | 'amount')[];
export type Amount = string | null;
export type Channel = string | null;
export type OrderNo = string | null;
export type PurchaseDate = string | null;
export type TargetIssueId3 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId4 = string;
export type CardId4 = string;
export type ExpectedVersion4 = number;
export type InputToken4 = string;
export type Kind4 = 'skip_receipt';
export type Reason = 'none' | 'unreadable' | 'later';
export type TargetIssueId4 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId5 = string;
export type CardId5 = string | null;
export type ExpectedVersion5 = number;
export type InputToken5 = string | null;
export type Kind5 = 'request_human';
export type TargetIssueId5 = string | null;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId6 = string;
export type ExpectedVersion6 = number;
export type Kind6 = 'new_issue';
export type TargetIssueId6 = null;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId7 = string;
export type ExpectedVersion7 = number;
export type Kind7 = 'resume_issue';
export type TargetIssueId7 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId8 = string;
export type CardId6 = string;
export type ExpectedVersion8 = number;
export type InputToken6 = string;
export type Kind8 = 'confirm_context';
export type Channel1 = string;
export type Platform = string | null;
export type RegionPurchase = string;
export type RegionUse = string;
export type TargetIssueId8 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId9 = string;
export type CardId7 = string;
export type ExpectedVersion9 = number;
export type InputToken7 = string;
export type Kind9 = 'confirm_proposal';
export type OptionId2 = string;
export type TargetIssueId9 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId10 = string;
export type CardId8 = string;
export type ExpectedVersion10 = number;
export type InputToken8 = string;
export type Kind10 = 'decline_proposal';
export type Reason1 = 'want_other' | 'not_now' | 'request_human';
export type TargetIssueId10 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId11 = string;
export type CardId9 = string;
export type ExpectedVersion11 = number;
export type InputToken9 = string;
export type Kind11 = 'skip_retake';
export type Reason2 = string;
export type TargetIssueId11 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId12 = string;
export type CardId10 = string;
export type ExpectedVersion12 = number;
export type InputToken10 = string;
export type Kind12 = 'rate_satisfaction';
export type Comment = string | null;
export type Score = number;
export type TargetIssueId12 = string;
export type Code = 'stale_version' | 'stale_card' | 'not_allowed_now' | 'run_active';
export type Message = string;
export type ActionId13 = string;
export type Replayed = boolean;
export type RunId = string;
export type VersionAfter = number | null;

export interface ActionRequestSchema {
  contract: ActionRequest;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "SelectProductAction".
 */
export interface SelectProductAction {
  action_id: ActionId;
  card_id: CardId;
  expected_version: ExpectedVersion;
  input_token: InputToken;
  kind: Kind;
  payload: SelectProductPayload;
  target_issue_id: TargetIssueId;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "SelectProductPayload".
 */
export interface SelectProductPayload {
  sku: Sku;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "StepFeedbackAction".
 */
export interface StepFeedbackAction {
  action_id: ActionId1;
  card_id: CardId1;
  expected_version: ExpectedVersion1;
  input_token: InputToken1;
  kind: Kind1;
  payload: StepFeedbackPayload;
  target_issue_id: TargetIssueId1;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "StepFeedbackPayload".
 */
export interface StepFeedbackPayload {
  feedback: Feedback;
  note?: Note;
  observations?: Observations;
}
/**
 * 用户对某个步骤观察的选择；option_id 必须是该步骤声明过的选项。
 *
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ObservationAnswer".
 */
export interface ObservationAnswer {
  observation_id: ObservationId;
  option_id: OptionId;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "AnswerObservationAction".
 */
export interface AnswerObservationAction {
  action_id: ActionId2;
  card_id: CardId2;
  expected_version: ExpectedVersion2;
  input_token: InputToken2;
  kind: Kind2;
  payload: AnswerObservationPayload;
  target_issue_id: TargetIssueId2;
}
/**
 * observation_card 的作答；option_id 必须是该卡声明过的选项。
 * kind=unknown 的选项记为「答不上来」，不写成观察事实。
 *
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "AnswerObservationPayload".
 */
export interface AnswerObservationPayload {
  observation_id: ObservationId1;
  option_id: OptionId1;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmReceiptAction".
 */
export interface ConfirmReceiptAction {
  action_id: ActionId3;
  card_id: CardId3;
  expected_version: ExpectedVersion3;
  input_token: InputToken3;
  kind: Kind3;
  payload: ConfirmReceiptPayload;
  target_issue_id: TargetIssueId3;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmReceiptPayload".
 */
export interface ConfirmReceiptPayload {
  edited?: Edited;
  fields: ReceiptFields;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ReceiptFields".
 */
export interface ReceiptFields {
  amount?: Amount;
  channel?: Channel;
  order_no?: OrderNo;
  purchase_date?: PurchaseDate;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "SkipReceiptAction".
 */
export interface SkipReceiptAction {
  action_id: ActionId4;
  card_id: CardId4;
  expected_version: ExpectedVersion4;
  input_token: InputToken4;
  kind: Kind4;
  payload: SkipReceiptPayload;
  target_issue_id: TargetIssueId4;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "SkipReceiptPayload".
 */
export interface SkipReceiptPayload {
  reason: Reason;
}
/**
 * 任何时刻可用；服务端忽略 version 与 pending 校验，有 active run 先取消。
 *
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "RequestHumanAction".
 */
export interface RequestHumanAction {
  action_id: ActionId5;
  card_id?: CardId5;
  expected_version: ExpectedVersion5;
  input_token?: InputToken5;
  kind: Kind5;
  payload?: RequestHumanPayload;
  target_issue_id?: TargetIssueId5;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "RequestHumanPayload".
 */
export interface RequestHumanPayload {}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "NewIssueAction".
 */
export interface NewIssueAction {
  action_id: ActionId6;
  expected_version: ExpectedVersion6;
  kind: Kind6;
  payload?: RequestHumanPayload;
  target_issue_id?: TargetIssueId6;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ResumeIssueAction".
 */
export interface ResumeIssueAction {
  action_id: ActionId7;
  expected_version: ExpectedVersion7;
  kind: Kind7;
  payload?: RequestHumanPayload;
  target_issue_id: TargetIssueId7;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmContextAction".
 */
export interface ConfirmContextAction {
  action_id: ActionId8;
  card_id: CardId6;
  expected_version: ExpectedVersion8;
  input_token: InputToken6;
  kind: Kind8;
  payload: ConfirmContextPayload;
  target_issue_id: TargetIssueId8;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmContextPayload".
 */
export interface ConfirmContextPayload {
  channel: Channel1;
  platform?: Platform;
  region_purchase: RegionPurchase;
  region_use: RegionUse;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmProposalAction".
 */
export interface ConfirmProposalAction {
  action_id: ActionId9;
  card_id: CardId7;
  expected_version: ExpectedVersion9;
  input_token: InputToken7;
  kind: Kind9;
  payload: ConfirmProposalPayload;
  target_issue_id: TargetIssueId9;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmProposalPayload".
 */
export interface ConfirmProposalPayload {
  option_id: OptionId2;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "DeclineProposalAction".
 */
export interface DeclineProposalAction {
  action_id: ActionId10;
  card_id: CardId8;
  expected_version: ExpectedVersion10;
  input_token: InputToken8;
  kind: Kind10;
  payload: DeclineProposalPayload;
  target_issue_id: TargetIssueId10;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "DeclineProposalPayload".
 */
export interface DeclineProposalPayload {
  reason: Reason1;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "SkipRetakeAction".
 */
export interface SkipRetakeAction {
  action_id: ActionId11;
  card_id: CardId9;
  expected_version: ExpectedVersion11;
  input_token: InputToken9;
  kind: Kind11;
  payload: SkipRetakePayload;
  target_issue_id: TargetIssueId11;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "SkipRetakePayload".
 */
export interface SkipRetakePayload {
  reason?: Reason2;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "RateSatisfactionAction".
 */
export interface RateSatisfactionAction {
  action_id: ActionId12;
  card_id: CardId10;
  expected_version: ExpectedVersion12;
  input_token: InputToken10;
  kind: Kind12;
  payload: RateSatisfactionPayload;
  target_issue_id: TargetIssueId12;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "RateSatisfactionPayload".
 */
export interface RateSatisfactionPayload {
  comment?: Comment;
  score: Score;
}
/**
 * 409 响应体：附最新快照供前端重建（08 §4 第 3 步）。
 *
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ActionConflict".
 */
export interface ActionConflict {
  code: Code;
  message: Message;
  snapshot: Snapshot;
}
/**
 * SessionSnapshot 序列化结果；此处用 dict 避免循环引用
 */
export interface Snapshot {
  [k: string]: unknown;
}
/**
 * 写入 session_actions.result_json 并在幂等重放时返回。
 *
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ActionResult".
 */
export interface ActionResult {
  action_id: ActionId13;
  replayed?: Replayed;
  run_id: RunId;
  version_after?: VersionAfter;
}

export type ActionKind = ActionRequest['kind'];
