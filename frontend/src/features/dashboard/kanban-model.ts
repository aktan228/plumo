export const stages = ["unassigned", "new", "discovery", "qualified", "meeting_requested", "meeting_confirmed"] as const;
export type Stage = typeof stages[number];
export type BoardCard = { id: string; pipeline_stage: Stage; stage_version: number; channel: string; mode: "ai" | "human" | "waiting"; name: string | null; handle: string | null; phone: string | null; preview: string | null; activity_at: string };
export type Column = { stage: Stage; total: number; items: BoardCard[]; next_cursor: string | null };
export type Board = Record<Stage, Column>;

export async function loadColumn(count: number, fetchPage: (limit: number, cursor?: string) => Promise<Column>): Promise<Column> {
  const items = new Map<string, BoardCard>();
  const seen = new Set<string>();
  let cursor: string | undefined;
  while (true) {
    const page = await fetchPage(Math.min(100, count - items.size), cursor);
    for (const item of page.items) items.set(item.id, item);
    if (!page.next_cursor || items.size >= count) return { ...page, items: [...items.values()] };
    if (seen.has(page.next_cursor)) throw new Error("Repeated board cursor");
    seen.add(page.next_cursor);
    cursor = page.next_cursor;
  }
}

/** Pure optimistic transition; retain the prior board for rollback until the API acknowledges. */
export function moveCard(board: Board, card: BoardCard, target: Stage): Board {
  if (card.pipeline_stage === target) return board;
  const source = board[card.pipeline_stage];
  if (!source.items.some(item => item.id === card.id && item.stage_version === card.stage_version)) return board;
  return { ...board,
    [card.pipeline_stage]: { ...source, total: Math.max(0, source.total - 1), items: source.items.filter(item => item.id !== card.id) },
    [target]: { ...board[target], total: board[target].total + 1, items: [{ ...card, pipeline_stage: target, stage_version: card.stage_version + 1 }, ...board[target].items.filter(item => item.id !== card.id)] },
  };
}
