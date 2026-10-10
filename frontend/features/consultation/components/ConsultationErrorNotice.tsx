import type { ReactNode } from "react";

import styles from "./ConsultationErrorNotice.module.css";

interface ConsultationErrorNoticeProps {
  message: string | null;
  actionLabel?: string;
  actionDisabled?: boolean;
  onAction?: () => void;
  children: ReactNode;
}

export function ConsultationErrorNotice({
  message,
  actionLabel,
  actionDisabled = false,
  onAction,
  children,
}: ConsultationErrorNoticeProps) {
  return (
    <>
      {message ? (
        <div className={styles.noticeArea}>
          <div className={styles.notice}>
            <p role="alert">{message}</p>
            {actionLabel && onAction ? (
              <button
                className={styles.actionButton}
                type="button"
                disabled={actionDisabled}
                onClick={onAction}
              >
                {actionDisabled ? "状態を確認しています…" : actionLabel}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      {children}
    </>
  );
}
