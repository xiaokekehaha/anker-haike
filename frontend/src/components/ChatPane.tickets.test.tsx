import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChatPane } from './ChatPane';

const TICKETS = [
  { id: 'T18', product_line: 'Robovacs', product_name: 'Omni E28', scenario: 'troubleshooting', body: 'Productnaam: Omni E28', attachments: ['T18.jpg'] },
];

afterEach(() => vi.unstubAllGlobals());

describe('载入真实工单', () => {
  it('展开后才拉列表，选中即回调该工单', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => TICKETS });
    vi.stubGlobal('fetch', fetch);
    const onLoadTicket = vi.fn();
    const { container } = render(<ChatPane onPick={vi.fn()} onLoadTicket={onLoadTicket} />);
    expect(fetch).not.toHaveBeenCalled();
    const details = [...container.querySelectorAll('details')].find((d) => d.textContent?.includes('载入主办方真实工单'))!;
    details.open = true;
    fireEvent(details, new Event('toggle'));
    const select = await screen.findByLabelText('选择主办方工单');
    expect(fetch).toHaveBeenCalledWith('/official/tickets');
    expect(screen.getByRole('option', { name: /T18 · 排障 · Omni E28 · 1 图/ })).toBeInTheDocument();
    fireEvent.change(select, { target: { value: 'T18' } });
    await waitFor(() => expect(onLoadTicket).toHaveBeenCalledWith(TICKETS[0]));
  });
});
