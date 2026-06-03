import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { apiRequest } from "../lib/api";
import { useUiStore } from "../stores/uiStore";
import CommandPalette from "./CommandPalette";
import OnboardingWizard from "./OnboardingWizard";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import UnlockModal from "./UnlockModal";

function useThemeSync() {
  useEffect(() => {
    apiRequest<{ api_port: number | null; preferences: Record<string, unknown> }>("/api/settings")
      .then((data) => {
        const theme = data?.preferences?.theme;
        if (theme === "dark") {
          document.documentElement.classList.add("dark");
        } else {
          document.documentElement.classList.remove("dark");
        }
      })
      .catch(() => {});

    function onThemeChange(e: Event) {
      const detail = (e as CustomEvent<string>).detail;
      if (detail === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    }
    window.addEventListener("pp:theme-change", onThemeChange);
    return () => window.removeEventListener("pp:theme-change", onThemeChange);
  }, []);
}

export default function AppLayout() {
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  useThemeSync();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "b") {
        e.preventDefault();
        toggleSidebar();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [toggleSidebar]);

  return (
    <div className="flex min-h-screen min-w-[1024px] dark:bg-neutral-900">
      <Sidebar />
      <div className="relative flex min-h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-auto bg-neutral-50 dark:bg-neutral-900">
          <Outlet />
        </main>
        <OnboardingWizard />
        <UnlockModal />
        <CommandPalette />
      </div>
    </div>
  );
}
