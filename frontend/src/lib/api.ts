import type {
  AppStatus,
  CaseDetail,
  CaseListItem,
  Company,
  DocumentDetail,
  DocumentGenerationPrepareRequest,
  DocumentGenerationRunStatus,
  DocumentPreparationResponse,
  DocumentRenderResponse,
  Site,
  StubAuthState,
} from "../types";

type RequestOptions = {
  method?: string;
  body?: unknown;
  auth?: StubAuthState;
  useStubAuth?: boolean;
};

const DEFAULT_API_BASE_URL = "";

function getApiBaseUrl(): string {
  const value = import.meta.env.VITE_API_BASE_URL;
  if (!value) {
    return DEFAULT_API_BASE_URL;
  }
  return String(value).replace(/\/+$/, "");
}

async function requestJson<T>(path: string, options: RequestOptions): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (options.useStubAuth && options.auth) {
    headers["X-Auth-User"] = options.auth.username;
    headers["X-Auth-Role"] = options.auth.role;
  }
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Preserve the original HTTP detail.
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function getAppStatus(): Promise<AppStatus> {
  return requestJson<AppStatus>("/app/status", {});
}

export function listCompanies(auth: StubAuthState, useStubAuth: boolean): Promise<Company[]> {
  return requestJson<Company[]>("/companies", { auth, useStubAuth });
}

export function listSites(auth: StubAuthState, useStubAuth: boolean): Promise<Site[]> {
  return requestJson<Site[]>("/sites", { auth, useStubAuth });
}

export function listCases(auth: StubAuthState, useStubAuth: boolean): Promise<CaseListItem[]> {
  return requestJson<CaseListItem[]>("/cases", { auth, useStubAuth });
}

export function getCaseDetail(caseId: string, auth: StubAuthState, useStubAuth: boolean): Promise<CaseDetail> {
  return requestJson<CaseDetail>(`/cases/${caseId}`, { auth, useStubAuth });
}

export function prepareDocument(
  payload: DocumentGenerationPrepareRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
): Promise<DocumentPreparationResponse> {
  return requestJson<DocumentPreparationResponse>("/documents/prepare", {
    method: "POST",
    body: payload,
    auth,
    useStubAuth,
  });
}

export function renderTemplateDocx(
  payload: DocumentGenerationPrepareRequest & { output_filename: string },
  auth: StubAuthState,
  useStubAuth: boolean,
): Promise<DocumentRenderResponse> {
  return requestJson<DocumentRenderResponse>("/documents/render-template-docx", {
    method: "POST",
    body: payload,
    auth,
    useStubAuth,
  });
}

export function getGenerationRun(
  generationRunId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
): Promise<DocumentGenerationRunStatus> {
  return requestJson<DocumentGenerationRunStatus>(`/document-generation-runs/${generationRunId}`, {
    auth,
    useStubAuth,
  });
}

export function getDocumentDetail(
  documentId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
): Promise<DocumentDetail> {
  return requestJson<DocumentDetail>(`/documents/${documentId}`, { auth, useStubAuth });
}
