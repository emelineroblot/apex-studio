"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import * as publicApi from "@/lib/api/resources/publicSpace";

/**
 * Image de l'espace client — vignette ou aperçu, toujours filigranés.
 *
 * Comme `AuthImage` côté studio, l'URL est un chemin d'API qui exige un en-tête
 * `Authorization` : une balise `<img src>` ne peut pas en porter, donc on récupère un
 * `Blob` et on l'expose en URL objet locale. Le stockage objet n'est jamais joignable
 * directement (`AGENTS.md`), y compris pour un client muni d'un lien valide.
 *
 * Composant distinct de `AuthImage` et non paramétrage de celui-ci : `AuthImage` lit le
 * jeton du back-office, celui-ci reçoit le jeton client explicitement. Les mélanger
 * rendrait possible, à une faute d'inattention près, l'emprunt d'une session studio.
 */
export function ClientImage({
  accessToken,
  path,
  alt,
  className,
}: {
  accessToken: string;
  path: string;
  alt: string;
  className?: string;
}) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let revoke: string | null = null;
    let cancelled = false;
    setFailed(false);
    publicApi
      .fetchImage(accessToken, path)
      .then((blob) => {
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revoke = url;
        setObjectUrl(url);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [accessToken, path]);

  if (failed) {
    return (
      <div
        className={clsx("flex items-center justify-center bg-ink-100 text-xs text-ink-500", className)}
        role="img"
        aria-label={`${alt} — image indisponible`}
      >
        Image indisponible
      </div>
    );
  }

  if (!objectUrl) {
    return <div className={clsx("animate-pulse bg-ink-100", className)} aria-hidden="true" />;
  }

  // Blob local : `next/image` exigerait une URL publique, que le cloisonnement interdit.
  // eslint-disable-next-line @next/next/no-img-element -- source blob authentifiee, cf. AuthImage.
  return <img src={objectUrl} alt={alt} className={className} draggable={false} loading="lazy" />;
}
