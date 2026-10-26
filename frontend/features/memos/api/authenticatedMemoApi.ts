import { apiClient } from "@/lib/apiClient";

import { createMemoApi } from "./memoApi";

/** 共通の認証済みAPI Clientへ接続した、参照が安定した保存メモAPI。 */
export const authenticatedMemoApi = createMemoApi(apiClient);
