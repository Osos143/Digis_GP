// src/netpulse/ui.tsx
//
// Small shared primitives so every Network Pulse page reuses the exact
// same look as the rest of NetFix (bg-[var(--color-surface)] card style,
// same border/shadow/radius, same primary button) instead of each page
// re-inventing it slightly differently.

import type { ReactNode, ButtonHTMLAttributes } from 'react';

export const Card = ({ className = '', children }: { className?: string; children: ReactNode }) => (
  <div className={`bg-[var(--color-surface)] rounded border border-[var(--color-border)] shadow-sm ${className}`}>
    {children}
  </div>
);

export const AccentHeader = ({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) => (
  <div className="relative overflow-hidden rounded-2xl border border-primary/15 bg-white/85 px-4 py-3 shadow-sm">
    <div className="absolute -right-6 -top-6 h-16 w-16 rounded-full bg-primary/10" />
    <div className="absolute -left-8 -bottom-8 h-20 w-20 rotate-12 rounded-2xl bg-secondary/15" />
    <div className="relative flex items-start justify-between gap-3 flex-wrap">
      <div className="flex items-start gap-3">
        <div className="w-2 self-stretch rounded-full bg-gradient-to-b from-primary to-secondary shrink-0" />
        <div>
          <div className="text-base font-bold text-slate-800">{title}</div>
          {subtitle && <div className="text-xs text-slate-600 mt-1">{subtitle}</div>}
        </div>
      </div>
      {actions}
    </div>
  </div>
);

export const FeatureCard = ({ className = '', children }: { className?: string; children: ReactNode }) => (
  <Card className={`relative overflow-hidden border-slate-200 bg-[linear-gradient(135deg,#f8fbff_0%,#eef4ff_42%,#ffffff_100%)] shadow-[0_24px_65px_-28px_rgba(15,23,42,0.5)] ${className}`}>
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(21,101,192,0.16),_transparent_45%),radial-gradient(circle_at_bottom_right,_rgba(0,172,193,0.12),_transparent_40%)]" />
    <div className="relative">{children}</div>
  </Card>
);

export const PageHeader = ({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) => (
  <div className="flex items-center justify-between">
    <div>
      <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">{title}</h2>
      {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
    </div>
    {actions && <div className="flex gap-3">{actions}</div>}
  </div>
);

export const PrimaryButton = ({ children, className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) => (
  <button
    className={`flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded text-sm font-medium hover:opacity-90 shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
    {...rest}
  >
    {children}
  </button>
);

export const SecondaryButton = ({ children, className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) => (
  <button
    className={`flex items-center gap-2 bg-white border border-[var(--color-border)] px-4 py-2 rounded text-sm font-medium hover:bg-gray-50 shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
    {...rest}
  >
    {children}
  </button>
);

export const Pill = ({ tone, children }: { tone: 'pass' | 'fail' | 'neutral'; children: ReactNode }) => {
  const cls =
    tone === 'pass' ? 'bg-green-50 text-[var(--color-success)] border-green-200' :
    tone === 'fail' ? 'bg-red-50 text-[var(--color-critical)] border-red-200' :
    'bg-gray-50 text-gray-600 border-gray-200';
  return <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold border ${cls}`}>{children}</span>;
};

export const StatCard = ({
  label, value, sub, hint, tone = 'neutral', icon: Icon,
}: { label: string; value: string | number; sub?: string; hint?: string; tone?: 'hero' | 'hard' | 'soft' | 'neutral'; icon?: any }) => {
  const barColor =
    tone === 'hero' ? 'bg-gradient-to-b from-[var(--color-primary)] to-[var(--color-secondary)]' :
    tone === 'hard' ? 'bg-[var(--color-critical)]' :
    tone === 'soft' ? 'bg-[var(--color-warning)]' : 'bg-gray-300';
  return (
    <div title={hint} className="relative overflow-hidden bg-[var(--color-surface)] rounded border border-[var(--color-border)] shadow-sm p-4 pl-5 cursor-default">
      <span className={`absolute left-0 top-0 bottom-0 w-1 ${barColor}`} />
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</span>
        {Icon && <Icon className="w-4 h-4 text-gray-400" />}
      </div>
      <div className="text-2xl font-bold text-[var(--color-text)] mt-2">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
};

export const LoadingBlock = ({ label = 'Loading...' }: { label?: string }) => (
  <div className="flex items-center justify-center h-64 text-sm text-gray-500 gap-2">
    <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    {label}
  </div>
);

export const ErrorBlock = ({ message }: { message: string }) => (
  <div className="bg-red-50 border border-red-200 text-[var(--color-critical)] rounded p-4 text-sm">
    <b>Couldn't load this data.</b> {message}
    <div className="text-xs text-red-500 mt-1">Is the Network Pulse API running at the configured VITE_API_URL (default http://localhost:8000)?</div>
  </div>
);
