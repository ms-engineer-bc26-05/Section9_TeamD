// POST /users/me・PATCH /users/me のレスポンス(設計書6.1.1・6.1.2)
// user_id はFirebase UIDではなく、内部ユーザーのUUID
export type User = {
  user_id: string;
  has_seen_notice: boolean;
};