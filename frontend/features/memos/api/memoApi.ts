import type { MemoDetail, MemoListResponse } from "../model/contracts";

export interface MemoApiRequestOptions {
  signal?: AbortSignal;
}

/** 共通apiClientのうち、保存メモ機能が利用する操作だけを表す。 */
export interface MemoAuthenticatedApiClient {
  get<T>(path: string, options?: MemoApiRequestOptions): Promise<T>;
  delete(path: string, options?: MemoApiRequestOptions): Promise<void>;
}

export interface MemoApi {
  list(
    cursor?: string,
    options?: MemoApiRequestOptions,
  ): Promise<MemoListResponse>;
  detail(
    memoId: string,
    options?: MemoApiRequestOptions,
  ): Promise<MemoDetail>;
  delete(
    memoId: string,
    options?: MemoApiRequestOptions,
  ): Promise<void>;
}

function memoPath(memoId: string): string {
  return `/memos/${encodeURIComponent(memoId)}`;
}

export function createMemoApi(apiClient: MemoAuthenticatedApiClient): MemoApi {
  return {
    list(cursor, options) {
      const path =
        cursor === undefined
          ? "/memos"
          : `/memos?cursor=${encodeURIComponent(cursor)}`;
      return apiClient.get<MemoListResponse>(path, options);
    },

    detail(memoId, options) {
      return apiClient.get<MemoDetail>(memoPath(memoId), options);
    },

    delete(memoId, options) {
      return apiClient.delete(memoPath(memoId), options);
    },
  };
}
