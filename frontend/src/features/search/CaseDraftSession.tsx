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

function createCommandRegistry() {
  const commands = new Map<string, object | "review">();
  const commandPayloads = new Map<string, unknown>();
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach(listener => listener());
  return {
    state: (key: string) => commands.get(key) === "review" ? "review" : commands.has(key) ? "pending" : "idle",
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    acquire: (key: string, payload?: unknown) => {
      if (commands.has(key)) return null;
      const token = {};
      if (payload !== undefined) commandPayloads.set(key, payload);
      commands.set(key, token); notify(); return token;
    },
    requireReview: (key: string, token: object, payload?: unknown) => {
      if (commands.get(key) !== token) return;
      if (payload !== undefined) commandPayloads.set(key, payload);
      commands.set(key, "review"); notify();
    },
    commandPayload: (key: string) => commands.has(key) ? commandPayloads.get(key) : undefined,
    release: (key: string, token: object) => {
      if (commands.get(key) !== token) return;
      commands.delete(key); commandPayloads.delete(key); notify();
    },
  };
}

const CommandRegistryContext = createContext<{ identity: string | null; registry: ReturnType<typeof createCommandRegistry> } | null>(null);
const FacilityCommandRegistryContext = createContext<{ identity: string | null; registry: ReturnType<typeof createCommandRegistry> } | null>(null);
const RootCaseRegistryContext = createContext<ReturnType<typeof createCommandRegistry> | null>(null);
const RootFacilityRegistryContext = createContext<ReturnType<typeof createCommandRegistry> | null>(null);

const Context = createContext<ReturnType<typeof createSession> | null>(null);

export function useCaseCommandRegistry() {
  const root = useContext(RootCaseRegistryContext);
  const registry = useRef<ReturnType<typeof createCommandRegistry> | null>(null);
  if (!registry.current) registry.current = createCommandRegistry();
  return root ?? registry.current;
}

export function CaseCommandRegistryRoot({ children }: { children: ReactNode }) {
  const registry = useRef<ReturnType<typeof createCommandRegistry> | null>(null);
  if (!registry.current) registry.current = createCommandRegistry();
  return <RootCaseRegistryContext.Provider value={registry.current}>{children}</RootCaseRegistryContext.Provider>;
}

export function useFacilityCommandRegistry() {
  const root = useContext(RootFacilityRegistryContext);
  const registry = useRef<ReturnType<typeof createCommandRegistry> | null>(null);
  if (!registry.current) registry.current = createCommandRegistry();
  return root ?? registry.current;
}

export function FacilityCommandRegistryRoot({ children }: { children: ReactNode }) {
  const registry = useRef<ReturnType<typeof createCommandRegistry> | null>(null);
  if (!registry.current) registry.current = createCommandRegistry();
  return <RootFacilityRegistryContext.Provider value={registry.current}>{children}</RootFacilityRegistryContext.Provider>;
}

// One active canonical Case/access/line context, in memory only. No history cache.
export function CaseDraftSession({ identity, commandRegistry, facilityIdentity = identity, facilityRegistry, children }: { identity: string | null; commandRegistry?: ReturnType<typeof createCommandRegistry>; facilityIdentity?: string | null; facilityRegistry?: ReturnType<typeof createCommandRegistry>; children: ReactNode }) {
  const localRegistry = useCaseCommandRegistry();
  const localFacilityRegistry = useFacilityCommandRegistry();
  const [owner, setOwner] = useState(() => ({ identity, session: createSession() }));
  if (owner.identity !== identity) {
    setOwner({ identity, session: createSession() });
  }
  // An interrupted render must not retire the still-committed editor session.
  // Cleanup runs when a replacement actually commits (or this owner unmounts).
  useLayoutEffect(() => {
    owner.session.activate();
    return () => owner.session.close();
  }, [owner.session]);
  return <FacilityCommandRegistryContext.Provider value={{ identity: facilityIdentity, registry: facilityRegistry ?? localFacilityRegistry }}><CommandRegistryContext.Provider value={{ identity, registry: commandRegistry ?? localRegistry }}><Context.Provider value={identity === null ? null : owner.session}>{children}</Context.Provider></CommandRegistryContext.Provider></FacilityCommandRegistryContext.Provider>;
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

// In-flight and uncertain command identities survive Case switches; drafts remain session-owned.
export function useCaseCommandLock(scope: string) {
  const context = useContext(CommandRegistryContext);
  const fallback = useRef<ReturnType<typeof createCommandRegistry> | null>(null);
  if (!fallback.current) fallback.current = createCommandRegistry();
  const registry = context?.registry ?? fallback.current;
  const key = JSON.stringify([context?.identity ?? null, scope]);
  const subscribe = useCallback((notify: () => void) => registry.subscribe(notify), [registry]);
  const snapshot = useCallback(() => registry.state(key), [registry, key]);
  const state = useSyncExternalStore(subscribe, snapshot, snapshot);
  const acquire = useCallback((payload?: unknown) => registry.acquire(key, payload), [registry, key]);
  const release = useCallback((token: object) => registry.release(key, token), [registry, key]);
  const requireReview = useCallback((token: object, payload?: unknown) => registry.requireReview(key, token, payload), [registry, key]);
  const commandPayload = useCallback(<T,>(): T | undefined => registry.commandPayload(key) as T | undefined, [registry, key]);
  return { pending: state === "pending", requiresReview: state === "review", acquire, release, requireReview, commandPayload };
}

// Facility commands are bound to access and Site, independently of selected history.
export function useFacilityCommandLock(scope: string) {
  const context = useContext(FacilityCommandRegistryContext);
  const fallback = useRef<ReturnType<typeof createCommandRegistry> | null>(null);
  if (!fallback.current) fallback.current = createCommandRegistry();
  const registry = context?.registry ?? fallback.current;
  const key = JSON.stringify([context?.identity ?? null, scope]);
  const subscribe = useCallback((notify: () => void) => registry.subscribe(notify), [registry]);
  const snapshot = useCallback(() => registry.state(key), [registry, key]);
  const state = useSyncExternalStore(subscribe, snapshot, snapshot);
  const acquire = useCallback(() => registry.acquire(key), [registry, key]);
  const release = useCallback((token: object) => registry.release(key, token), [registry, key]);
  const requireReview = useCallback((token: object) => registry.requireReview(key, token), [registry, key]);
  return { owner: context?.identity ?? null, pending: state === "pending", requiresReview: state === "review", acquire, release, requireReview };
}
