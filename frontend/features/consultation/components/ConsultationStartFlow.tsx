"use client";

import { useState } from "react";

import type {
  StartConsultationRequest,
  ThemeCategory,
} from "../model/contracts";
import { getStartConsultationErrorMessage } from "../model/errorMessages";
import type { ConsultationErrorCode } from "../model/state";
import { DetailInputStep } from "./DetailInputStep";
import { ThemeSelectionStep } from "./ThemeSelectionStep";

type StartStep = "theme" | "detail";

interface ConsultationStartFlowProps {
  detailMaxLength: number;
  isSubmitting: boolean;
  startErrorCode: ConsultationErrorCode | null;
  onBackToNotice: () => void;
  onCancel: () => void;
  onStartConsultation: (request: StartConsultationRequest) => void;
}

export function ConsultationStartFlow({
  detailMaxLength,
  isSubmitting,
  startErrorCode,
  onBackToNotice,
  onCancel,
  onStartConsultation,
}: ConsultationStartFlowProps) {
  const [step, setStep] = useState<StartStep>("theme");
  const [selectedTheme, setSelectedTheme] = useState<ThemeCategory | null>(null);
  const [detail, setDetail] = useState("");
  const startErrorMessage =
    getStartConsultationErrorMessage(startErrorCode);

  function handleThemeNext(theme: ThemeCategory) {
    setSelectedTheme(theme);
    setStep("detail");
  }

  function handleDetailBack() {
    setStep("theme");
  }

  function handleStart(detailInput: string) {
    if (selectedTheme === null) {
      setStep("theme");
      return;
    }

    onStartConsultation({
      theme: selectedTheme,
      detail: detailInput,
    });
  }

  if (step === "detail" && selectedTheme !== null) {
    return (
      <DetailInputStep
        selectedTheme={selectedTheme}
        detail={detail}
        maxLength={detailMaxLength}
        isSubmitting={isSubmitting}
        startErrorMessage={startErrorMessage}
        onDetailChange={setDetail}
        onBack={handleDetailBack}
        onCancel={onCancel}
        onStart={handleStart}
      />
    );
  }

  return (
    <ThemeSelectionStep
      selectedTheme={selectedTheme}
      onThemeChange={setSelectedTheme}
      onBack={onBackToNotice}
      onNext={handleThemeNext}
    />
  );
}
