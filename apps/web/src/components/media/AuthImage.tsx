"use client";

import { useEffect, useState } from "react";
import { API_MODE } from "@/lib/env";
import { apiFetchBlob } from "@/lib/api/http";

/**
 * Affiche une vignette/aperçu média. `AGENTS.md` impose que l'accès au stockage objet
 * soit **toujours médié par le backend** — en mode "live", `src` est donc traité comme un
 * chemin d'API nécessitant l'en-tête `Authorization` (une `<img src>` classique ne peut
 * pas porter d'en-tête), récupéré en `Blob` puis exposé en URL objet locale. En mode
 * "fixtures", `src` est déjà une data URI directement utilisable.
 * Voir la note d'architecture dans `implementation.md` (point d'attention pour la revue).
 */
export function AuthImage({
  src,
  alt,
  className,
}: {
  src: string;
  alt: string;
  className?: string;
}) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const directSrc = API_MODE === "fixtures" || src.startsWith("data:") || src.startsWith("http");

  useEffect(() => {
    if (directSrc) return;
    let revoke: string | null = null;
    let cancelled = false;
    setFailed(false);
    apiFetchBlob(src)
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
  }, [src, directSrc]);

  if (failed) {
    return (
      <div
        role="img"
        aria-label={`${alt} — image indisponible`}
        className={`flex items-center justify-center bg-ink-100 text-xs text-ink-400 ${className ?? ""}`}
      >
        Image indisponible
      </div>
    );
  }

  const finalSrc = directSrc ? src : objectUrl;
  if (!finalSrc) {
    return <div className={`animate-pulse bg-ink-100 ${className ?? ""}`} aria-hidden="true" />;
  }

  // eslint-disable-next-line @next/next/no-img-element -- source dynamique (fixtures/data URI ou blob authentifié), incompatible avec l'optimiseur next/image.
  return <img src={finalSrc} alt={alt} className={className} loading="lazy" />;
}
