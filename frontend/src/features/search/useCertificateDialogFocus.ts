import { useLayoutEffect, useRef } from "react";

function controls(dialog: HTMLElement): HTMLElement[] {
  return Array.from(dialog.querySelectorAll<HTMLElement>('input, textarea, select, button, a[href], [tabindex], [contenteditable="true"]'))
    .filter(element => element.tabIndex >= 0 && !element.matches(':disabled, [aria-disabled="true"], input[type="hidden"]')
      && !element.closest('[hidden], [inert], [aria-hidden="true"]')
      && getComputedStyle(element).display !== "none" && getComputedStyle(element).visibility !== "hidden");
}

export function useCertificateDialogFocus() {
  const ref = useRef<HTMLElement>(null);
  const lastControl = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const trigger = document.activeElement as HTMLElement | null;
    const background: { element: Element; inert: string | null }[] = [];
    // Exclude siblings along the modal's ancestry, leaving its path accessible.
    // Restore attributes already owned by another caller when the modal closes.
    for (let node: Element = dialog; node.parentElement; node = node.parentElement) {
      for (const sibling of Array.from(node.parentElement.children)) {
        if (sibling === node) continue;
        background.push({ element: sibling, inert: sibling.getAttribute("inert") });
        sibling.setAttribute("inert", "");
      }
      if (node.parentElement === document.body) break;
    }
    function fallback() {
      const enabled = controls(dialog!);
      return lastControl.current && enabled.includes(lastControl.current) ? lastControl.current : enabled[0] ?? dialog!;
    }
    function containFocus(event: FocusEvent) {
      if (!dialog!.contains(event.target as Node)) fallback().focus();
      else if (controls(dialog!).includes(event.target as HTMLElement)) lastControl.current = event.target as HTMLElement;
    }
    function trap(event: KeyboardEvent) {
      if (event.key !== "Tab") return;
      const enabled = controls(dialog!);
      const active = document.activeElement;
      if (enabled.length === 0) {
        event.preventDefault(); dialog!.focus();
      } else if (!enabled.includes(active as HTMLElement)) {
        event.preventDefault(); (event.shiftKey ? enabled.at(-1)! : enabled[0]).focus();
      } else if (event.shiftKey && active === enabled[0]) {
        event.preventDefault(); enabled.at(-1)!.focus();
      } else if (!event.shiftKey && active === enabled.at(-1)) {
        event.preventDefault(); enabled[0].focus();
      }
    }
    document.addEventListener("focusin", containFocus);
    document.addEventListener("keydown", trap, true);
    (controls(dialog)[0] ?? dialog).focus();
    return () => {
      document.removeEventListener("focusin", containFocus);
      document.removeEventListener("keydown", trap, true);
      for (const { element, inert } of background) {
        if (inert === null) element.removeAttribute("inert"); else element.setAttribute("inert", inert);
      }
      if (trigger?.isConnected && !trigger.matches(":disabled") && !trigger.closest("[inert]")) trigger.focus();
    };
  }, []);
  useLayoutEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const enabled = controls(dialog);
    if (!enabled.includes(document.activeElement as HTMLElement)) {
      const target = lastControl.current && enabled.includes(lastControl.current) ? lastControl.current : enabled[0] ?? dialog;
      target.focus();
    }
  });
  return ref;
}
