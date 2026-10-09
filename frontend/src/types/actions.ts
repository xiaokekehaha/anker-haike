// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.
// Source: contracts/schema/actions.schema.json
// SHA-256: fc8ac1760536ef912e366dddef61cf2a4081bffe56a36b14b57f1a15db59bc3b

/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ActionRequest".
 */
export type ActionRequest =
  | SelectProductAction
  | StepFeedbackAction
  | ConfirmReceiptAction
  | SkipReceiptAction
  | RequestHumanAction
  | NewIssueAction
  | ResumeIssueAction
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
export type Option = string | null;
export type Text = string | null;
export type Unavailable = boolean;
export type Feedback = ('solved' | 'not_solved' | 'cannot_do') | null;
export type Note = string | null;
export type TargetIssueId1 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId2 = string;
export type CardId2 = string;
export type ExpectedVersion2 = number;
export type InputToken2 = string;
export type Kind2 = 'confirm_receipt';
export type Edited = ('order_no' | 'seller' | 'country' | 'purchase_date' | 'amount')[];
export type Amount = string | null;
export type Country = string | null;
export type OrderNo = string | null;
export type PurchaseDate = string | null;
export type Seller = string | null;
export type TargetIssueId2 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId3 = string;
export type CardId3 = string;
export type ExpectedVersion3 = number;
export type InputToken3 = string;
export type Kind3 = 'skip_receipt';
export type Reason = 'none' | 'unreadable' | 'later';
export type TargetIssueId3 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId4 = string;
export type CardId4 = string | null;
export type ExpectedVersion4 = number;
export type InputToken4 = string | null;
export type Kind4 = 'request_human';
export type TargetIssueId4 = string | null;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId5 = string;
export type ExpectedVersion5 = number;
export type Kind5 = 'new_issue';
export type TargetIssueId5 = null;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId6 = string;
export type ExpectedVersion6 = number;
export type Kind6 = 'resume_issue';
export type TargetIssueId6 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId7 = string;
export type CardId5 = string;
export type ExpectedVersion7 = number;
export type InputToken5 = string;
export type Kind7 = 'confirm_proposal';
export type OptionId = string;
export type TargetIssueId7 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId8 = string;
export type CardId6 = string;
export type ExpectedVersion8 = number;
export type InputToken6 = string;
export type Kind8 = 'decline_proposal';
export type Reason1 = 'want_other' | 'not_now' | 'request_human';
export type TargetIssueId8 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId9 = string;
export type CardId7 = string;
export type ExpectedVersion9 = number;
export type InputToken7 = string;
export type Kind9 = 'skip_retake';
export type Reason2 = string;
export type TargetIssueId9 = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId10 = string;
export type CardId8 = string;
export type ExpectedVersion10 = number;
export type InputToken8 = string;
export type Kind10 = 'rate_satisfaction';
export type Comment = string | null;
export type Score = number;
export type TargetIssueId10 = string;
export type Code = 'stale_version' | 'stale_card' | 'not_allowed_now' | 'run_active';
export type Message = string;
export type ActionId11 = string;
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
 * action 卡交 feedback；question / material_request 卡交 answer；statement 卡两者都可省（确认已读）。
 * 服务端按卡片 kind 校验组合（sessions/router.py）。
 *
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "StepFeedbackPayload".
 */
export interface StepFeedbackPayload {
  answer?: StepAnswer | null;
  feedback?: Feedback;
  note?: Note;
}
/**
 * 问句卡 / 材料卡的回答：选项原文或短答；material_request 可声明暂时没有。
 *
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "StepAnswer".
 */
export interface StepAnswer {
  option?: Option;
  text?: Text;
  unavailable?: Unavailable;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmReceiptAction".
 */
export interface ConfirmReceiptAction {
  action_id: ActionId2;
  card_id: CardId2;
  expected_version: ExpectedVersion2;
  input_token: InputToken2;
  kind: Kind2;
  payload: ConfirmReceiptPayload;
  target_issue_id: TargetIssueId2;
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
  country?: Country;
  order_no?: OrderNo;
  purchase_date?: PurchaseDate;
  seller?: Seller;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "SkipReceiptAction".
 */
export interface SkipReceiptAction {
  action_id: ActionId3;
  card_id: CardId3;
  expected_version: ExpectedVersion3;
  input_token: InputToken3;
  kind: Kind3;
  payload: SkipReceiptPayload;
  target_issue_id: TargetIssueId3;
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
  action_id: ActionId4;
  card_id?: CardId4;
  expected_version: ExpectedVersion4;
  input_token?: InputToken4;
  kind: Kind4;
  payload?: RequestHumanPayload;
  target_issue_id?: TargetIssueId4;
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
  action_id: ActionId5;
  expected_version: ExpectedVersion5;
  kind: Kind5;
  payload?: RequestHumanPayload;
  target_issue_id?: TargetIssueId5;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ResumeIssueAction".
 */
export interface ResumeIssueAction {
  action_id: ActionId6;
  expected_version: ExpectedVersion6;
  kind: Kind6;
  payload?: RequestHumanPayload;
  target_issue_id: TargetIssueId6;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmProposalAction".
 */
export interface ConfirmProposalAction {
  action_id: ActionId7;
  card_id: CardId5;
  expected_version: ExpectedVersion7;
  input_token: InputToken5;
  kind: Kind7;
  payload: ConfirmProposalPayload;
  target_issue_id: TargetIssueId7;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmProposalPayload".
 */
export interface ConfirmProposalPayload {
  option_id: OptionId;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "DeclineProposalAction".
 */
export interface DeclineProposalAction {
  action_id: ActionId8;
  card_id: CardId6;
  expected_version: ExpectedVersion8;
  input_token: InputToken6;
  kind: Kind8;
  payload: DeclineProposalPayload;
  target_issue_id: TargetIssueId8;
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
  action_id: ActionId9;
  card_id: CardId7;
  expected_version: ExpectedVersion9;
  input_token: InputToken7;
  kind: Kind9;
  payload: SkipRetakePayload;
  target_issue_id: TargetIssueId9;
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
  action_id: ActionId10;
  card_id: CardId8;
  expected_version: ExpectedVersion10;
  input_token: InputToken8;
  kind: Kind10;
  payload: RateSatisfactionPayload;
  target_issue_id: TargetIssueId10;
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
  action_id: ActionId11;
  replayed?: Replayed;
  run_id: RunId;
  version_after?: VersionAfter;
}

export type ActionKind = ActionRequest['kind'];
