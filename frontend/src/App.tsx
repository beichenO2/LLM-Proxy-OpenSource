import { Component, type ComponentType, type ErrorInfo, lazy, type ReactNode, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";

class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-neutral-50 p-8">
          <div className="w-full max-w-md rounded-xl border border-red-200 bg-white p-8 text-center shadow-sm">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-500">
              <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-neutral-900">页面出错了</h2>
            <p className="mt-2 text-sm text-neutral-500">{this.state.error.message}</p>
            <button
              type="button"
              className="mt-6 rounded-lg bg-neutral-900 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-800"
              onClick={() => {
                this.setState({ error: null });
                window.location.href = "/";
              }}
            >
              返回首页
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ProjectsPage = lazy(() => import("./pages/ProjectsPage"));
const SecretsPage = lazy(() => import("./pages/SecretsPage"));
const BindingsPage = lazy(() => import("./pages/BindingsPage"));
const TestCenterPage = lazy(() => import("./pages/TestCenterPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const LogsPage = lazy(() => import("./pages/LogsPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const UsagePage = lazy(() => import("./pages/UsagePage"));
const AboutPage = lazy(() => import("./pages/AboutPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

function PageFallback() {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-900" />
    </div>
  );
}

/** Wrap a lazy component (with optional props) in shared Suspense boundary. */
function lazy$<P extends Record<string, unknown>>(
  Component: ComponentType<P>,
  props?: P,
): ReactNode {
  return (
    <Suspense fallback={<PageFallback />}>
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <Component {...(props as any)} />
    </Suspense>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={lazy$(DashboardPage)} />
        <Route path="projects" element={lazy$(ProjectsPage)} />
        <Route path="secrets" element={lazy$(SecretsPage)} />
        <Route path="bindings" element={lazy$(BindingsPage)} />
        <Route path="test-center" element={lazy$(TestCenterPage)} />
        <Route path="settings" element={lazy$(SettingsPage)} />
        <Route path="users" element={lazy$(UsersPage)} />
        <Route path="logs" element={lazy$(LogsPage)} />
        <Route path="usage" element={lazy$(UsagePage)} />
        <Route path="about" element={lazy$(AboutPage)} />
        <Route path="*" element={lazy$(NotFoundPage)} />
      </Route>
    </Routes>
    </ErrorBoundary>
  );
}
