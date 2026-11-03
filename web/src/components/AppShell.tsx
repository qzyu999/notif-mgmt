import type { ReactNode } from "react";

const NAV_ITEMS = [
  { href: "#/today", label: "Today", route: "today" },
  { href: "#/people", label: "People", route: "people" },
  { href: "#/followups", label: "Follow-ups", route: "followups" },
  { href: "#/sources", label: "Sources", route: "sources" },
] as const;

function activeRoute(route: string): string {
  if (route.startsWith("#/people")) return "people";
  if (route.startsWith("#/followups")) return "followups";
  if (route.startsWith("#/sources")) return "sources";
  return "today";
}

export default function AppShell({
  route,
  children,
}: {
  route: string;
  children: ReactNode;
}) {
  const active = activeRoute(route);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <aside className="app-sidebar">
        <div className="brand-block">
          <p className="brand-eyebrow">Local-first</p>
          <p className="brand-name">Relationship Ledger</p>
          <p className="brand-note">Evidence first. Confirmation by you.</p>
        </div>
        <nav className="primary-nav" aria-label="Primary">
          <ul>
            {NAV_ITEMS.map((item) => (
              <li key={item.route}>
                <a
                  href={item.href}
                  aria-current={active === item.route ? "page" : undefined}
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <p className="shell-note">
          Notifications are evidence, not proof that a reply is owed.
        </p>
      </aside>
      <div className="app-main" id="main-content" tabIndex={-1}>
        {children}
      </div>
    </div>
  );
}
