import { useLayoutEffect, useRef } from "react";

export function useCertificateDialogFocus() {
  const ref = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    const controls = () => Array.from(dialog?.querySelectorAll<HTMLElement>('input:not(:disabled), textarea:not(:disabled), select:not(:disabled), button:not(:disabled)') ?? []);
    controls()[0]?.focus();
    function trap(event: KeyboardEvent) {
      if (event.key !== "Tab") return;
      const elements = controls();
      const first = elements[0], last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    dialog?.addEventListener("keydown", trap);
    return () => { dialog?.removeEventListener("keydown", trap); if (trigger?.isConnected) trigger.focus(); };
  }, []);
  useLayoutEffect(() => {
    const dialog = ref.current;
    if (dialog && (!dialog.contains(document.activeElement) || document.activeElement === dialog)) {
      // Disabling a focused save control during a request sends focus to body
      // in real browsers. Keep it in the dialog, including after a 409.
      const first = dialog.querySelector<HTMLElement>('input:not(:disabled), textarea:not(:disabled), select:not(:disabled), button:not(:disabled)');
      (first ?? dialog).focus();
    }
  });
  return ref;
}
