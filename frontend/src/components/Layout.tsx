import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Boxes,
  CircleHelp,
  Copy,
  FileStack,
  FileText,
  GitCompare,
  LayoutGrid,
  Menu,
  Settings,
  Upload,
  X,
} from "lucide-react";
import { cn } from "../lib/utils";
import { useHealth } from "../hooks/queries";
import { IconButton } from "./ui";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  /** Exact match required — used for the index route. */
  end?: boolean;
}

interface NavSection {
  title?: string;
  items: NavItem[];
}

const NAV: NavSection[] = [
  {
    items: [
      { to: "/", label: "Dashboard", icon: <LayoutGrid />, end: true },
      { to: "/documents", label: "Documents", icon: <FileText /> },
      { to: "/upload", label: "Upload", icon: <Upload /> },
    ],
  },
  {
    title: "Analysis",
    items: [
      { to: "/compare", label: "Compare", icon: <GitCompare /> },
      { to: "/duplicates", label: "Duplicates", icon: <Copy /> },
      { to: "/templates", label: "Templates", icon: <FileStack /> },
      { to: "/reports", label: "Reports", icon: <Boxes /> },
    ],
  },
  {
    title: "Config",
    items: [
      { to: "/settings", label: "Settings", icon: <Settings /> },
    ],
  },
];

function NavRow({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn("dt-nav-item", isActive && "dt-nav-item-active")
      }
    >
      <span className="shrink-0 [&>svg]:h-4 [&>svg]:w-4">{item.icon}</span>
      <span className="truncate">{item.label}</span>
    </NavLink>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { data: health } = useHealth();
  const dbOk = health?.database === "ok";

  return (
    <div className="flex h-full flex-col bg-canvas">
      {/* Workspace header */}
      <div className="flex h-[52px] shrink-0 items-center gap-2.5 border-b border-line px-4">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-brand text-[11px] font-bold text-txt-inverse">
          D
        </span>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold leading-tight text-txt">DocuTrace</p>
          <p className="truncate text-[10.5px] leading-tight text-txt-faint">
            Verification workspace
          </p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2.5 py-3">
        {NAV.map((section, index) => (
          <div key={section.title ?? `section-${index}`} className={index > 0 ? "mt-4" : undefined}>
            {section.title ? (
              <p className="px-2.5 pb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-txt-faint">
                {section.title}
              </p>
            ) : null}
            <ul className="space-y-0.5">
              {section.items.map((item) => (
                <li key={item.to}>
                  <NavRow item={item} onNavigate={onNavigate} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="shrink-0 space-y-0.5 border-t border-line px-2.5 py-2.5">
        <a
          href="http://127.0.0.1:8000/docs"
          target="_blank"
          rel="noreferrer"
          className="dt-nav-item"
        >
          <span className="shrink-0 [&>svg]:h-4 [&>svg]:w-4">
            <CircleHelp />
          </span>
          <span className="truncate">API Docs</span>
        </a>
        <div className="flex items-center gap-2 px-2.5 pt-1.5">
          <span
            className={cn(
              "h-1.5 w-1.5 shrink-0 rounded-full",
              dbOk ? "bg-pill-green-txt" : "bg-pill-amber-txt"
            )}
          />
          <span className="truncate text-[10.5px] text-txt-faint">
            {health ? `v${health.version} · db ${health.database}` : "Connecting…"}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  // Close the drawer on navigation.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  // Lock body scroll while the drawer is open.
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [mobileOpen]);

  return (
    <div className="flex min-h-screen bg-canvas-soft">
      {/* Desktop sidebar — fixed, ~200px */}
      <aside className="sticky top-0 hidden h-screen w-[200px] shrink-0 border-r border-line lg:block">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-txt/25 animate-fade-in"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="absolute inset-y-0 left-0 w-[240px] border-r border-line shadow-pop animate-slide-in-right">
            <div className="absolute right-2 top-3 z-10">
              <IconButton label="Close navigation" onClick={() => setMobileOpen(false)}>
                <X className="h-4 w-4" />
              </IconButton>
            </div>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex h-[52px] items-center gap-2 border-b border-line bg-canvas px-3 lg:hidden">
          <IconButton label="Open navigation" onClick={() => setMobileOpen(true)}>
            <Menu className="h-4 w-4" />
          </IconButton>
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-brand text-[11px] font-bold text-txt-inverse">
            D
          </span>
          <p className="text-[13px] font-semibold text-txt">DocuTrace</p>
        </header>

        <main className="min-w-0 flex-1">
          <div className="mx-auto max-w-[1240px] px-5 py-6 sm:px-6 lg:px-8 lg:py-7">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
