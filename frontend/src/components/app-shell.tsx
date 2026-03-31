"use client";

import {
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  UserButton,
} from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

interface AppShellProps {
  children: React.ReactNode;
  /** Optional action in the top bar (e.g. Webhook button) */
  topAction?: React.ReactNode;
}

const NAV = [
  { href: "/", label: "Scrape", hint: "Find leads" },
  { href: "/history", label: "History", hint: "Past jobs" },
  { href: "/releases", label: "Releases", hint: "What's new" },
];

/**
 * App chrome: charcoal sidebar + stone workspace.
 */
export function AppShell({ children, topAction }: AppShellProps) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="shell-main flex min-h-screen">
      {mobileOpen ? (
        <button
          type="button"
          aria-label="Close menu"
          className="drawer-backdrop lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}

      <aside
        className={`shell-sidebar fixed inset-y-0 left-0 z-50 flex w-60 flex-col lg:static lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div
          className="px-5 py-6"
          style={{ borderBottom: "1px solid color-mix(in srgb, #F4F4F5 15%, transparent)" }}
        >
          <p className="font-display text-xl font-semibold tracking-tight">
            Intent Engine
          </p>
          <p className="mt-1 text-xs" style={{ opacity: 0.55 }}>
            B2B lead generation
          </p>
        </div>

        <nav className="flex flex-1 flex-col gap-1 px-3 py-4">
          {NAV.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={`rounded-sm px-3 py-2.5 text-sm ${
                  active ? "nav-active" : "nav-idle"
                }`}
              >
                <span className="block">{item.label}</span>
                <span
                  className="block text-xs font-normal"
                  style={{ opacity: active ? 0.55 : 0.45 }}
                >
                  {item.hint}
                </span>
              </Link>
            );
          })}
        </nav>

        <div
          className="px-4 py-4"
          style={{ borderTop: "1px solid color-mix(in srgb, #F4F4F5 15%, transparent)" }}
        >
          <SignedOut>
            <div className="flex flex-col gap-2">
              <SignInButton mode="modal">
                <button type="button" className="btn-sidebar-ghost">
                  Sign in
                </button>
              </SignInButton>
              <SignUpButton mode="modal">
                <button type="button" className="btn-sidebar-solid">
                  Sign up
                </button>
              </SignUpButton>
            </div>
          </SignedOut>
          <SignedIn>
            <div className="flex items-center gap-3">
              <UserButton afterSignOutUrl="/sign-in" />
              <span className="text-xs" style={{ opacity: 0.55 }}>
                Account
              </span>
            </div>
          </SignedIn>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="shell-topbar flex items-center justify-between px-4 py-3 lg:px-8">
          <button
            type="button"
            className="btn-ghost lg:hidden"
            onClick={() => setMobileOpen(true)}
          >
            Menu
          </button>
          <p className="hidden text-sm opacity-55 lg:block">Workspace</p>
          <div className="flex items-center gap-2">{topAction}</div>
        </header>

        <main className="flex-1 px-4 py-8 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
