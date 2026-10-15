import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time errors so a broken page shows a readable message instead
 * of a blank white screen.
 *
 * Without this, any uncaught exception during render unmounts the entire React
 * tree and leaves `#root` empty — which is indistinguishable from "the app is
 * broken" and gives no clue what went wrong.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the full stack in the console for debugging.
    console.error("DocuTrace render error:", error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas-soft px-6">
        <div className="w-full max-w-[560px] rounded-card border border-line bg-canvas p-6">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-control bg-pill-rose text-pill-rose-txt">
              <AlertTriangle className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <h1 className="text-[15px] font-semibold text-txt">
                Something went wrong on this page
              </h1>
              <p className="mt-1 text-[13px] leading-relaxed text-txt-muted">
                The page could not be rendered. The rest of the app is unaffected —
                navigate elsewhere, or reload to try again.
              </p>
            </div>
          </div>

          <pre className="mt-4 max-h-[180px] overflow-auto whitespace-pre-wrap rounded-panel border border-line bg-canvas-section p-3 font-mono text-[12px] leading-relaxed text-txt-muted">
            {error.message || String(error)}
          </pre>

          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" className="dt-btn-primary" onClick={() => window.location.reload()}>
              <RotateCcw className="h-4 w-4" />
              Reload
            </button>
            <a
              className="dt-btn-secondary"
              href="/"
              onClick={this.reset}
            >
              Go to dashboard
            </a>
          </div>
        </div>
      </div>
    );
  }
}
