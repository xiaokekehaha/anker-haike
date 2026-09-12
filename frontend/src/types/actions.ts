// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.
// Source: contracts/schema/actions.schema.json
// SHA-256: 7ba75f6b6c6f6e87b667b8a638b9b519edeb13dd39ca1eb870ddea11f20eb666

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
  | RediagnoseAction;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId = string;
export type CardId = string;
export type ExpectedVersion = number;
export type InterruptId = string;
export type Kind = 'select_product';
export type Sku = string;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId1 = string;
export type CardId1 = string;
export type ExpectedVersion1 = number;
export type InterruptId1 = string;
export type Kind1 = 'step_feedback';
export type Feedback = 'solved' | 'not_solved' | 'cannot_do';
export type Note = string | null;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId2 = string;
export type CardId2 = string;
export type ExpectedVersion2 = number;
export type InterruptId2 = string;
export type Kind2 = 'confirm_receipt';
export type Edited = ('order_no' | 'channel' | 'purchase_date' | 'amount')[];
export type Amount = string | null;
export type Channel = string | null;
export type OrderNo = string | null;
export type PurchaseDate = string | null;
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId3 = string;
export type CardId3 = string;
export type ExpectedVersion3 = number;
export type InterruptId3 = string;
export type Kind3 = 'skip_receipt';
export type Reason = 'none' | 'unreadable' | 'later';
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId4 = string;
export type CardId4 = string | null;
export type ExpectedVersion4 = number;
export type InterruptId4 = string | null;
export type Kind4 = 'request_human';
/**
 * 前端生成的 uuid，重试时复用，服务端据此幂等
 */
export type ActionId5 = string;
export type CardId5 = string | null;
export type ExpectedVersion5 = number;
export type InterruptId5 = string | null;
export type Kind5 = 'rediagnose';
export type ImageIds = string[];
export type Text = string | null;
export type Code = 'version_mismatch' | 'stale_card' | 'not_allowed_now' | 'run_active';
export type Message = string;
export type ActionId6 = string;
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
  interrupt_id: InterruptId;
  kind: Kind;
  payload: SelectProductPayload;
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
  interrupt_id: InterruptId1;
  kind: Kind1;
  payload: StepFeedbackPayload;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "StepFeedbackPayload".
 */
export interface StepFeedbackPayload {
  feedback: Feedback;
  note?: Note;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "ConfirmReceiptAction".
 */
export interface ConfirmReceiptAction {
  action_id: ActionId2;
  card_id: CardId2;
  expected_version: ExpectedVersion2;
  interrupt_id: InterruptId2;
  kind: Kind2;
  payload: ConfirmReceiptPayload;
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
  action_id: ActionId3;
  card_id: CardId3;
  expected_version: ExpectedVersion3;
  interrupt_id: InterruptId3;
  kind: Kind3;
  payload: SkipReceiptPayload;
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
  interrupt_id?: InterruptId4;
  kind: Kind4;
  payload?: RequestHumanPayload;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "RequestHumanPayload".
 */
export interface RequestHumanPayload {}
/**
 * guide / verify 阶段且无 active run；无绑定卡片。
 *
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "RediagnoseAction".
 */
export interface RediagnoseAction {
  action_id: ActionId5;
  card_id?: CardId5;
  expected_version: ExpectedVersion5;
  interrupt_id?: InterruptId5;
  kind: Kind5;
  payload: RediagnosePayload;
}
/**
 * This interface was referenced by `ActionRequestSchema`'s JSON-Schema
 * via the `definition` "RediagnosePayload".
 */
export interface RediagnosePayload {
  image_ids?: ImageIds;
  text?: Text;
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
  action_id: ActionId6;
  replayed?: Replayed;
  run_id: RunId;
  version_after?: VersionAfter;
}

export type ActionKind = ActionRequest['kind'];
