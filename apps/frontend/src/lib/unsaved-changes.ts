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

type FormLike = { getAttribute: (name: string) => string | null };
type TargetLike = { closest?: (selector: string) => FormLike | null } | null;
type EventRoot = {
  addEventListener: (type: string, listener: (event: { target: unknown }) => void) => void;
  removeEventListener: (type: string, listener: (event: { target: unknown }) => void) => void;
};

function formKey(form: FormLike): string {
  return form.getAttribute("aria-label") ?? form.getAttribute("id") ?? "form";
}

/** Forms typed in but not submitted. Only Log out asks about these: the page-unload prompt and the
 * expiry drafts stay with forms that register themselves through `unsavedChanges`. */
export const typedForms = createUnsavedChanges();

/** Typing in any form but a search marks it unsaved; submitting it clears the mark. Returns a disposer. */
export function trackUnsavedForms(root: EventRoot, registry: UnsavedChanges = typedForms): () => void {
  const onInput = (event: { target: unknown }) => {
    const form = (event.target as TargetLike)?.closest?.("form");
    if (form && form.getAttribute("role") !== "search") {
      registry.mark(formKey(form), true);
    }
  };
  const onSubmit = (event: { target: unknown }) => {
    const form = event.target as FormLike | null;
    if (form?.getAttribute) {
      registry.mark(formKey(form), false);
    }
  };
  root.addEventListener("input", onInput);
  root.addEventListener("submit", onSubmit);
  return () => {
    root.removeEventListener("input", onInput);
    root.removeEventListener("submit", onSubmit);
  };
}
