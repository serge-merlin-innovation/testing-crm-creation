type Snapshot = () => unknown;

export type UnsavedChanges = {
  mark: (form: string, dirty: boolean, snapshot?: Snapshot) => void;
  any: () => boolean;
  drafts: () => Record<string, unknown>;
  clear: () => void;
};

export function createUnsavedChanges(): UnsavedChanges {
  const dirty = new Map<string, Snapshot | undefined>();
  return {
    mark(form, isDirty, snapshot) {
      if (isDirty) {
        dirty.set(form, snapshot);
      } else {
        dirty.delete(form);
      }
    },
    any: () => dirty.size > 0,
    clear: () => dirty.clear(),
    drafts: () =>
      Object.fromEntries(
        [...dirty].flatMap(([form, snapshot]) => (snapshot ? [[form, snapshot()]] : [])),
      ),
  };
}

/** One registry per browser tab: forms mark themselves dirty, Log out and the timeout read it. */
export const unsavedChanges = createUnsavedChanges();
