import type { Role } from "@/lib/api/types";

/**
 * Regroupement des entrées dans la barre latérale. Quatre familles distinctes par statut
 * métier (§ mission « Navigation latérale ») :
 * - `daily` — le travail quotidien du pipeline (shootings → dépôt → bibliothèque → file de
 *   validation → recherche → collections) ;
 * - `billing` — la facturation, en aval de la sélection client (devis, factures) ;
 * - `catalog` — le référentiel stable (clients, circuits, pilotes, écuries, boîtiers), qui se
 *   consulte plus qu'il ne se manipule au jour le jour ;
 * - `settings` — la configuration technique du pipeline (seuils OCR), réservée au dirigeant.
 * `undefined` marque une entrée hors section, épinglée seule en tête de barre (tableau de bord).
 */
export type NavSectionId = "daily" | "billing" | "catalog" | "settings";

export const NAV_SECTION_ORDER: NavSectionId[] = ["daily", "billing", "catalog", "settings"];

export const NAV_SECTION_LABELS: Record<NavSectionId, string> = {
  daily: "Travail quotidien",
  billing: "Facturation",
  catalog: "Catalogue",
  settings: "Réglages",
};

export type NavItem = {
  href: string;
  label: string;
  /** Rôles autorisés à voir l'entrée. §3-I du plan — cloisonnement souple côté UI, le
   * backend reste la seule porte faisant autorité. */
  roles: Role[];
  /** Section d'appartenance dans la barre latérale ; absente pour une entrée hors section. */
  section?: NavSectionId;
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Tableau de bord", roles: ["owner", "photographer"] },
  { href: "/shootings", label: "Shootings", roles: ["owner", "photographer"], section: "daily" },
  { href: "/upload", label: "Dépôt de photos", roles: ["owner", "photographer"], section: "daily" },
  { href: "/library", label: "Bibliothèque", roles: ["owner", "photographer"], section: "daily" },
  { href: "/review", label: "File de validation", roles: ["owner", "photographer"], section: "daily" },
  { href: "/search", label: "Recherche", roles: ["owner", "photographer"], section: "daily" },
  { href: "/collections", label: "Collections", roles: ["owner", "photographer"], section: "daily" },
  { href: "/quotes", label: "Devis", roles: ["owner"], section: "billing" },
  { href: "/invoices", label: "Factures", roles: ["owner"], section: "billing" },
  { href: "/clients", label: "Clients", roles: ["owner", "photographer"], section: "catalog" },
  { href: "/circuits", label: "Circuits", roles: ["owner", "photographer"], section: "catalog" },
  { href: "/drivers", label: "Pilotes", roles: ["owner", "photographer"], section: "catalog" },
  { href: "/teams", label: "Écuries", roles: ["owner", "photographer"], section: "catalog" },
  { href: "/cameras", label: "Boîtiers", roles: ["owner"], section: "catalog" },
  { href: "/settings/ocr", label: "Seuils OCR", roles: ["owner"], section: "settings" },
];

/**
 * Une entrée est active sur sa route exacte ou toute sous-route (`/collections/12/share`
 * marque « Collections »). Extrait en fonction pure et testée : c'est le seul calcul de ce
 * fichier qui n'est pas une simple donnée statique.
 */
export function isNavItemActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export type NavGroup = {
  section: NavSectionId | undefined;
  label: string | undefined;
  items: NavItem[];
};

/**
 * Filtre par rôle puis regroupe par section, dans l'ordre `NAV_SECTION_ORDER`. Le groupe
 * sans section (tableau de bord) sort toujours en premier ; une section sans entrée visible
 * pour le rôle courant (ex. Facturation pour un photographe) n'apparaît pas.
 */
export function groupNavItemsForRole(items: NavItem[], role: Role): NavGroup[] {
  const visible = items.filter((item) => item.roles.includes(role));
  const groups: NavGroup[] = [];

  const unsectioned = visible.filter((item) => item.section === undefined);
  if (unsectioned.length > 0) {
    groups.push({ section: undefined, label: undefined, items: unsectioned });
  }

  for (const section of NAV_SECTION_ORDER) {
    const sectionItems = visible.filter((item) => item.section === section);
    if (sectionItems.length > 0) {
      groups.push({ section, label: NAV_SECTION_LABELS[section], items: sectionItems });
    }
  }

  return groups;
}
