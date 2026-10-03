/** 何も選んでいない状態。 */
export const NO_SELECTION: ReadonlySet<string> = new Set();

/** id が入っていれば外し、なければ足した、新しい集合。 */
export function toggled(
  ids: ReadonlySet<string>,
  id: string,
): ReadonlySet<string> {
  const next = new Set(ids);
  if (!next.delete(id)) {
    next.add(id);
  }
  return next;
}
