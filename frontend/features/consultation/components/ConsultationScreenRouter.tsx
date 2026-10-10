import type { ReactNode } from "react";

import {
  resolveConsultationScreen,
  type ConsultationScreen,
} from "../model/screen";
import type { ConsultationState } from "../model/state";

interface ConsultationScreenRouterProps {
  state: ConsultationState;
  screens: Record<ConsultationScreen, ReactNode>;
}

export function ConsultationScreenRouter({
  state,
  screens,
}: ConsultationScreenRouterProps) {
  const currentScreen = resolveConsultationScreen(state);

  return screens[currentScreen];
}
