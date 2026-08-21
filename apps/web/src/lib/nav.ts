import type { Role } from "@/lib/api/types";

export type NavItem = {
  href: string;
  label: string;
  /** Rôles autorisés à voir l'entrée. §3-I du plan — cloisonnement souple côté UI, le
   * backend reste la seule porte faisant autorité. */
  roles: Role[];
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Tableau de bord", roles: ["owner", "photographer"] },
  { href: "/shootings", label: "Shootings", roles: ["owner", "photographer"] },
  { href: "/upload", label: "Dépôt de photos", roles: ["owner", "photographer"] },
  { href: "/library", label: "Bibliothèque", roles: ["owner", "photographer"] },
  { href: "/search", label: "Recherche", roles: ["owner", "photographer"] },
  { href: "/review", label: "File de validation", roles: ["owner", "photographer"] },
  { href: "/collections", label: "Collections", roles: ["owner", "photographer"] },
  { href: "/quotes", label: "Devis", roles: ["owner"] },
  { href: "/invoices", label: "Factures", roles: ["owner"] },
  { href: "/clients", label: "Clients", roles: ["owner", "photographer"] },
  { href: "/circuits", label: "Circuits", roles: ["owner", "photographer"] },
  { href: "/drivers", label: "Pilotes", roles: ["owner", "photographer"] },
  { href: "/teams", label: "Écuries", roles: ["owner", "photographer"] },
  { href: "/cameras", label: "Boîtiers", roles: ["owner"] },
  { href: "/settings/ocr", label: "Seuils OCR", roles: ["owner"] },
];
