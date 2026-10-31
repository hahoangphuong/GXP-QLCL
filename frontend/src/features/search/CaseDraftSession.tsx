import { createContext, useCallback, useContext, useLayoutEffect, useRef, useState, useSyncExternalStore, type Dispatch, type MutableRefObject, type ReactNode, type SetStateAction } from "react";

function createSession() {
  const values = new Map<string, unknown>();
  const listeners = new Map<string, Set<() => void>>();
  let live = true;
  return {
    isLive: () => live,
    activate: () => { live = true; },
    close: () => { live = false; },
    ensure<T>(key: string, initial: T | (() => T)) {
      if (!values.has(key)) values.set(key, typeof initial === "function" ? (initial as () => T)() : initial);
    },
    get<T>(key: string): T { return values.get(key) as T; },
    set<T>(key: string, update: SetStateAction<T>) {
      if (!live) return;
      const previous = values.get(key) as T;
      const next = typeof update === "function" ? (update as (value: T) => T)(previous) : update;
      if (Object.is(previous, next)) return;
      values.set(key, next);
      listeners.get(key)?.forEach(notify => notify());
    },
    subscribe(key: string, notify: () => void) {
      if (!listeners.has(key)) listeners.set(key, new Set());
      listeners.get(key)!.add(notify);
      return () => { listeners.get(key)?.delete(notify); };
    },
  };
}

const Context = createContext<ReturnType<typeof createSession> | null>(null);

// One active canonical Case/access/line context, in memory only. No history cache.
export function CaseDraftSession({ identity, children }: { identity: string | null; children: ReactNode }) {
  const [owner, setOwner] = useState(() => ({ identity, session: createSession() }));
  if (owner.identity !== identity) {
    owner.session.close();
    setOwner({ identity, session: createSession() });
  }
  useLayoutEffect(() => {
    owner.session.activate();
    return () => owner.session.close();
  }, [owner.session]);
  return <Context.Provider value={identity === null ? null : owner.session}>{children}</Context.Provider>;
}

export function useCaseDraftSession() { return useContext(Context); }

export function useCaseDraftState<T>(key: string, initial: T | (() => T) = undefined as T): [T, Dispatch<SetStateAction<T>>] {
  const session = useContext(Context);
  const fallback = useRef<ReturnType<typeof createSession> | null>(null);
  if (!fallback.current) fallback.current = createSession();
  const owner = session ?? fallback.current;
  owner.ensure(key, initial);
  const subscribe = useCallback((notify: () => void) => owner.subscribe(key, notify), [owner, key]);
  const snapshot = useCallback(() => owner.get<T>(key), [owner, key]);
  const value = useSyncExternalStore(subscribe, snapshot, snapshot);
  const setValue = useCallback((update: SetStateAction<T>) => owner.set(key, update), [owner, key]);
  return [value, setValue];
}

export function useCaseDraftRef<T>(key: string, initial: T): MutableRefObject<T> {
  return useCaseDraftState<MutableRefObject<T>>(key, () => ({ current: initial }))[0];
}
