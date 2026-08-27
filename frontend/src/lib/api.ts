import type {
  AppStatus,
  CaseDetail,
  CaseListItem,
  Company,
  DashboardSummary,
  DocumentDetail,
  DocumentGenerationPrepareRequest,
  DocumentGenerationRunStatus,
  DocumentPreparationResponse,
  DocumentRenderResponse,
  FacilitySearchResult,
  FacilityWorkspace,
  Site,
  StubAuthState,
} from "../types";

type RequestOptions = {
  method?: string;
  body?: unknown;
  auth?: StubAuthState;
  useStubAuth?: boolean;
  bearerToken?: string | null;
};

const DEFAULT_API_BASE_URL = "/api";

function normalizeApiBaseUrl(value: string): string {
  const normalized = String(value).trim().replace(/\/+$/, "");
  return normalized || DEFAULT_API_BASE_URL;
}

function normalizeApiPath(path: string): string {
  const normalized = String(path).trim();
  return normalized.startsWith("/") ? normalized : `/${normalized}`;
}

function getApiBaseUrl(): string {
  const value = import.meta.env.VITE_API_BASE_URL;
  if (!value) {
    return DEFAULT_API_BASE_URL;
  }
  return normalizeApiBaseUrl(String(value));
}

function buildApiUrl(path: string): string {
  return `${getApiBaseUrl()}${normalizeApiPath(path)}`;
}

function buildApiPath(path: string, searchParams?: URLSearchParams): string {
  const normalizedPath = normalizeApiPath(path);
  if (!searchParams || Array.from(searchParams.keys()).length === 0) {
    return normalizedPath;
  }
  return `${normalizedPath}?${searchParams.toString()}`;
}

function isJsonContentType(contentType: string | null): boolean {
  if (!contentType) {
    return false;
  }
  const normalized = contentType.toLowerCase();
  return normalized.includes("application/json") || normalized.includes("+json");
}

function getContentTypeLabel(contentType: string | null): string {
  const normalized = (contentType ?? "").split(";", 1)[0].trim().toLowerCase();
  return normalized || "loại nội dung không rõ";
}

async function requestJson<T>(path: string, options: RequestOptions): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (options.useStubAuth && options.auth) {
    headers["X-Auth-User"] = options.auth.username;
    headers["X-Auth-Role"] = options.auth.role;
  } else if (options.bearerToken) {
    headers.Authorization = `Bearer ${options.bearerToken}`;
  }
  const requestUrl = buildApiUrl(path);
  const response = await fetch(requestUrl, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const contentType = response.headers.get("content-type");

  if (!isJsonContentType(contentType)) {
    throw new Error(`Kỳ vọng JSON từ ${requestUrl} nhưng nhận được ${getContentTypeLabel(contentType)}`);
  }

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

export function getDashboardSummary(
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<DashboardSummary> {
  return requestJson<DashboardSummary>("/dashboard/summary", { auth, useStubAuth, bearerToken });
}

export function listCompanies(auth: StubAuthState, useStubAuth: boolean, bearerToken?: string | null): Promise<Company[]> {
  return requestJson<Company[]>("/companies", { auth, useStubAuth, bearerToken });
}

export function listSites(auth: StubAuthState, useStubAuth: boolean, bearerToken?: string | null): Promise<Site[]> {
  return requestJson<Site[]>("/sites", { auth, useStubAuth, bearerToken });
}

export function listCases(auth: StubAuthState, useStubAuth: boolean, bearerToken?: string | null): Promise<CaseListItem[]> {
  return requestJson<CaseListItem[]>("/cases", { auth, useStubAuth, bearerToken });
}

export function searchFacilities(
  filters: {
    q?: string;
    gxp_type?: string | null;
    province?: string;
    case_state?: string | null;
    certificate_state?: string | null;
    certificate_expiring_within_days?: number | null;
    limit?: number;
  },
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<FacilitySearchResult[]> {
  const searchParams = new URLSearchParams();
  if (filters.q) {
    searchParams.set("q", filters.q);
  }
  if (filters.gxp_type) {
    searchParams.set("gxp_type", filters.gxp_type);
  }
  if (filters.province) {
    searchParams.set("province", filters.province);
  }
  if (filters.case_state) {
    searchParams.set("case_state", filters.case_state);
  }
  if (filters.certificate_state) {
    searchParams.set("certificate_state", filters.certificate_state);
  }
  if (filters.certificate_expiring_within_days) {
    searchParams.set(
      "certificate_expiring_within_days",
      String(filters.certificate_expiring_within_days),
    );
  }
  searchParams.set("limit", String(filters.limit ?? 50));
  return requestJson<FacilitySearchResult[]>(buildApiPath("/search/facilities", searchParams), {
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function getFacilityWorkspace(
  siteId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<FacilityWorkspace> {
  return requestJson<FacilityWorkspace>(`/sites/${siteId}/workspace`, { auth, useStubAuth, bearerToken });
}

export function getCaseDetail(
  caseId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<CaseDetail> {
  return requestJson<CaseDetail>(`/cases/${caseId}`, { auth, useStubAuth, bearerToken });
}

export function prepareDocument(
  payload: DocumentGenerationPrepareRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<DocumentPreparationResponse> {
  return requestJson<DocumentPreparationResponse>("/documents/prepare", {
    method: "POST",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function renderTemplateDocx(
  payload: DocumentGenerationPrepareRequest & { output_filename: string },
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<DocumentRenderResponse> {
  return requestJson<DocumentRenderResponse>("/documents/render-template-docx", {
    method: "POST",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function getGenerationRun(
  generationRunId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<DocumentGenerationRunStatus> {
  return requestJson<DocumentGenerationRunStatus>(`/document-generation-runs/${generationRunId}`, {
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function getDocumentDetail(
  documentId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<DocumentDetail> {
  return requestJson<DocumentDetail>(`/documents/${documentId}`, { auth, useStubAuth, bearerToken });
}
