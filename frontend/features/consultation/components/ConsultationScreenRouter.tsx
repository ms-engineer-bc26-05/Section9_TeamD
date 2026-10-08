import type { ReactNode } from "react";

import {
  resolveConsultationScreen,
  type ConsultationScreen,
} from "../model/screen";
import type { ConsultationState } from "../model/state";
import { ConsultationSafetyBoundary } from "./ConsultationSafetyBoundary";

interface ConsultationScreenRouterProps {
  state: ConsultationState;
  screens: Record<ConsultationScreen, ReactNode>;
  onFinishSafetyGuidance: () => void;
}

export function ConsultationScreenRouter({
  state,
  screens,
  onFinishSafetyGuidance,
}: ConsultationScreenRouterProps) {
  const currentScreen = resolveConsultationScreen(state);

  return (
    <ConsultationSafetyBoundary
      state={state}
      onFinish={onFinishSafetyGuidance}
    >
      {screens[currentScreen]}
    </ConsultationSafetyBoundary>
  );
}
