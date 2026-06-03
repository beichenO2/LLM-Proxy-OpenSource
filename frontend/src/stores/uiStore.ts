import { create } from "zustand";

const STORAGE_KEY = "privportal:ui";

interface IPersistedUi {
  activeProjectId: string | null;
  sidebarCollapsed: boolean;
}

function loadPersisted(): IPersistedUi {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { activeProjectId: null, sidebarCollapsed: false };
    const parsed = JSON.parse(raw) as Partial<IPersistedUi>;
    return {
      activeProjectId: typeof parsed.activeProjectId === "string" ? parsed.activeProjectId : null,
      sidebarCollapsed: parsed.sidebarCollapsed === true,
    };
  } catch {
    return { activeProjectId: null, sidebarCollapsed: false };
  }
}

function persist(state: IPersistedUi): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // localStorage may be full or unavailable — silently ignore
  }
}

interface IUiState {
  activeProjectId: string | null;
  setActiveProjectId: (id: string | null) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  vaultRole: "admin" | "user" | "readonly" | "service" | null;
  setVaultRole: (role: "admin" | "user" | "readonly" | "service" | null) => void;
}

const initial = loadPersisted();

export const useUiStore = create<IUiState>((set, get) => ({
  activeProjectId: initial.activeProjectId,
  setActiveProjectId: (id) => {
    set({ activeProjectId: id });
    persist({ ...get(), activeProjectId: id });
  },
  sidebarCollapsed: initial.sidebarCollapsed,
  toggleSidebar: () => {
    const next = !get().sidebarCollapsed;
    set({ sidebarCollapsed: next });
    persist({ ...get(), sidebarCollapsed: next });
  },
  vaultRole: null,
  setVaultRole: (role) => set({ vaultRole: role }),
}));
