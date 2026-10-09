import { useRef, useState, type KeyboardEvent } from "react";

// Focus is local UI state; only explicit activation changes business identity.
export function useCertificateRows(ids: string[], selectedId: string | null, onSelect: (id: string) => void, disabled: boolean) {
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const rows = useRef(new Map<string, HTMLTableRowElement>());
  const entryId = ids.includes(focusedId ?? "") ? focusedId
    : ids.includes(selectedId ?? "") ? selectedId : ids[0];
  function activate(id: string) { if (!disabled && id !== selectedId) onSelect(id); }
  return (id: string) => ({
    ref: (row: HTMLTableRowElement | null) => { if (row) rows.current.set(id, row); else rows.current.delete(id); },
    tabIndex: entryId === id ? 0 : -1,
    onFocus: () => setFocusedId(id),
    onClick: () => { rows.current.get(id)?.focus(); activate(id); },
    onKeyDown: (event: KeyboardEvent<HTMLTableRowElement>) => {
      const index = ids.indexOf(id);
      let next: number;
      switch (event.key) {
        case "ArrowDown": next = Math.min(index + 1, ids.length - 1); break;
        case "ArrowUp": next = Math.max(index - 1, 0); break;
        case "Home": next = 0; break;
        case "End": next = ids.length - 1; break;
        case "Enter":
        case " ": event.preventDefault(); activate(id); return;
        default: return;
      }
      event.preventDefault();
      rows.current.get(ids[next])?.focus();
    },
  });
}
