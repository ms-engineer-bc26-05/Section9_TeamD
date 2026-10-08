import type { ReactNode } from "react";

import type { ConsultationState } from "../model/state";
import { SafetyGuidanceStep } from "./SafetyGuidanceStep";

interface ConsultationSafetyBoundaryProps {
  state: Pick<
    ConsultationState,
    "status" | "safetyGuidance" | "pendingOperation"
  >;
  children: ReactNode;
  onFinish: () => void;
}

export function ConsultationSafetyBoundary({
  state,
  children,
  onFinish,
}: ConsultationSafetyBoundaryProps) {
  if (state.status !== "safety_guidance") {
    return children;
  }

  return (
    <SafetyGuidanceStep
      safetyMessage={state.safetyGuidance?.safety_message ?? null}
      isSubmitting={state.pendingOperation === "discard"}
      onFinish={onFinish}
    />
  );
}
