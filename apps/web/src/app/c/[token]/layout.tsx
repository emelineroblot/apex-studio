import type { Metadata } from "next";

/**
 * Layout **autonome** de l'espace client (§3-L.3, frontend J3).
 *
 * Aucun composant de navigation du back-office n'est importé ici, et rien de `lib/auth`
 * n'est atteignable depuis cet arbre : le client externe ne doit voir ni la barre latérale
 * du studio, ni ses libellés, ni un lien qui l'y renverrait. C'est un cloisonnement visuel
 * autant que technique — un client qui aperçoit « File de validation » ou « Quarantaine »
 * dans un menu comprend qu'il regarde un outil interne, pas une galerie faite pour lui.
 *
 * Volontairement un composant serveur sans état : la session client vit dans les pages,
 * jamais dans le layout, pour qu'un lien mort n'ait pas à traverser deux niveaux avant
 * d'atteindre son écran dédié.
 */
export const metadata: Metadata = {
  title: "Votre galerie",
  description: "Sélectionnez les photos que vous souhaitez recevoir.",
  // Une galerie client n'a rien à faire dans un moteur de recherche : le lien est un
  // secret, l'indexer le rendrait public.
  robots: { index: false, follow: false },
};

export default function ClientSpaceLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-ink-50">{children}</div>;
}
