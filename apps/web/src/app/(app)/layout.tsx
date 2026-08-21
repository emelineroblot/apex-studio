"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import { useAuth } from "@/lib/auth/AuthProvider";
import { groupNavItemsForRole, isNavItemActive, NAV_ITEMS } from "@/lib/nav";
import { ROLE_LABELS } from "@/lib/labels";
import { Spinner } from "@/components/ui/States";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  // La barre latérale devient persistante à partir de `lg` (1024px) : en dessous, quatorze
  // entrées réparties sur plusieurs sections ne tiennent pas à côté du contenu applicatif,
  // et le drawer passe en tiroir superposé. Connu seulement côté client (`matchMedia`) ; faux
  // par défaut le temps du premier rendu, sans conséquence visuelle puisque `lg:translate-x-0`
  // gère déjà l'affichage par CSS pur — cet état ne sert qu'à piloter le focus (`inert`).
  const [isDesktop, setIsDesktop] = useState(false);

  useEffect(() => {
    if (user === null) router.replace("/login");
  }, [user, router]);

  // Le drawer mobile se referme sur Échap, en plus du clic sur le fond et de la navigation
  // (onClick sur chaque lien, plus bas) — trois façons cohérentes de sortir du menu.
  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  // Fermer le drawer au franchissement du point de rupture évite un overlay fantôme si
  // l'utilisateur redimensionne la fenêtre pendant qu'il est ouvert.
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1024px)");
    setIsDesktop(query.matches);
    const onChange = (event: MediaQueryListEvent) => {
      setIsDesktop(event.matches);
      setMenuOpen(false);
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

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

  const groups = groupNavItemsForRole(NAV_ITEMS, user.role);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen bg-ink-50 lg:flex">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent-600 focus:px-4 focus:py-2 focus:text-white"
      >
        Aller au contenu
      </a>

      {/* Barre du haut, mobile/tablette uniquement : logo + bouton d'ouverture du drawer. */}
      <div className="flex items-center justify-between border-b border-ink-800 bg-ink-950 px-4 py-3 lg:hidden">
        <Link href="/dashboard" className="flex items-center gap-2 text-white">
          <span className="text-sm font-bold uppercase tracking-[0.25em] text-accent-500">Apex</span>
          <span className="hidden text-xs text-ink-400 sm:inline">Studio photo motorsport</span>
        </Link>
        <button
          type="button"
          className="rounded-md p-2 text-ink-300 hover:bg-ink-800"
          aria-expanded={menuOpen}
          aria-controls="primary-nav"
          onClick={() => setMenuOpen((v) => !v)}
        >
          <span className="sr-only">Ouvrir la navigation</span>
          <span aria-hidden="true">☰</span>
        </button>
      </div>

      {/* Fond cliquable derrière le drawer mobile — deuxième façon de le refermer. */}
      {menuOpen ? (
        <div
          className="fixed inset-0 z-40 bg-ink-950/60 lg:hidden"
          onClick={() => setMenuOpen(false)}
          aria-hidden="true"
        />
      ) : null}

      <aside
        // Off-canvas et fermé (mobile/tablette) : `inert` retire tout le sous-arbre du focus
        // clavier et de l'arbre d'accessibilité, sans quoi les liens restent atteignables au
        // Tab bien qu'invisibles hors écran. Jamais appliqué sur `lg`, où la barre est fixe.
        inert={!isDesktop && !menuOpen ? true : undefined}
        className={clsx(
          "fixed inset-y-0 left-0 z-50 flex w-72 shrink-0 -translate-x-full flex-col bg-ink-950 transition-transform duration-200 ease-out",
          "lg:static lg:z-auto lg:translate-x-0",
          menuOpen && "translate-x-0",
        )}
      >
        <div className="flex items-center justify-between gap-2 border-b border-ink-800 px-5 py-4">
          <Link href="/dashboard" className="flex items-center gap-2 text-white" onClick={() => setMenuOpen(false)}>
            <span className="text-sm font-bold uppercase tracking-[0.25em] text-accent-500">Apex</span>
            <span className="text-xs text-ink-400">Studio photo motorsport</span>
          </Link>
          <button
            type="button"
            className="rounded-md p-2 text-ink-300 hover:bg-ink-800 lg:hidden"
            onClick={() => setMenuOpen(false)}
          >
            <span className="sr-only">Fermer la navigation</span>
            <span aria-hidden="true">✕</span>
          </button>
        </div>

        <nav id="primary-nav" aria-label="Navigation principale" className="flex-1 overflow-y-auto px-3 py-4">
          {groups.map((group, index) => (
            <div key={group.section ?? "top"} className={index > 0 ? "mt-6" : undefined}>
              {group.label ? (
                <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wider text-ink-500">
                  {group.label}
                </p>
              ) : null}
              <ul className="flex flex-col gap-1">
                {group.items.map((item) => {
                  const active = isNavItemActive(pathname, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        onClick={() => setMenuOpen(false)}
                        className={clsx(
                          "block rounded-md px-3 py-2 text-sm font-medium transition-colors",
                          active
                            ? "bg-accent-600 text-white"
                            : "text-ink-300 hover:bg-ink-800 hover:text-white",
                        )}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-ink-800 px-4 py-4">
          <p className="truncate text-sm font-medium text-ink-100">{user.full_name}</p>
          <p className="text-xs text-ink-400">{ROLE_LABELS[user.role]}</p>
          <button
            type="button"
            onClick={handleLogout}
            className="mt-3 w-full rounded-md border border-ink-700 px-3 py-1.5 text-sm text-ink-200 hover:bg-ink-800"
          >
            Se déconnecter
          </button>
        </div>
      </aside>

      <main id="main-content" className="mx-auto w-full max-w-7xl min-w-0 flex-1 px-4 py-8 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}
