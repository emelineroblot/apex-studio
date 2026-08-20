"use client";

import * as mediaApi from "@/lib/api/resources/media";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { MediaGrid } from "@/components/media/MediaGrid";

export function MediaTab({ shootingId }: { shootingId: number }) {
  const { data, loading, error, reload } = useAsync(
    () => mediaApi.list({ shooting_id: shootingId, limit: 100 }),
    [shootingId],
  );

  if (loading) return <Spinner label="Chargement des médias…" />;
  if (error) return <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} />;
  if (!data || data.items.length === 0) {
    return (
      <EmptyState
        title="Aucun média rattaché pour l'instant"
        description="Les photos apparaîtront ici une fois déposées et traitées par le pipeline."
      />
    );
  }
  return <MediaGrid items={data.items} />;
}
