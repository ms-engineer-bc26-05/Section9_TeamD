"use client";

import { useState } from "react";

import type { EmotionCategory, EmotionRequest } from "../model/contracts";
import { EmotionDetailStep } from "./EmotionDetailStep";
import { EmotionSelectionStep } from "./EmotionSelectionStep";

type EmotionInputStep = "selection" | "detail";

interface EmotionInputFlowProps {
  selectedEmotion: EmotionCategory | null;
  detailMaxLength: number;
  isSubmitting: boolean;
  onEmotionChange: (emotion: EmotionCategory) => void;
  onCancel: () => void;
  onSubmit: (request: EmotionRequest) => void;
}

export function EmotionInputFlow({
  selectedEmotion,
  detailMaxLength,
  isSubmitting,
  onEmotionChange,
  onCancel,
  onSubmit,
}: EmotionInputFlowProps) {
  const [step, setStep] = useState<EmotionInputStep>("selection");
  const [detail, setDetail] = useState("");
  const [cannotVerbalize, setCannotVerbalize] = useState(false);

  function handleSelectionNext(emotion: EmotionCategory) {
    onEmotionChange(emotion);
    setStep("detail");
  }

  function handleDetailBack() {
    if (isSubmitting) {
      return;
    }

    setStep("selection");
  }

  if (step === "detail" && selectedEmotion !== null) {
    return (
      <EmotionDetailStep
        selectedEmotion={selectedEmotion}
        detail={detail}
        cannotVerbalize={cannotVerbalize}
        maxLength={detailMaxLength}
        isSubmitting={isSubmitting}
        onDetailChange={setDetail}
        onCannotVerbalizeChange={setCannotVerbalize}
        onBack={handleDetailBack}
        onCancel={onCancel}
        onNext={onSubmit}
      />
    );
  }

  return (
    <EmotionSelectionStep
      selectedEmotion={selectedEmotion}
      onEmotionChange={onEmotionChange}
      onNext={handleSelectionNext}
      onCancel={onCancel}
    />
  );
}
