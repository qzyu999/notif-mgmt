import type { ButtonHTMLAttributes, ReactNode } from "react";

export type BadgeTone =
  | "evidence"
  | "inference"
  | "confirmed"
  | "candidate"
  | "withdrawn"
  | "neutral";

export function SemanticBadge({
  tone,
  children,
}: {
  tone: BadgeTone;
  children: ReactNode;
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "quiet" | "danger";
}) {
  return (
    <button
      type="button"
      {...props}
      className={`button button-${variant} ${className}`.trim()}
    />
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="state state-loading" aria-live="polite">
      {label}
    </p>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <p className="state state-error" role="alert">
      {message}
    </p>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="state state-empty">{children}</p>;
}
