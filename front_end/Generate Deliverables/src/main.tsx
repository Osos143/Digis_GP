import React, { Component, ErrorInfo, ReactNode } from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('NetFix Platform Uncaught Error:', error, errorInfo);
  }

  private handleReset = () => {
    try {
      localStorage.removeItem('netfix_current_view');
    } catch (e) {}
    window.location.reload();
  };

  private handleClearAll = () => {
    try {
      localStorage.clear();
    } catch (e) {}
    window.location.href = '/';
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-slate-900 text-slate-100 flex items-center justify-center p-6 font-sans">
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 max-w-xl w-full shadow-2xl space-y-6 text-center">
            <div className="w-16 h-16 bg-rose-500/10 border border-rose-500/30 rounded-2xl flex items-center justify-center mx-auto text-rose-400 text-3xl">
              ⚠️
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Platform Exception Encountered</h1>
              <p className="text-sm text-slate-400 mt-2">
                NetFix encountered an unexpected rendering runtime error.
              </p>
            </div>

            {this.state.error && (
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-left overflow-x-auto max-h-40">
                <p className="text-xs font-mono text-rose-400 font-semibold">{this.state.error.name}: {this.state.error.message}</p>
                {this.state.error.stack && (
                  <pre className="text-[11px] font-mono text-slate-400 mt-2 whitespace-pre-wrap">{this.state.error.stack}</pre>
                )}
              </div>
            )}

            <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
              <button
                onClick={this.handleReset}
                className="w-full sm:flex-1 bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-5 rounded-xl text-sm transition-all shadow-md cursor-pointer"
              >
                Reload Dashboard
              </button>
              <button
                onClick={this.handleClearAll}
                className="w-full sm:flex-1 bg-slate-700 hover:bg-slate-600 text-slate-200 font-bold py-3 px-5 rounded-xl text-sm transition-all border border-slate-600 cursor-pointer"
              >
                Reset Session & Login
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
