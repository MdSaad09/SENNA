import { create } from "zustand";

interface UiState {
  contextLost: boolean;
  // null until the first canvas reports its renderer string (the GPU heuristic
  // decides the default; the toggle then owns it)
  bloomEnabled: boolean | null;
  bloomReason: string;
  devOverlayOpen: boolean;
  setContextLost(lost: boolean): void;
  setBloomDefault(enabled: boolean, reason: string): void;
  setBloom(enabled: boolean): void;
  toggleDevOverlay(): void;
}

export const useUiStore = create<UiState>((set) => ({
  contextLost: false,
  bloomEnabled: null,
  bloomReason: "",
  devOverlayOpen: false,
  setContextLost: (lost) => set({ contextLost: lost }),
  setBloomDefault: (enabled, reason) =>
    set((state) =>
      // the heuristic only fills the initial position; a user choice sticks
      state.bloomEnabled === null ? { bloomEnabled: enabled, bloomReason: reason } : state,
    ),
  setBloom: (enabled) => set({ bloomEnabled: enabled, bloomReason: "set by the quality toggle" }),
  toggleDevOverlay: () => set((state) => ({ devOverlayOpen: !state.devOverlayOpen })),
}));
