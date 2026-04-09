import React from "react";

interface State { hasError: boolean; message?: string }

export class ErrorBoundary extends React.Component<React.PropsWithChildren<unknown>, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: unknown): State {
    const message = error instanceof Error ? error.message : String(error);
    return { hasError: true, message };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 text-red-400">
          <h2 className="text-xl font-bold">Something went wrong.</h2>
          <pre className="mt-2 text-sm">{this.state.message}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}
