import type { ReactNode } from "react";

import styles from "./ConsultationErrorNotice.module.css";

interface ConsultationErrorNoticeProps {
  message: string | null;
  children: ReactNode;
}

export function ConsultationErrorNotice({
  message,
  children,
}: ConsultationErrorNoticeProps) {
  return (
    <>
      {message ? (
        <div className={styles.noticeArea}>
          <p className={styles.notice} role="alert">
            {message}
          </p>
        </div>
      ) : null}
      {children}
    </>
  );
}
