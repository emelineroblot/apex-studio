/**
 * « Ce lien n'est plus valide » — écran dédié, exigé par le brief comme critère
 * d'acceptation à part entière.
 *
 * Ton métier, aucune trace technique : ni code d'erreur, ni statut HTTP, ni nom de route.
 * Un client qui tombe ici n'a rien fait de mal — son lien a expiré ou a été révoqué — et
 * la seule chose utile qu'on puisse lui donner, c'est le moyen de joindre le studio.
 *
 * Composant serveur volontairement statique : cette page doit s'afficher même quand rien
 * d'autre ne fonctionne, et surtout ne pas retenter l'appel qui vient d'échouer.
 */
import Link from "next/link";

const STUDIO_NAME = "Studio Chicane";
const STUDIO_EMAIL = "contact@studio-chicane.example";

export default function ExpiredLinkPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6 py-16">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">{STUDIO_NAME}</p>
      <h1 className="mt-2 text-3xl font-semibold text-ink-900">Ce lien n’est plus valide</h1>
      <p className="mt-4 text-base leading-relaxed text-ink-700">
        Le lien que vous avez ouvert a expiré, ou il a été remplacé par le studio. Vos photos
        n’ont pas disparu : elles sont toujours là, il suffit d’un nouveau lien pour y accéder.
      </p>
      <div className="mt-8 rounded-xl border border-ink-200 bg-white p-5">
        <p className="text-sm font-medium text-ink-900">Demander un nouveau lien</p>
        <p className="mt-1 text-sm text-ink-600">
          Écrivez-nous en précisant l’événement concerné, nous vous renvoyons un accès.
        </p>
        <Link
          href={`mailto:${STUDIO_EMAIL}`}
          className="mt-3 inline-block text-sm font-medium text-accent-700 underline hover:no-underline"
        >
          {STUDIO_EMAIL}
        </Link>
      </div>
    </main>
  );
}
