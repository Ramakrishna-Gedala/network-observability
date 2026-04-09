import { create } from "zustand";

interface PipelineState {
  health: "green" | "yellow" | "red";
  alertBadgeCount: number;
  setHealth: (h: PipelineState["health"]) => void;
  setAlertBadgeCount: (n: number) => void;
}

export const usePipelineStore = create<PipelineState>((set) => ({
  health: "green",
  alertBadgeCount: 0,
  setHealth: (h) => set({ health: h }),
  setAlertBadgeCount: (n) => set({ alertBadgeCount: n }),
}));
