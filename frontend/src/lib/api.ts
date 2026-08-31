import type {
  AppStatus,
  BusinessEligibilityDetail,
  BusinessEligibilityList,
  CapaCycleAssessRequest,
  CapaCycleCreateRequest,
  CapaCycleMutationResponse,
  CapaCycleSubmitRequest,
  CapaCycleUpdateRequest,
  CaseApplicationUpsertRequest,
  CaseApplicationUpsertResponse,
  CaseAssessmentUpsertRequest,
  CaseAssessmentUpsertResponse,
  CaseDetail,
  CaseListItem,
  CaseWorkspace,
  ChangeRequestWorkspace,
  Company,
  DashboardSummary,
  DocumentDetail,
  DocumentGenerationPrepareRequest,
  DocumentGenerationRunStatus,
  DocumentPreparationResponse,
  DocumentRenderResponse,
  FacilitySearchPage,
  FacilityWorkspace,
  GxpCertificateDetail,
  GxpCertificateList,
  InspectionOutcomeUpsertRequest,
  InspectionOutcomeUpsertResponse,
  InspectionCaseCreateRequest,
  InspectionCaseCreateResponse,
  InspectionPlanUpsertRequest,
  InspectionPlanUpsertResponse,
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
    const error = new Error(detail) as Error & { status?: number };
    error.status = response.status;
    throw error;
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
    facility_name?: string;
    certificate_scope?: string;
    gxp_type?: string | null;
    province?: string;
    case_state?: string[] | null;
    change_request_state?: string[] | null;
    certificate_state?: string | null;
    certificate_expiring_within_days?: number | null;
    offset?: number;
    limit?: number;
  },
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<FacilitySearchPage> {
  const searchParams = new URLSearchParams();
  if (filters.q) {
    searchParams.set("q", filters.q);
  }
  if (filters.facility_name) {
    searchParams.set("facility_name", filters.facility_name);
  }
  if (filters.certificate_scope) {
    searchParams.set("certificate_scope", filters.certificate_scope);
  }
  if (filters.gxp_type) {
    searchParams.set("gxp_type", filters.gxp_type);
  }
  if (filters.province) {
    searchParams.set("province", filters.province);
  }
  for (const caseState of filters.case_state ?? []) {
    searchParams.append("case_state", caseState);
  }
  for (const changeRequestState of filters.change_request_state ?? []) {
    searchParams.append("change_request_state", changeRequestState);
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
  if (filters.offset && filters.offset > 0) {
    searchParams.set("offset", String(filters.offset));
  }
  searchParams.set("limit", String(filters.limit ?? 50));
  return requestJson<FacilitySearchPage>(buildApiPath("/search/facilities", searchParams), {
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function getFacilityWorkspace(
  siteId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  gxpType?: string | null,
  lineCode?: string | null,
  bearerToken?: string | null,
): Promise<FacilityWorkspace> {
  const searchParams = new URLSearchParams();
  if (gxpType) {
    searchParams.set("gxp_type", gxpType);
  }
  if (lineCode) {
    searchParams.set("line_code", lineCode);
  }
  return requestJson<FacilityWorkspace>(buildApiPath(`/sites/${siteId}/workspace`, searchParams), {
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function getCaseDetail(
  caseId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<CaseDetail> {
  return requestJson<CaseDetail>(`/cases/${caseId}`, { auth, useStubAuth, bearerToken });
}

export function getCaseWorkspace(
  caseId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<CaseWorkspace> {
  return requestJson<CaseWorkspace>(`/cases/${caseId}/workspace`, { auth, useStubAuth, bearerToken });
}

export function createInspectionCase(
  siteId: string,
  payload: InspectionCaseCreateRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<InspectionCaseCreateResponse> {
  return requestJson<InspectionCaseCreateResponse>(`/sites/${siteId}/inspection-cases`, {
    method: "POST",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function upsertCaseApplication(
  caseId: string,
  payload: CaseApplicationUpsertRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<CaseApplicationUpsertResponse> {
  return requestJson<CaseApplicationUpsertResponse>(`/cases/${caseId}/application`, {
    method: "PUT",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function upsertCaseAssessment(
  caseId: string,
  payload: CaseAssessmentUpsertRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<CaseAssessmentUpsertResponse> {
  return requestJson<CaseAssessmentUpsertResponse>(`/cases/${caseId}/assessment`, {
    method: "PUT",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function upsertInspectionPlan(
  caseId: string,
  payload: InspectionPlanUpsertRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<InspectionPlanUpsertResponse> {
  return requestJson<InspectionPlanUpsertResponse>(`/cases/${caseId}/plan`, {
    method: "PUT",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function upsertInspectionOutcome(
  caseId: string,
  payload: InspectionOutcomeUpsertRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<InspectionOutcomeUpsertResponse> {
  return requestJson<InspectionOutcomeUpsertResponse>(`/cases/${caseId}/outcome`, {
    method: "PUT",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function createCapaCycle(
  caseId: string,
  payload: CapaCycleCreateRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<CapaCycleMutationResponse> {
  return requestJson<CapaCycleMutationResponse>(`/cases/${caseId}/capa-cycles`, {
    method: "POST",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function updateCapaCycle(
  capaCycleId: string,
  payload: CapaCycleUpdateRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<CapaCycleMutationResponse> {
  return requestJson<CapaCycleMutationResponse>(`/capa-cycles/${capaCycleId}`, {
    method: "PUT",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function submitCapaCycle(
  capaCycleId: string,
  payload: CapaCycleSubmitRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<CapaCycleMutationResponse> {
  return requestJson<CapaCycleMutationResponse>(`/capa-cycles/${capaCycleId}/submit`, {
    method: "POST",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function assessCapaCycle(
  capaCycleId: string,
  payload: CapaCycleAssessRequest,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<CapaCycleMutationResponse> {
  return requestJson<CapaCycleMutationResponse>(`/capa-cycles/${capaCycleId}/assess`, {
    method: "POST",
    body: payload,
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function getChangeRequestWorkspace(
  changeRequestId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<ChangeRequestWorkspace> {
  return requestJson<ChangeRequestWorkspace>(`/change-requests/${changeRequestId}/workspace`, {
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function listSiteGxpCertificates(
  siteId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  gxpType?: string | null,
  lineCode?: string | null,
  bearerToken?: string | null,
): Promise<GxpCertificateList> {
  const searchParams = new URLSearchParams();
  if (gxpType) {
    searchParams.set("gxp_type", gxpType);
  }
  if (lineCode) {
    searchParams.set("line_code", lineCode);
  }
  return requestJson<GxpCertificateList>(buildApiPath(`/sites/${siteId}/gxp-certificates`, searchParams), {
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function getGxpCertificateDetail(
  certificateId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<GxpCertificateDetail> {
  return requestJson<GxpCertificateDetail>(`/certificates/${certificateId}`, { auth, useStubAuth, bearerToken });
}

export function listSiteBusinessEligibilityCertificates(
  siteId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<BusinessEligibilityList> {
  return requestJson<BusinessEligibilityList>(`/sites/${siteId}/business-eligibility-certificates`, {
    auth,
    useStubAuth,
    bearerToken,
  });
}

export function getBusinessEligibilityDetail(
  businessEligibilityCertificateId: string,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken?: string | null,
): Promise<BusinessEligibilityDetail> {
  return requestJson<BusinessEligibilityDetail>(`/business-eligibility-certificates/${businessEligibilityCertificateId}`, {
    auth,
    useStubAuth,
    bearerToken,
  });
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
