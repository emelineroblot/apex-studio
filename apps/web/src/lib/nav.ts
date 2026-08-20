import type { Role } from "@/lib/api/types";

export type NavItem = {
  href: string;
  label: string;
  /** Rôles autorisés à voir l'entrée. §3-I du plan — cloisonnement souple côté UI, le
   * backend reste la seule porte faisant autorité. */
  roles: Role[];
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/shootings", label: "Shootings", roles: ["owner", "photographer"] },
  { href: "/upload", label: "Dépôt de photos", roles: ["owner", "photographer"] },
  { href: "/library", label: "Bibliothèque", roles: ["owner", "photographer"] },
  { href: "/clients", label: "Clients", roles: ["owner", "photographer"] },
  { href: "/circuits", label: "Circuits", roles: ["owner", "photographer"] },
  { href: "/drivers", label: "Pilotes", roles: ["owner", "photographer"] },
  { href: "/teams", label: "Écuries", roles: ["owner", "photographer"] },
  { href: "/cameras", label: "Boîtiers", roles: ["owner"] },
];
