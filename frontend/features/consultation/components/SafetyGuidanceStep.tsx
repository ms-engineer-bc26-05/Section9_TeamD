"use client";

import {
  SAFETY_CONTACTS_VERIFIED_ON,
  SAFETY_SUPPORT_CONTACTS,
} from "../model/constants";
import styles from "./SafetyGuidanceStep.module.css";

const FALLBACK_SAFETY_MESSAGE =
  "安全のため、このサービスでの通常の整理はいったん終了します。ひとりで抱えずに、相談窓口で話を聞いてもらうこともできますよ。";

interface SafetyGuidanceStepProps {
  safetyMessage: string | null;
  isSubmitting: boolean;
  onFinish: () => void;
}

export function SafetyGuidanceStep({
  safetyMessage,
  isSubmitting,
  onFinish,
}: SafetyGuidanceStepProps) {
  const message = safetyMessage?.trim() || FALLBACK_SAFETY_MESSAGE;

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="safety-guidance-title">
        <p className={styles.eyebrow}>大切なお知らせ</p>
        <h1 id="safety-guidance-title" className={styles.title}>
          ここからは、相談窓口をご案内します
        </h1>

        <p className={styles.guidanceMessage}>{message}</p>

        <section className={styles.emergencyCard} aria-labelledby="emergency-title">
          <h2 id="emergency-title" className={styles.sectionTitle}>
            今すぐ身の危険があるとき
          </h2>
          <p className={styles.sectionText}>
            自分やほかの人を傷つけるおそれがあるときは、警察または救急へ連絡してください。
          </p>
          <div className={styles.emergencyLinks}>
            <a className={styles.emergencyLink} href="tel:110">
              警察 110
            </a>
            <a className={styles.emergencyLink} href="tel:119">
              救急 119
            </a>
          </div>
        </section>

        <section className={styles.contactsSection} aria-labelledby="contacts-title">
          <h2 id="contacts-title" className={styles.sectionTitle}>
            話を聞いてくれる相談窓口
          </h2>
          <ul className={styles.contactList}>
            {SAFETY_SUPPORT_CONTACTS.map((contact) => (
              <li className={styles.contactCard} key={contact.name}>
                <h3 className={styles.contactName}>{contact.name}</h3>
                <p className={styles.contactDescription}>{contact.description}</p>
                <div className={styles.contactActions}>
                  {"phoneNumber" in contact && contact.phoneNumber ? (
                    <a
                      className={styles.contactLink}
                      href={`tel:${contact.phoneNumber.replaceAll("-", "")}`}
                    >
                      {contact.phoneNumber}へ電話
                    </a>
                  ) : null}
                  <a
                    className={styles.secondaryLink}
                    href={contact.websiteUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    公式サイトを開く
                  </a>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <p className={styles.verifiedText}>
          窓口情報は{SAFETY_CONTACTS_VERIFIED_ON}に公式情報を確認しています。
        </p>

        <button
          className={styles.finishButton}
          type="button"
          disabled={isSubmitting}
          onClick={onFinish}
        >
          {isSubmitting ? "終了しています…" : "相談を終了してホームへ戻る"}
        </button>

        {isSubmitting ? (
          <p className={styles.loadingMessage} role="status">
            相談を終了しています…
          </p>
        ) : null}
      </section>
    </main>
  );
}
