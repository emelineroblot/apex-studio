/**
 * Sélection multiple avec `Shift`+clic — logique **pure**, testable sans DOM
 * (`selection.test.ts`). Utilisée par `/search` pour composer une collection depuis une
 * sélection de résultats (§ tâche 4 du brief).
 */
export function toggleWithRange(
  selected: ReadonlySet<number>,
  ids: readonly number[],
  clickedIndex: number,
  lastIndex: number | null,
  shiftKey: boolean,
): { next: Set<number>; lastIndex: number } {
  const next = new Set(selected);
  if (shiftKey && lastIndex != null && ids[lastIndex] != null) {
    const [start, end] = lastIndex <= clickedIndex ? [lastIndex, clickedIndex] : [clickedIndex, lastIndex];
    for (let i = start; i <= end; i += 1) next.add(ids[i]);
    return { next, lastIndex: clickedIndex };
  }
  const id = ids[clickedIndex];
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return { next, lastIndex: clickedIndex };
}
