/**
 * Shared UI primitives.
 *
 * Small, dependency-light components that mirror the reference design language:
 * flat white surfaces, 1px subtle borders, 12–14px radii, royal-blue accent and
 * compact information density. Icons come from lucide-react at 16px with a
 * 1.75 stroke weight to match the reference's small outline icons.
 */

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "../lib/utils";

// --------------------------------------------------------------------------- //
// Button
// --------------------------------------------------------------------------- //

type ButtonVariant = "primary" | "secondary" | "ghost";
type ButtonSize = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
}

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "border-brand bg-brand text-txt-inverse hover:bg-brand-hover active:bg-brand-active",
  secondary: "border-line bg-canvas text-txt hover:bg-canvas-hover",
  ghost: "border-transparent bg-transparent text-txt-muted hover:bg-canvas-hover hover:text-txt",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-[12.5px]",
  md: "h-8 px-3 text-[13px]",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", icon, className, children, ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-control border font-medium",
        "transition-colors duration-fast disabled:cursor-not-allowed disabled:opacity-50",
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className
      )}
      {...rest}
    >
      {icon ? <span className="shrink-0 [&>svg]:h-4 [&>svg]:w-4">{icon}</span> : null}
      {children}
    </button>
  );
});

// --------------------------------------------------------------------------- //
// IconButton
// --------------------------------------------------------------------------- //

export const IconButton = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { label: string }
>(function IconButton({ label, className, children, ...rest }, ref) {
  return (
    <button
      ref={ref}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-7 w-7 items-center justify-center rounded-md text-txt-faint",
        "transition-colors duration-fast hover:bg-canvas-hover hover:text-txt",
        className
      )}
      {...rest}
    >
      {children}
    </button>
  );
});

// --------------------------------------------------------------------------- //
// Surfaces
// --------------------------------------------------------------------------- //

export function Panel({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return <Tag className={cn("dt-panel", className)}>{children}</Tag>;
}

export function Card({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return <Tag className={cn("dt-card", className)}>{children}</Tag>;
}

/** Card header with an optional small outline icon, title and right-side actions. */
export function CardHeader({
  icon,
  title,
  subtitle,
  actions,
  className,
  bordered = true,
}: {
  icon?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
  bordered?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 px-4 py-3",
        bordered && "border-b border-line",
        className
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        {icon ? <span className="shrink-0 text-txt-muted [&>svg]:h-4 [&>svg]:w-4">{icon}</span> : null}
        <div className="min-w-0">
          <h3 className="truncate text-section font-semibold text-txt">{title}</h3>
          {subtitle ? <p className="mt-0.5 truncate text-meta text-txt-faint">{subtitle}</p> : null}
        </div>
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-1.5">{actions}</div> : null}
    </div>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("px-4 py-3.5", className)}>{children}</div>;
}

// --------------------------------------------------------------------------- //
// Status pill
// --------------------------------------------------------------------------- //

export type PillTone = "green" | "lavender" | "blue" | "amber" | "rose" | "slate";

const PILL_TONES: Record<PillTone, string> = {
  green: "bg-pill-green text-pill-green-txt",
  lavender: "bg-pill-lavender text-pill-lavender-txt",
  blue: "bg-pill-blue text-pill-blue-txt",
  amber: "bg-pill-amber text-pill-amber-txt",
  rose: "bg-pill-rose text-pill-rose-txt",
  slate: "bg-pill-slate text-pill-slate-txt",
};

export function StatusBadge({
  tone = "slate",
  children,
  className,
}: {
  tone?: PillTone;
  children: ReactNode;
  className?: string;
}) {
  return <span className={cn("dt-pill", PILL_TONES[tone], className)}>{children}</span>;
}

// --------------------------------------------------------------------------- //
// Avatar
// --------------------------------------------------------------------------- //

/** Deterministic initials avatar with a soft tinted background. */
export function Avatar({
  name,
  size = 24,
  className,
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  const palette = [
    "bg-[#DBEAFE] text-[#1D4ED8]",
    "bg-[#DCFCE7] text-[#166534]",
    "bg-[#F3E8FF] text-[#6B21A8]",
    "bg-[#FEF3C7] text-[#92400E]",
    "bg-[#FEE2E2] text-[#991B1B]",
    "bg-[#E0E7FF] text-[#3730A3]",
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  const tone = palette[hash % palette.length];

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        tone,
        className
      )}
      style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.4)) }}
      title={name}
    >
      {initials || "?"}
    </span>
  );
}

// --------------------------------------------------------------------------- //
// Feedback
// --------------------------------------------------------------------------- //

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 py-12 text-[13px] text-txt-faint">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line-strong border-t-brand" />
      {label}…
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      {icon ? (
        <span className="mb-1 flex h-9 w-9 items-center justify-center rounded-full bg-canvas-section text-txt-faint [&>svg]:h-[18px] [&>svg]:w-[18px]">
          {icon}
        </span>
      ) : null}
      <p className="text-[13.5px] font-semibold text-txt">{title}</p>
      {description ? (
        <p className="max-w-sm text-[12.5px] leading-relaxed text-txt-faint">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "Something went wrong.";
  return (
    <div className="rounded-card border border-pill-rose bg-pill-rose/40 px-4 py-3">
      <p className="text-[12.5px] font-semibold text-pill-rose-txt">Request failed</p>
      <p className="mt-0.5 text-[12.5px] text-txt-muted">{message}</p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Page header
// --------------------------------------------------------------------------- //

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow ? <p className="dt-label mb-1">{eyebrow}</p> : null}
        <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.02em] text-txt">
          {title}
        </h1>
        {description ? (
          <p className="mt-1 max-w-3xl text-[12.5px] leading-relaxed text-txt-muted">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

// --------------------------------------------------------------------------- //
// Metric
// --------------------------------------------------------------------------- //

export function StatTile({
  icon,
  label,
  value,
  hint,
}: {
  icon?: ReactNode;
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="dt-card px-4 py-3.5">
      <div className="flex items-center gap-1.5 text-txt-muted">
        {icon ? <span className="[&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span> : null}
        <p className="dt-label">{label}</p>
      </div>
      <p className="mt-1.5 text-[22px] font-semibold leading-none tracking-[-0.02em] text-txt">
        {value}
      </p>
      {hint ? <p className="mt-1.5 text-meta text-txt-faint">{hint}</p> : null}
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(1, value || 0));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-canvas-section">
      <div
        className="h-full rounded-full bg-brand transition-all duration-300"
        style={{ width: `${clamped * 100}%` }}
      />
    </div>
  );
}

export function KeyValue({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="dt-label">{item.label}</dt>
          <dd className="mt-0.5 truncate text-[12.5px] text-txt">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
