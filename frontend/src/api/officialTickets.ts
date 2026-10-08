/** 主办方 63 单工单（后端 /official/tickets）：演示与回归时把真实工单原文和附件载入输入框。 */
export type OfficialTicket = {
  id: string;
  product_line: string;
  product_name: string;
  scenario: 'shipping' | 'troubleshooting';
  body: string;
  attachments: string[];
};

export async function listOfficialTickets(): Promise<OfficialTicket[]> {
  const res = await fetch('/official/tickets');
  if (!res.ok) throw new Error(`official tickets ${res.status}`);
  return (await res.json()) as OfficialTicket[];
}

/** 附件按原文件名取回成 File，交给输入框走与用户手动选择图片相同的压缩与校验。 */
export async function ticketFiles(ticket: OfficialTicket): Promise<File[]> {
  return Promise.all(ticket.attachments.map(async (name) => {
    const res = await fetch(`/official/tickets/${ticket.id}/attachments/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error(`attachment ${name} ${res.status}`);
    const blob = await res.blob();
    return new File([blob], name, { type: blob.type || 'image/jpeg' });
  }));
}
