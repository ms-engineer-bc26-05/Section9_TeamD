export type MemoHandling = "tell" | "hold" | "not_tell";

export interface MemoListItem {
  memo_id: string;
  created_at: string;
  summary: string;
  handling: MemoHandling;
}

export interface MemoListResponse {
  memos: MemoListItem[];
  next_cursor: string | null;
}

export interface MemoDetail {
  memo_id: string;
  created_at: string;
  event_summary: string;
  emotion: string;
  true_feeling: string;
  background: string;
  wish: string;
  handling: MemoHandling;
  reason: string | null;
}
