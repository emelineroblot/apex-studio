import { describe, expect, it } from "vitest";
import {
  NAV_ITEMS,
  NAV_SECTION_ORDER,
  groupNavItemsForRole,
  isNavItemActive,
  type NavItem,
} from "@/lib/nav";

describe("isNavItemActive", () => {
  it("marque actif sur la route exacte", () => {
    expect(isNavItemActive("/collections", "/collections")).toBe(true);
  });

  it("marque actif sur une sous-route", () => {
    expect(isNavItemActive("/collections/12/share", "/collections")).toBe(true);
  });

  it("ne marque pas actif un préfixe partiel non séparé par un slash", () => {
    // /reviews ne doit pas activer l'entrée /review.
    expect(isNavItemActive("/reviews", "/review")).toBe(false);
  });

  it("ne marque pas actif une route indépendante", () => {
    expect(isNavItemActive("/dashboard", "/collections")).toBe(false);
  });
});

describe("groupNavItemsForRole", () => {
  it("filtre par rôle avant de regrouper — un photographe ne voit pas les entrées réservées au dirigeant", () => {
    const groups = groupNavItemsForRole(NAV_ITEMS, "photographer");
    const allItems = groups.flatMap((g) => g.items);
    expect(allItems.some((item) => item.href === "/quotes")).toBe(false);
    expect(allItems.some((item) => item.href === "/invoices")).toBe(false);
    expect(allItems.some((item) => item.href === "/cameras")).toBe(false);
    expect(allItems.some((item) => item.href === "/settings/ocr")).toBe(false);
  });

  it("place le groupe sans section (tableau de bord) en tête", () => {
    const groups = groupNavItemsForRole(NAV_ITEMS, "owner");
    expect(groups[0]?.section).toBeUndefined();
    expect(groups[0]?.items.map((i) => i.href)).toEqual(["/dashboard"]);
  });

  it("respecte l'ordre NAV_SECTION_ORDER pour les sections suivantes", () => {
    const groups = groupNavItemsForRole(NAV_ITEMS, "owner");
    const sectionIds = groups.map((g) => g.section).filter((s): s is (typeof NAV_SECTION_ORDER)[number] => s !== undefined);
    const expectedOrder = NAV_SECTION_ORDER.filter((s) => sectionIds.includes(s));
    expect(sectionIds).toEqual(expectedOrder);
  });

  it("omet une section entièrement invisible pour le rôle courant", () => {
    const items: NavItem[] = [
      { href: "/dashboard", label: "Tableau de bord", roles: ["owner", "photographer"] },
      { href: "/quotes", label: "Devis", roles: ["owner"], section: "billing" },
    ];
    const groups = groupNavItemsForRole(items, "photographer");
    expect(groups.some((g) => g.section === "billing")).toBe(false);
  });

  it("couvre toutes les entrées de NAV_ITEMS sans perte ni duplication", () => {
    const groups = groupNavItemsForRole(NAV_ITEMS, "owner");
    const hrefs = groups.flatMap((g) => g.items.map((i) => i.href)).sort();
    expect(hrefs).toEqual([...NAV_ITEMS.map((i) => i.href)].sort());
  });
});
