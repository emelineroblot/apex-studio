"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import { useAuth } from "@/lib/auth/AuthProvider";
import { NAV_ITEMS } from "@/lib/nav";
import { ROLE_LABELS } from "@/lib/labels";
import { Spinner } from "@/components/ui/States";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (user === null) router.replace("/login");
  }, [user, router]);

  if (user === undefined) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Vérification de la session…" />
      </div>
    );
  }
  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Redirection vers la connexion…" />
      </div>
    );
  }

  const items = NAV_ITEMS.filter((item) => item.roles.includes(user.role));

  return (
    <div className="min-h-screen bg-ink-50">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent-600 focus:px-4 focus:py-2 focus:text-white"
      >
        Aller au contenu
      </a>
      <header className="border-b border-ink-100 bg-ink-950">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-6">
            <Link href="/shootings" className="flex items-center gap-2 text-white">
              <span className="text-sm font-bold uppercase tracking-[0.25em] text-accent-500">Apex</span>
              <span className="hidden text-xs text-ink-400 sm:inline">Studio photo motorsport</span>
            </Link>
            <button
              type="button"
              className="rounded-md p-2 text-ink-300 hover:bg-ink-800 sm:hidden"
              aria-expanded={menuOpen}
              aria-controls="primary-nav"
              onClick={() => setMenuOpen((v) => !v)}
            >
              <span className="sr-only">Ouvrir la navigation</span>
              ☰
            </button>
            <nav
              id="primary-nav"
              aria-label="Navigation principale"
              className={clsx(
                "flex-col gap-1 sm:flex sm:flex-row sm:gap-1",
                menuOpen ? "flex" : "hidden",
              )}
            >
              {items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setMenuOpen(false)}
                    className={clsx(
                      "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                      active ? "bg-accent-600 text-white" : "text-ink-300 hover:bg-ink-800 hover:text-white",
                    )}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right text-xs text-ink-400 sm:block">
              <p className="font-medium text-ink-100">{user.full_name}</p>
              <p>{ROLE_LABELS[user.role]}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                logout();
                router.replace("/login");
              }}
              className="rounded-md border border-ink-700 px-3 py-1.5 text-sm text-ink-200 hover:bg-ink-800"
            >
              Se déconnecter
            </button>
          </div>
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {children}
      </main>
    </div>
  );
}
