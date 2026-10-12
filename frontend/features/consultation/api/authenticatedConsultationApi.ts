import { apiClient } from "@/lib/apiClient";

import { createConsultationApi } from "./consultationApi";

/** Issue #48の認証済み共通クライアントを、相談APIの公開境界へ接続する。 */
export const authenticatedConsultationApi = createConsultationApi(apiClient);
