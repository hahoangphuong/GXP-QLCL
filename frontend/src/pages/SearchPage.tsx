import { startTransition, useDeferredValue, useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { ActionCard } from "../features/search/ActionCard";
import { FacilityTable } from "../features/search/FacilityTable";
import { FacilityWorkspaceTabs } from "../features/search/FacilityWorkspaceTabs";
import {
  assessCapaCycle,
  createCapaCycle,
  createInspectionCase,
  createChangeRequest,
  createChangeRequestDetail,
  issueChangeRequestCertificateSuccessor,
  updateChangeRequest,
  updateChangeRequestDetail,
  upsertChangeApproval,
  transitionChangeRequest,
  getBusinessEligibilityDetail,
  issueBusinessEligibility,
  promoteBusinessEligibilityCurrent,
  upsertBusinessEligibilityLatestVersion,
  getCaseWorkspace,
  getInspectionFolder,
  getChangeRequestWorkspace,
  getDocumentDetail,
  openCapaCycleDocumentCurrentContent,
  openCaseDocumentCurrentContent,
  getFacilityWorkspace,
  getGxpCertificateDetail,
  issueGxpCertificate,
  listSiteBusinessEligibilityCertificates,
  listSiteGxpCertificates,
  promoteGxpCertificateCurrent,
  upsertGxpCertificateLatestVersion,
  searchFacilities,
  submitCapaCycle,
  upsertCaseApplication,
  upsertCaseAssessment,
  updateCapaCycle,
  upsertInspectionOutcome,
  upsertInspectionPeriodSegments,
  createInspectionApprovalSubmission,
  completeInspectionApprovalSubmission,
  transitionCase,
  finalizeInspectionOutcome,
  upsertInspectionPlan,
  upsertInspectionTeam,
  listInspectionTeamIdentityOptions,
  upsertEvaluationScope,
} from "../lib/api";
import type {
  BusinessEligibilityDetail,
  BusinessEligibilityIssueActionReadiness,
  BusinessEligibilityIssueRequest,
  BusinessEligibilityLatestVersionUpsertRequest,
  BusinessEligibilityListItem,
  CapaCycleAssessRequest,
  CapaCycleCreateRequest,
  CapaCycleSubmitRequest,
  CapaCycleUpdateRequest,
  CaseApplicationUpsertRequest,
  CaseAssessmentUpsertRequest,
  CaseWorkspace,
  ChangeRequestWorkspace,
  ChangeApprovalUpsertRequest,
  ChangeRequestCreateRequest,
  ChangeRequestCertificateSuccessorIssueRequest,
  ChangeRequestDetailCreateRequest,
  ChangeRequestDetailUpdateRequest,
  ChangeRequestTransitionRequest,
  ChangeRequestUpdateRequest,
  ContextualDocumentAction,
  DocumentDetail,
  FacilitySearchResult,
  FacilityWorkspace,
  GxpCertificateDetail,
  GxpCertificateListItem,
  CertificateLatestVersionUpsertRequest,
  CertificateIssueRequest,
  InspectionOutcomeUpsertRequest,
  InspectionFinalEvaluationRequest,
  InspectionPlanUpsertRequest,
  InspectionTeamIdentityOption,
  InspectionTeamUpsertRequest,
  EvaluationScopeUpsertRequest,
} from "../types";

const DEFAULT_EVENT_TAB = "Hồ sơ";
const DEFAULT_FACILITY_TAB = "Các đợt kiểm tra & thay đổi";
const RESULT_PAGE_SIZE = 100;
const GXP_FILTER_OPTIONS = new Set(["GMP", "GLP", "GMPbb"]);

type PendingDeepLink = {
  resultKey: string | null;
  requestedGxpType: string | null;
  historyId: string | null;
  siteId: string | null;
  contextGxp: string | null;
  productionLineId: string | null;
  lineCode: string | null;
};

type ResolutionState = "none" | "pending" | "resolved" | "not_found";

function normalizeLineHint(value: string | null): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

function readPendingDeepLink(params: URLSearchParams): PendingDeepLink {
  return {
    resultKey: params.get("result_key"),
    requestedGxpType: params.get("gxp_type"),
    historyId: params.get("history_id"),
    siteId: params.get("site_id"),
    contextGxp: params.get("context_gxp"),
    productionLineId: params.get("production_line_id"),
    lineCode: normalizeLineHint(params.get("line_code")),
  };
}

function hasExplicitResultIdentity(pending: PendingDeepLink): boolean {
  return pending.resultKey !== null
    || pending.siteId !== null
    || pending.contextGxp !== null
    || pending.productionLineId !== null
    || pending.lineCode !== null;
}

function normalizeExplicitGxpHint(value: string | null): string | null {
  return value && GXP_FILTER_OPTIONS.has(value) ? value : null;
}

function hasInvalidOrContradictoryTargetGxpHints(pending: PendingDeepLink): boolean {
  const requestedGxpType = normalizeExplicitGxpHint(pending.requestedGxpType);
  const contextGxp = normalizeExplicitGxpHint(pending.contextGxp);
  return (pending.requestedGxpType !== null && requestedGxpType === null)
    || (pending.contextGxp !== null && contextGxp === null)
    || (requestedGxpType !== null && contextGxp !== null && requestedGxpType !== contextGxp);
}

function targetGxpConstraint(pending: PendingDeepLink): string | null {
  return normalizeExplicitGxpHint(pending.requestedGxpType)
    ?? normalizeExplicitGxpHint(pending.contextGxp);
}

function initialResolutionState(pending: PendingDeepLink): ResolutionState {
  return hasExplicitResultIdentity(pending) ? "pending" : "none";
}

function matchesCompatibilityHints(row: FacilitySearchResult, pending: PendingDeepLink): boolean {
  if (pending.siteId && row.site_id !== pending.siteId) return false;
  const contextGxp = normalizeExplicitGxpHint(pending.contextGxp);
  if (contextGxp && row.gxp_type !== contextGxp) return false;
  if (pending.productionLineId) return row.production_line_id === pending.productionLineId;
  if (pending.lineCode) {
    return row.production_line_identity_state === "legacy_unlinked"
      && normalizeLineHint(row.line_code) === pending.lineCode;
  }
  return Boolean(pending.siteId && pending.contextGxp && row.production_line_identity_state === "facility_wide");
}

function normalizeGxpSelection(value: string | null): string {
  return value && GXP_FILTER_OPTIONS.has(value) ? value : "GMP";
}

function initialGxpSelection(params: URLSearchParams): string {
  const pending = readPendingDeepLink(params);
  return normalizeGxpSelection(
    normalizeExplicitGxpHint(pending.requestedGxpType)
      ?? normalizeExplicitGxpHint(pending.contextGxp),
  );
}

function appendUniqueResults(current: FacilitySearchResult[], incoming: FacilitySearchResult[]) {
  const seen = new Set(current.map((item) => item.result_key));
  const next = [...current];
  for (const item of incoming) {
    if (seen.has(item.result_key)) {
      continue;
    }
    seen.add(item.result_key);
    next.push(item);
  }
  return next;
}

function resolveSelectedRemediationCycleId(
  caseWorkspace: CaseWorkspace | null,
  preferredCycleId: string | null,
): string | null {
  if (!caseWorkspace) {
    return null;
  }
  return preferredCycleId && caseWorkspace.remediation.cycles.some((cycle) => cycle.capa_cycle_id === preferredCycleId)
    ? preferredCycleId
    : caseWorkspace.remediation.cycles.at(-1)?.capa_cycle_id ?? null;
}

export function SearchPage({
  access,
  statusError,
}: {
  access: ApiAccess;
  statusError: string | null;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const searchSignature = searchParams.toString();
  const [generalQuery, setGeneralQuery] = useState(searchParams.get("q") ?? "");
  const [facilityName, setFacilityName] = useState(searchParams.get("facility_name") ?? "");
  const [certificateScope, setCertificateScope] = useState(searchParams.get("certificate_scope") ?? "");
  const [gxpType, setGxpType] = useState(initialGxpSelection(searchParams));
  const [province, setProvince] = useState(searchParams.get("province") ?? "");
  const [caseStates, setCaseStates] = useState<string[]>(searchParams.getAll("case_state"));
  const [certificateState, setCertificateState] = useState(searchParams.get("certificate_state") ?? "");
  const [certificateExpiringWithinDays, setCertificateExpiringWithinDays] = useState(searchParams.get("certificate_expiring_within_days") ?? "");
  const [changeRequestStates, setChangeRequestStates] = useState<string[]>(searchParams.getAll("change_request_state"));
  const [resultsOffset, setResultsOffset] = useState(0);
  const [searchEpoch, setSearchEpoch] = useState(0);
  const [selectedResultKey, setSelectedResultKey] = useState<string | null>(searchParams.get("result_key"));
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(searchParams.get("history_id"));
  const [pendingDeepLink, setPendingDeepLink] = useState<PendingDeepLink>(() => readPendingDeepLink(searchParams));
  const [resultResolution, setResultResolution] = useState<ResolutionState>(() => initialResolutionState(readPendingDeepLink(searchParams)));
  const [historyResolution, setHistoryResolution] = useState<ResolutionState>(() => searchParams.get("history_id") ? "pending" : "none");
  const [deepLinkError, setDeepLinkError] = useState<string | null>(null);
  const [selectedFacilityTab, setSelectedFacilityTab] = useState(searchParams.get("facility_tab") ?? DEFAULT_FACILITY_TAB);
  const [activeTab, setActiveTab] = useState(searchParams.get("event_tab") ?? DEFAULT_EVENT_TAB);
  const [selectedRemediationCycleId, setSelectedRemediationCycleId] = useState<string | null>(null);
  const deferredGeneralQuery = useDeferredValue(generalQuery);
  const deferredFacilityName = useDeferredValue(facilityName);
  const deferredCertificateScope = useDeferredValue(certificateScope);

  const [results, setResults] = useState<FacilitySearchResult[]>([]);
  // A resolved deep link owns the workspace target while the ordinary result
  // universe is reconciled to its settled GxP filter.
  const [resolvedDeepLinkResult, setResolvedDeepLinkResult] = useState<FacilitySearchResult | null>(null);
  const [resultsLoading, setResultsLoading] = useState(true);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [resultsTotalCount, setResultsTotalCount] = useState(0);
  const [workspace, setWorkspace] = useState<FacilityWorkspace | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [selectedActionKey, setSelectedActionKey] = useState<string | null>(null);
  const [applicableStandardInput, setApplicableStandardInput] = useState("");
  const [createInspectionCasePending, setCreateInspectionCasePending] = useState(false);
  const [createInspectionCaseError, setCreateInspectionCaseError] = useState<string | null>(null);
  const [createChangeRequestPending, setCreateChangeRequestPending] = useState(false);
  const [createChangeRequestError, setCreateChangeRequestError] = useState<string | null>(null);
  const [createChangeRequestDraft, setCreateChangeRequestDraft] = useState({
    scopeLabel: "",
    description: "",
    submittedOn: "",
    requesterName: "",
  });
  const [selectedCaseWorkspace, setSelectedCaseWorkspace] = useState<CaseWorkspace | null>(null);
  const [caseWorkspaceLoading, setCaseWorkspaceLoading] = useState(false);
  const [caseWorkspaceError, setCaseWorkspaceError] = useState<string | null>(null);
  const [selectedChangeRequestWorkspace, setSelectedChangeRequestWorkspace] = useState<ChangeRequestWorkspace | null>(null);
  const [changeRequestWorkspaceLoading, setChangeRequestWorkspaceLoading] = useState(false);
  const [changeRequestWorkspaceError, setChangeRequestWorkspaceError] = useState<string | null>(null);
  const [gxpCertificates, setGxpCertificates] = useState<GxpCertificateListItem[]>([]);
  const [gxpCertificatesLoading, setGxpCertificatesLoading] = useState(false);
  const [gxpCertificatesError, setGxpCertificatesError] = useState<string | null>(null);
  const [selectedGxpCertificateId, setSelectedGxpCertificateId] = useState<string | null>(null);
  const [gxpCertificateDetail, setGxpCertificateDetail] = useState<GxpCertificateDetail | null>(null);
  const [gxpCertificateDetailLoading, setGxpCertificateDetailLoading] = useState(false);
  const [gxpCertificateDetailError, setGxpCertificateDetailError] = useState<string | null>(null);
  const [gxpCertificatePromotionPending, setGxpCertificatePromotionPending] = useState(false);
  const [gxpCertificatePromotionError, setGxpCertificatePromotionError] = useState<string | null>(null);
  const [eligibilityCertificates, setEligibilityCertificates] = useState<BusinessEligibilityListItem[]>([]);
  const [eligibilityCertificatesLoading, setEligibilityCertificatesLoading] = useState(false);
  const [eligibilityCertificatesError, setEligibilityCertificatesError] = useState<string | null>(null);
  const [selectedEligibilityCertificateId, setSelectedEligibilityCertificateId] = useState<string | null>(null);
  const [eligibilityCertificateDetail, setEligibilityCertificateDetail] = useState<BusinessEligibilityDetail | null>(null);
  const [eligibilityCertificateDetailLoading, setEligibilityCertificateDetailLoading] = useState(false);
  const [eligibilityCertificateDetailError, setEligibilityCertificateDetailError] = useState<string | null>(null);
  const [eligibilityIssueReadiness, setEligibilityIssueReadiness] = useState<BusinessEligibilityIssueActionReadiness | null>(null);
  const [eligibilityBasisCertificates, setEligibilityBasisCertificates] = useState<GxpCertificateListItem[]>([]);
  const [eligibilityBasisLoading, setEligibilityBasisLoading] = useState(false);
  const [eligibilityBasisError, setEligibilityBasisError] = useState<string | null>(null);
  const [eligibilityPromotionPending, setEligibilityPromotionPending] = useState(false);
  const [eligibilityPromotionError, setEligibilityPromotionError] = useState<string | null>(null);
  const { auth, useStubAuth, bearerToken, canLoadSecureApi } = access;
  const reassessmentInputRef = useRef<HTMLInputElement | null>(null);
  const reassessmentTriggerRef = useRef<HTMLButtonElement | null>(null);
  const internalUrlWriteRef = useRef<string | null>(null);
  const suppressUrlSyncRef = useRef(false);
  const didHydrateInitialUrlRef = useRef(false);
  const latestSearchSignatureRef = useRef(searchSignature);
  const resultsRef = useRef<FacilitySearchResult[]>([]);
  latestSearchSignatureRef.current = searchSignature;

  useEffect(() => {
    resultsRef.current = results;
  }, [results]);

  const selectedResultFromResults = results.find((item) => item.result_key === selectedResultKey) ?? null;
  const selectedResult = resultResolution === "resolved"
    && resolvedDeepLinkResult?.result_key === selectedResultKey
    ? resolvedDeepLinkResult
    : selectedResultFromResults;
  const explicitTargetPending = resultResolution === "pending" && hasExplicitResultIdentity(pendingDeepLink);
  const pendingTargetGxpConstraint = targetGxpConstraint(pendingDeepLink);
  const pendingTargetGxpHintsInvalid = hasInvalidOrContradictoryTargetGxpHints(pendingDeepLink);
  const searchGxpType = explicitTargetPending ? pendingTargetGxpConstraint : gxpType;
  const selectedHistory = workspace?.history.find((item) => item.id === selectedHistoryId) ?? null;
  const hasMoreResults = results.length < resultsTotalCount;
  const createReassessmentAction =
    workspace?.action_readiness.find((item) => item.action_key === "create_reassessment_case") ?? null;
  const reassessmentDialogOpen = selectedActionKey === "create_reassessment_case" && selectedResult && createReassessmentAction;
  const createChangeRequestAction =
    workspace?.action_readiness.find((item) => item.action_key === "create_change_request") ?? null;
  const changeRequestDialogOpen =
    selectedActionKey === "create_change_request" &&
    selectedResult &&
    createChangeRequestAction?.readiness_status === "available";

  // External same-route navigation owns URL -> state. Local interaction below owns state -> URL.
  useLayoutEffect(() => {
    const signature = searchSignature;
    const params = new URLSearchParams(signature);
    // Initial state is derived from the initial URL. Mark it before consuming a
    // possible normalization write so the next external navigation is hydrated.
    if (!didHydrateInitialUrlRef.current) {
      didHydrateInitialUrlRef.current = true;
      if (internalUrlWriteRef.current === signature) {
        internalUrlWriteRef.current = null;
      }
      return;
    }
    if (internalUrlWriteRef.current === signature) {
      internalUrlWriteRef.current = null;
      return;
    }
    suppressUrlSyncRef.current = true;
    setGeneralQuery(params.get("q") ?? "");
    setFacilityName(params.get("facility_name") ?? "");
    setCertificateScope(params.get("certificate_scope") ?? "");
    setGxpType(initialGxpSelection(params));
    setProvince(params.get("province") ?? "");
    setCaseStates(params.getAll("case_state"));
    setChangeRequestStates(params.getAll("change_request_state"));
    setCertificateState(params.get("certificate_state") ?? "");
    setCertificateExpiringWithinDays(params.get("certificate_expiring_within_days") ?? "");
    const pending = readPendingDeepLink(params);
    setPendingDeepLink(pending);
    setResultResolution(initialResolutionState(pending));
    setResolvedDeepLinkResult(null);
    setHistoryResolution(pending.historyId ? "pending" : "none");
    setSelectedResultKey(pending.resultKey);
    setSelectedHistoryId(pending.historyId);
    setSelectedFacilityTab(params.get("facility_tab") ?? DEFAULT_FACILITY_TAB);
    setActiveTab(params.get("event_tab") ?? DEFAULT_EVENT_TAB);
    setResultsOffset(0);
    setSearchEpoch((current) => current + 1);
    setDeepLinkError(null);
  }, [searchSignature]);

  function resetCertificateWorkspaceState() {
    setGxpCertificates([]);
    setGxpCertificatesLoading(false);
    setGxpCertificatesError(null);
    setSelectedGxpCertificateId(null);
    setGxpCertificateDetail(null);
    setGxpCertificateDetailLoading(false);
    setGxpCertificateDetailError(null);
    setEligibilityCertificates([]);
    setEligibilityCertificatesLoading(false);
    setEligibilityCertificatesError(null);
    setSelectedEligibilityCertificateId(null);
    setEligibilityCertificateDetail(null);
    setEligibilityCertificateDetailLoading(false);
    setEligibilityCertificateDetailError(null);
    setEligibilityIssueReadiness(null);
    setEligibilityBasisCertificates([]);
    setEligibilityBasisLoading(false);
    setEligibilityBasisError(null);
    setEligibilityPromotionPending(false);
    setEligibilityPromotionError(null);
  }

  function resetCreateInspectionCaseState() {
    setSelectedActionKey(null);
    setApplicableStandardInput("");
    setCreateInspectionCasePending(false);
    setCreateInspectionCaseError(null);
  }

  function resetCreateChangeRequestState() {
    setSelectedActionKey(null);
    setCreateChangeRequestPending(false);
    setCreateChangeRequestError(null);
    setCreateChangeRequestDraft({
      scopeLabel: "",
      description: "",
      submittedOn: "",
      requesterName: "",
    });
  }

  function closeChangeRequestDialog() {
    if (!createChangeRequestPending) {
      resetCreateChangeRequestState();
    }
  }

  function closeReassessmentDialog() {
    if (createInspectionCasePending) {
      return;
    }
    resetCreateInspectionCaseState();
    reassessmentTriggerRef.current?.focus();
  }

  useLayoutEffect(() => {
    if (suppressUrlSyncRef.current) {
      suppressUrlSyncRef.current = false;
      return;
    }
    // Do not let an effect from a previous render overwrite a newer external navigation.
    if (latestSearchSignatureRef.current !== searchSignature) {
      return;
    }
    const nextParams = new URLSearchParams();
    if (deferredGeneralQuery.trim()) {
      nextParams.set("q", deferredGeneralQuery.trim());
    }
    if (deferredFacilityName.trim()) {
      nextParams.set("facility_name", deferredFacilityName.trim());
    }
    if (deferredCertificateScope.trim()) {
      nextParams.set("certificate_scope", deferredCertificateScope.trim());
    }
    const explicitTargetUnresolved = resultResolution !== "resolved" && hasExplicitResultIdentity(pendingDeepLink);
    if (explicitTargetUnresolved) {
      if (pendingDeepLink.requestedGxpType !== null) {
        nextParams.set("gxp_type", pendingDeepLink.requestedGxpType);
      }
    } else {
      nextParams.set("gxp_type", gxpType);
    }
    if (province.trim()) {
      nextParams.set("province", province.trim());
    }
    for (const value of caseStates) {
      nextParams.append("case_state", value);
    }
    for (const value of changeRequestStates) {
      nextParams.append("change_request_state", value);
    }
    if (certificateState) {
      nextParams.set("certificate_state", certificateState);
    }
    if (certificateExpiringWithinDays) {
      nextParams.set("certificate_expiring_within_days", certificateExpiringWithinDays);
    }
    const unresolvedIdentity = selectedResult && resultResolution !== "not_found"
      ? {
          resultKey: selectedResult.result_key,
          siteId: selectedResult.site_id,
          contextGxp: selectedResult.gxp_type,
          productionLineId: selectedResult.production_line_id ?? null,
          lineCode: selectedResult.line_code,
        }
      : pendingDeepLink;
    if (unresolvedIdentity.resultKey) {
      nextParams.set("result_key", unresolvedIdentity.resultKey);
    }
    if (unresolvedIdentity.siteId) {
      nextParams.set("site_id", unresolvedIdentity.siteId);
    }
    if (unresolvedIdentity.lineCode) {
      nextParams.set("line_code", unresolvedIdentity.lineCode);
    }
    if (unresolvedIdentity.productionLineId) {
      nextParams.set("production_line_id", unresolvedIdentity.productionLineId);
    }
    if (unresolvedIdentity.contextGxp) {
      nextParams.set("context_gxp", unresolvedIdentity.contextGxp);
    }
    const historyForUrl = selectedHistoryId ?? (
      historyResolution === "pending" || historyResolution === "not_found"
        ? pendingDeepLink.historyId
        : null
    );
    if (historyForUrl) {
      nextParams.set("history_id", historyForUrl);
    }
    if (selectedFacilityTab !== DEFAULT_FACILITY_TAB) {
      nextParams.set("facility_tab", selectedFacilityTab);
    }
    if (activeTab !== DEFAULT_EVENT_TAB) {
      nextParams.set("event_tab", activeTab);
    }
    const nextSignature = nextParams.toString();
    if (nextSignature !== searchSignature) {
      internalUrlWriteRef.current = nextSignature;
      setSearchParams(nextParams, { replace: true });
    }
  }, [
    activeTab,
    caseStates,
    certificateExpiringWithinDays,
    certificateState,
    changeRequestStates,
    deferredCertificateScope,
    deferredFacilityName,
    deferredGeneralQuery,
    gxpType,
    province,
    selectedFacilityTab,
    selectedHistoryId,
    selectedResult,
    pendingDeepLink,
    historyResolution,
    resultResolution,
    searchSignature,
    setSearchParams,
  ]);

  useEffect(() => {
    if (!canLoadSecureApi) {
      setResultsLoading(false);
      setResults([]);
      setResultsTotalCount(0);
      return;
    }
    if (explicitTargetPending && pendingTargetGxpHintsInvalid) {
      setResultsLoading(false);
      setResults([]);
      setResultsTotalCount(0);
      setSelectedResultKey(null);
      setSelectedHistoryId(null);
      setResolvedDeepLinkResult(null);
      setWorkspace(null);
      resetCertificateWorkspaceState();
      setResultResolution("not_found");
      setDeepLinkError("Các ràng buộc GxP trong liên kết không hợp lệ hoặc mâu thuẫn.");
      return;
    }
    const isFirstPage = resultsOffset === 0;
    let cancelled = false;
    setResultsLoading(true);
    if (isFirstPage) {
      setResults([]);
      setResultsTotalCount(0);
    }
    void searchFacilities(
      {
        q: deferredGeneralQuery.trim() || undefined,
        facility_name: deferredFacilityName.trim() || undefined,
        certificate_scope: deferredCertificateScope.trim() || undefined,
        gxp_type: searchGxpType,
        province: province.trim() || undefined,
        case_state: caseStates,
        change_request_state: changeRequestStates,
        certificate_state: certificateState || null,
        certificate_expiring_within_days: certificateExpiringWithinDays ? Number(certificateExpiringWithinDays) : null,
        offset: resultsOffset,
        limit: RESULT_PAGE_SIZE,
      },
      auth,
      useStubAuth,
      bearerToken,
    )
      .then((payload) => {
        if (cancelled) {
          return;
        }
        const nextResults = isFirstPage ? payload.items : appendUniqueResults(resultsRef.current, payload.items);
        setResults(nextResults);
        setResultsTotalCount(payload.total_count);
        setResultsError(null);
        setResultsLoading(false);
        const explicitTarget = explicitTargetPending;
        const compatibleRows = explicitTarget && !pendingDeepLink.resultKey
          ? nextResults.filter((item) => matchesCompatibilityHints(item, pendingDeepLink))
          : [];
        const pendingMatch = explicitTarget && pendingDeepLink.resultKey
          ? nextResults.find((item) => item.result_key === pendingDeepLink.resultKey) ?? null
          : null;
        const resolveExplicitTarget = (target: FacilitySearchResult) => {
          const resolvedGxpType = normalizeGxpSelection(target.gxp_type);
          setResolvedDeepLinkResult(target);
          setSelectedResultKey(target.result_key);
          setGxpType(resolvedGxpType);
          setResultResolution("resolved");
          setDeepLinkError(null);

          // A target found through an unfiltered or differently filtered
          // lookup must not leave that lookup universe in the settled table.
          if (pendingTargetGxpConstraint !== resolvedGxpType) {
            setResultsOffset(0);
            setSearchEpoch((current) => current + 1);
          }
        };
        if (pendingMatch) {
          resolveExplicitTarget(pendingMatch);
        } else if (explicitTarget) {
          if (!pendingDeepLink.resultKey && compatibleRows.length > 1) {
            setSelectedResultKey(null);
            setSelectedHistoryId(null);
            setResolvedDeepLinkResult(null);
            setWorkspace(null);
            resetCertificateWorkspaceState();
            setResultResolution("not_found");
            setDeepLinkError("Không tìm thấy ngữ cảnh được liên kết trong kết quả tra cứu hiện tại.");
          } else if (nextResults.length < payload.total_count) {
            setResultsOffset(nextResults.length);
          } else if (!pendingDeepLink.resultKey && compatibleRows.length === 1) {
            resolveExplicitTarget(compatibleRows[0]);
          } else {
            setSelectedResultKey(null);
            setSelectedHistoryId(null);
            setResolvedDeepLinkResult(null);
            setWorkspace(null);
            resetCertificateWorkspaceState();
            setResultResolution("not_found");
            setDeepLinkError("Không tìm thấy ngữ cảnh được liên kết trong kết quả tra cứu hiện tại.");
          }
        } else if (resultResolution === "none" && isFirstPage && payload.items.length > 0 && !selectedResultKey) {
            setSelectedResultKey(payload.items[0].result_key);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setResultsError(error.message);
          setResultsLoading(false);
          if (isFirstPage) {
            setResults([]);
            setResultsTotalCount(0);
          }
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    auth,
    bearerToken,
    caseStates,
    canLoadSecureApi,
    certificateExpiringWithinDays,
    certificateState,
    changeRequestStates,
    deferredCertificateScope,
    deferredFacilityName,
    deferredGeneralQuery,
    gxpType,
    province,
    resultsOffset,
    searchEpoch,
    useStubAuth,
  ]);

  useEffect(() => {
    if (!selectedResult || !canLoadSecureApi) {
      setWorkspace(null);
      resetCreateInspectionCaseState();
      setSelectedCaseWorkspace(null);
      setCaseWorkspaceError(null);
      setCaseWorkspaceLoading(false);
      setSelectedRemediationCycleId(null);
      setSelectedChangeRequestWorkspace(null);
      setChangeRequestWorkspaceError(null);
      setChangeRequestWorkspaceLoading(false);
      resetCertificateWorkspaceState();
      return;
    }
    let cancelled = false;
    setWorkspaceLoading(true);
    setCreateInspectionCaseError(null);
    resetCertificateWorkspaceState();
    void getFacilityWorkspace(
      selectedResult.site_id,
      auth,
      useStubAuth,
      selectedResult.gxp_type,
      selectedResult.line_code,
      bearerToken,
      selectedResult.production_line_id,
    )
      .then((payload) => {
        if (!cancelled) {
          setWorkspace(payload);
          setWorkspaceError(null);
          setWorkspaceLoading(false);
          setSelectedActionKey((current) =>
            current &&
            payload.action_readiness.some(
              (item) => item.action_key === current && item.readiness_status === "available",
            )
              ? current
              : null,
          );
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setWorkspaceError(error.message);
          setWorkspaceLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, canLoadSecureApi, selectedResult, useStubAuth]);

  useEffect(() => {
    if (!workspace) return;
    if (historyResolution === "pending" && pendingDeepLink.historyId) {
      if (workspace.history.some((row) => row.id === pendingDeepLink.historyId)) {
        setSelectedHistoryId(pendingDeepLink.historyId);
        setHistoryResolution("resolved");
      } else {
        setSelectedHistoryId(null);
        setHistoryResolution("not_found");
        setDeepLinkError("Không tìm thấy hồ sơ được liên kết trong lịch sử ngữ cảnh hiện tại.");
      }
      return;
    }
    if (historyResolution === "none") {
      setSelectedHistoryId((current) => current && workspace.history.some((row) => row.id === current) ? current : workspace.history[0]?.id ?? null);
    }
  }, [historyResolution, pendingDeepLink.historyId, workspace]);

  useEffect(() => {
    setSelectedCaseWorkspace(null);
    setCaseWorkspaceError(null);
    setCaseWorkspaceLoading(false);
    setSelectedRemediationCycleId(null);
    if (!canLoadSecureApi || !selectedHistoryId || selectedHistory?.source_type !== "case") {
      return;
    }
    let cancelled = false;
    setCaseWorkspaceLoading(true);
    void getCaseWorkspace(selectedHistoryId, auth, useStubAuth, bearerToken)
      .then((payload) => {
        if (!cancelled) {
          setSelectedCaseWorkspace(payload);
          setSelectedRemediationCycleId((current) => resolveSelectedRemediationCycleId(payload, current));
          setCaseWorkspaceError(null);
          setCaseWorkspaceLoading(false);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setSelectedCaseWorkspace(null);
          setSelectedRemediationCycleId(null);
          setCaseWorkspaceError(error.message);
          setCaseWorkspaceLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, canLoadSecureApi, selectedHistoryId, selectedHistory?.source_type, useStubAuth]);

  useEffect(() => {
    setSelectedChangeRequestWorkspace(null);
    setChangeRequestWorkspaceError(null);
    setChangeRequestWorkspaceLoading(false);
    if (!canLoadSecureApi || !selectedHistoryId || selectedHistory?.source_type !== "change_request") {
      return;
    }
    let cancelled = false;
    setChangeRequestWorkspaceLoading(true);
    void getChangeRequestWorkspace(selectedHistoryId, auth, useStubAuth, bearerToken)
      .then((payload) => {
        if (!cancelled) {
          setSelectedChangeRequestWorkspace(payload);
          setChangeRequestWorkspaceError(null);
          setChangeRequestWorkspaceLoading(false);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setSelectedChangeRequestWorkspace(null);
          setChangeRequestWorkspaceError(error.message);
          setChangeRequestWorkspaceLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, canLoadSecureApi, selectedHistoryId, selectedHistory?.source_type, useStubAuth]);

  useEffect(() => {
    if (!selectedResult || !canLoadSecureApi || selectedFacilityTab !== "Giấy chứng nhận GxP") {
      return;
    }
    let cancelled = false;
    setGxpCertificatesLoading(true);
    void listSiteGxpCertificates(
      selectedResult.site_id,
      auth,
      useStubAuth,
      selectedResult.gxp_type,
      selectedResult.line_code,
      bearerToken,
      selectedResult.production_line_id,
    )
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setGxpCertificates(payload.items);
        setGxpCertificatesError(null);
        setGxpCertificatesLoading(false);
        setSelectedGxpCertificateId((current) =>
          current && payload.items.some((item) => item.certificate_id === current) ? current : payload.items[0]?.certificate_id ?? null,
        );
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setGxpCertificates([]);
          setGxpCertificatesError(error.message);
          setGxpCertificatesLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, canLoadSecureApi, selectedFacilityTab, selectedResult, useStubAuth]);

  useEffect(() => {
    setGxpCertificateDetail(null);
    setGxpCertificateDetailError(null);
    setGxpCertificateDetailLoading(false);
    if (!selectedGxpCertificateId || !canLoadSecureApi || selectedFacilityTab !== "Giấy chứng nhận GxP") {
      return;
    }
    let cancelled = false;
    setGxpCertificateDetailLoading(true);
    void getGxpCertificateDetail(selectedGxpCertificateId, auth, useStubAuth, bearerToken)
      .then((payload) => {
        if (!cancelled) {
          setGxpCertificateDetail(payload);
          setGxpCertificateDetailError(null);
          setGxpCertificateDetailLoading(false);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setGxpCertificateDetail(null);
          setGxpCertificateDetailError(error.message);
          setGxpCertificateDetailLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, canLoadSecureApi, selectedFacilityTab, selectedGxpCertificateId, useStubAuth]);

  useEffect(() => {
    if (!selectedResult || !canLoadSecureApi || selectedFacilityTab !== "Giấy chứng nhận đủ điều kiện") {
      return;
    }
    let cancelled = false;
    setEligibilityCertificatesLoading(true);
    void listSiteBusinessEligibilityCertificates(
      selectedResult.site_id,
      auth,
      useStubAuth,
      bearerToken,
    )
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setEligibilityCertificates(payload.items);
        setEligibilityIssueReadiness(payload.issue_readiness);
        setEligibilityCertificatesError(null);
        setEligibilityCertificatesLoading(false);
        setSelectedEligibilityCertificateId((current) =>
          current && payload.items.some((item) => item.business_eligibility_certificate_id === current)
            ? current
            : payload.items[0]?.business_eligibility_certificate_id ?? null,
        );
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setEligibilityCertificates([]);
          setEligibilityIssueReadiness(null);
          setEligibilityCertificatesError(error.message);
          setEligibilityCertificatesLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, canLoadSecureApi, selectedFacilityTab, selectedResult, useStubAuth]);

  useEffect(() => {
    setEligibilityCertificateDetail(null);
    setEligibilityCertificateDetailError(null);
    setEligibilityCertificateDetailLoading(false);
    if (!selectedEligibilityCertificateId || !canLoadSecureApi || selectedFacilityTab !== "Giấy chứng nhận đủ điều kiện") {
      return;
    }
    let cancelled = false;
    setEligibilityCertificateDetailLoading(true);
    void getBusinessEligibilityDetail(selectedEligibilityCertificateId, auth, useStubAuth, bearerToken)
      .then((payload) => {
        if (!cancelled) {
          setEligibilityCertificateDetail(payload);
          setEligibilityCertificateDetailError(null);
          setEligibilityCertificateDetailLoading(false);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setEligibilityCertificateDetail(null);
          setEligibilityCertificateDetailError(error.message);
          setEligibilityCertificateDetailLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, canLoadSecureApi, selectedEligibilityCertificateId, selectedFacilityTab, useStubAuth]);

  useEffect(() => {
    const editAvailable = (eligibilityCertificateDetail?.action_readiness ?? [])
      .some((action) => action.action_key === "edit_latest_version" && action.available);
    const needsBasis = eligibilityIssueReadiness?.available === true || editAvailable;
    if (!selectedResult || !canLoadSecureApi || selectedFacilityTab !== "Giấy chứng nhận đủ điều kiện" || !needsBasis) {
      setEligibilityBasisCertificates([]);
      setEligibilityBasisLoading(false);
      setEligibilityBasisError(null);
      return;
    }
    let cancelled = false;
    setEligibilityBasisLoading(true);
    void listSiteGxpCertificates(selectedResult.site_id, auth, useStubAuth, null, null, bearerToken, null)
      .then((payload) => {
        if (!cancelled) {
          setEligibilityBasisCertificates(payload.items);
          setEligibilityBasisLoading(false);
          setEligibilityBasisError(null);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setEligibilityBasisCertificates([]);
          setEligibilityBasisLoading(false);
          setEligibilityBasisError(error.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, canLoadSecureApi, eligibilityCertificateDetail, eligibilityIssueReadiness, selectedFacilityTab, selectedResult, useStubAuth]);

  useEffect(() => {
    if (!reassessmentDialogOpen) {
      return;
    }
    reassessmentInputRef.current?.focus();
  }, [reassessmentDialogOpen]);

  useEffect(() => {
    if (!reassessmentDialogOpen) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !createInspectionCasePending) {
        event.preventDefault();
        closeReassessmentDialog();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [createInspectionCasePending, reassessmentDialogOpen]);

  function resetDependentContext() {
    setResultsOffset(0);
    setSelectedResultKey(null);
    setSelectedHistoryId(null);
    setResolvedDeepLinkResult(null);
    setPendingDeepLink({ resultKey: null, requestedGxpType: null, historyId: null, siteId: null, contextGxp: null, productionLineId: null, lineCode: null });
    setResultResolution("none");
    setHistoryResolution("none");
    setDeepLinkError(null);
    setSelectedFacilityTab(DEFAULT_FACILITY_TAB);
    setActiveTab(DEFAULT_EVENT_TAB);
    setWorkspace(null);
    setWorkspaceError(null);
    resetCreateInspectionCaseState();
    resetCreateChangeRequestState();
    setSelectedCaseWorkspace(null);
    setCaseWorkspaceError(null);
    setCaseWorkspaceLoading(false);
    setSelectedRemediationCycleId(null);
    setSelectedChangeRequestWorkspace(null);
    setChangeRequestWorkspaceError(null);
    setChangeRequestWorkspaceLoading(false);
    resetCertificateWorkspaceState();
  }

  function updateFilter(field: "facilityName" | "certificateScope" | "caseState" | "gxpType", value: string) {
    startTransition(() => {
      resetDependentContext();
      if (field === "facilityName") {
        setFacilityName(value);
      } else if (field === "certificateScope") {
        setCertificateScope(value);
      } else if (field === "gxpType") {
        setGxpType(value);
      } else if (field === "caseState") {
        setCaseStates(value ? [value] : []);
      }
    });
  }

  function loadMoreResults() {
    if (resultsLoading || !hasMoreResults) {
      return;
    }
    setResultsOffset(results.length);
  }

  function selectResultFromTable(resultKey: string) {
    setPendingDeepLink({ resultKey: null, requestedGxpType: null, historyId: null, siteId: null, contextGxp: null, productionLineId: null, lineCode: null });
    setResultResolution("none");
    setResolvedDeepLinkResult(null);
    setHistoryResolution("none");
    setDeepLinkError(null);
    setSelectedResultKey(resultKey);
    setSelectedHistoryId(null);
  }

  async function refreshWorkspaceAfterCreate(createdCaseId: string) {
    if (!selectedResult) {
      return;
    }
    setWorkspaceLoading(true);
    resetCertificateWorkspaceState();
    try {
      const payload = await getFacilityWorkspace(
        selectedResult.site_id,
        auth,
        useStubAuth,
        selectedResult.gxp_type,
        selectedResult.line_code,
        bearerToken,
        selectedResult.production_line_id,
      );
      setWorkspace(payload);
      setWorkspaceError(null);
      setSelectedFacilityTab(DEFAULT_FACILITY_TAB);
      setActiveTab(DEFAULT_EVENT_TAB);
      setSelectedHistoryId(
        payload.history.some((row) => row.id === createdCaseId) ? createdCaseId : payload.history[0]?.id ?? null,
      );
    } finally {
      setWorkspaceLoading(false);
    }
  }

  async function refreshSelectedFacilityWorkspace(preferredHistoryId: string | null) {
    if (!selectedResult) {
      return null;
    }
    const payload = await getFacilityWorkspace(
      selectedResult.site_id,
      auth,
      useStubAuth,
      selectedResult.gxp_type,
      selectedResult.line_code,
      bearerToken,
      selectedResult.production_line_id,
    );
    setWorkspace(payload);
    setWorkspaceError(null);
    setSelectedHistoryId((current) => {
      const nextPreferredHistoryId = preferredHistoryId ?? current;
      return nextPreferredHistoryId && payload.history.some((row) => row.id === nextPreferredHistoryId)
        ? nextPreferredHistoryId
        : payload.history[0]?.id ?? null;
    });
    return payload;
  }

  async function refreshSelectedChangeRequestWorkspace(changeRequestId: string) {
    const payload = await getChangeRequestWorkspace(changeRequestId, auth, useStubAuth, bearerToken);
    setSelectedChangeRequestWorkspace(payload);
    setChangeRequestWorkspaceError(null);
    return payload;
  }

  async function runSelectedChangeRequestMutation(
    mutation: (changeRequestId: string) => Promise<unknown>,
  ) {
    if (!selectedHistory || selectedHistory.source_type !== "change_request") {
      throw new Error("Chưa chọn yêu cầu thay đổi để cập nhật.");
    }
    const changeRequestId = selectedHistory.id;
    try {
      await mutation(changeRequestId);
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      if (status === 409) {
        await Promise.all([
          refreshSelectedChangeRequestWorkspace(changeRequestId).catch(() => undefined),
          refreshSelectedFacilityWorkspace(changeRequestId).catch(() => undefined),
        ]);
      }
      throw error;
    }
    await Promise.all([
      refreshSelectedChangeRequestWorkspace(changeRequestId),
      refreshSelectedFacilityWorkspace(changeRequestId).catch(() => undefined),
    ]);
  }

  async function handleChangeRequestCertificateSuccessorIssue(
    payload: ChangeRequestCertificateSuccessorIssueRequest,
  ) {
    await runSelectedChangeRequestMutation((changeRequestId) =>
      issueChangeRequestCertificateSuccessor(
        changeRequestId,
        payload,
        auth,
        useStubAuth,
        bearerToken,
      ));
  }

  async function handleChangeRequestHeaderUpdate(payload: ChangeRequestUpdateRequest) {
    await runSelectedChangeRequestMutation((changeRequestId) =>
      updateChangeRequest(changeRequestId, payload, auth, useStubAuth, bearerToken));
  }

  async function handleChangeRequestDetailCreate(payload: ChangeRequestDetailCreateRequest) {
    await runSelectedChangeRequestMutation((changeRequestId) =>
      createChangeRequestDetail(changeRequestId, payload, auth, useStubAuth, bearerToken));
  }

  async function handleChangeRequestDetailUpdate(changeDetailId: string, payload: ChangeRequestDetailUpdateRequest) {
    await runSelectedChangeRequestMutation(() =>
      updateChangeRequestDetail(changeDetailId, payload, auth, useStubAuth, bearerToken));
  }

  async function handleChangeApprovalUpsert(payload: ChangeApprovalUpsertRequest) {
    await runSelectedChangeRequestMutation((changeRequestId) =>
      upsertChangeApproval(changeRequestId, payload, auth, useStubAuth, bearerToken));
  }

  async function handleChangeRequestTransition(payload: ChangeRequestTransitionRequest) {
    await runSelectedChangeRequestMutation((changeRequestId) =>
      transitionChangeRequest(changeRequestId, payload, auth, useStubAuth, bearerToken));
  }

  async function handleCaseApplicationSave(payload: CaseApplicationUpsertRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật.");
    }
    const caseId = selectedHistory.id;
    const currentCaseWorkspace = selectedCaseWorkspace;
    const response = await upsertCaseApplication(caseId, payload, auth, useStubAuth, bearerToken);
    const refreshedCaseWorkspace = await getCaseWorkspace(caseId, auth, useStubAuth, bearerToken).catch(() => {
      if (!currentCaseWorkspace) {
        throw new Error("Đã lưu nhưng không tải lại được workspace hồ sơ.");
      }
      return {
        ...currentCaseWorkspace,
        application: {
          ...currentCaseWorkspace.application,
          row_version: response.row_version,
          submitted_on: response.submitted_on,
          dossier_code: response.dossier_code,
          dossier_reference: response.dossier_reference,
          applicant_name: response.applicant_name,
        },
      };
    });
    setSelectedCaseWorkspace(refreshedCaseWorkspace);
    setCaseWorkspaceError(null);
    await refreshSelectedFacilityWorkspace(caseId).catch(() => undefined);
  }

  async function handleResolveInspectionFolder() {
    const summary = selectedCaseWorkspace?.case_summary;
    if (!summary || summary.legacy_site_id === null || !summary.legacy_inspection_code) {
      throw new Error("Hồ sơ chưa có đủ định danh legacy để tra cứu thư mục kiểm tra.");
    }
    return getInspectionFolder(
      {
        caseId: summary.id,
        siteLegacyId: summary.legacy_site_id,
        inspectionLegacyCode: summary.legacy_inspection_code,
      },
      auth,
      useStubAuth,
      bearerToken,
    );
  }

  async function handleInspectionPlanSave(payload: InspectionPlanUpsertRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật.");
    }
    const caseId = selectedHistory.id;
    const currentCaseWorkspace = selectedCaseWorkspace;
    const response = await upsertInspectionPlan(caseId, payload, auth, useStubAuth, bearerToken);
    const refreshedCaseWorkspace = await getCaseWorkspace(caseId, auth, useStubAuth, bearerToken).catch(() => {
      if (!currentCaseWorkspace) {
        throw new Error("Đã lưu nhưng không tải lại được workspace hồ sơ.");
      }
      return {
        ...currentCaseWorkspace,
        inspection: {
          ...currentCaseWorkspace.inspection,
          plan_row_version: response.row_version,
          plan_start_on: response.plan_start_on,
          plan_end_on: response.plan_end_on,
          planning_sheet_name: response.planning_sheet_name,
          plan_decision_reference: response.decision_reference,
          plan_decision_date: response.decision_date,
        },
      };
    });
    setSelectedCaseWorkspace(refreshedCaseWorkspace);
    setCaseWorkspaceError(null);
  }

  async function handleInspectionOutcomeSave(payload: InspectionOutcomeUpsertRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật.");
    }
    const caseId = selectedHistory.id;
    const currentCaseWorkspace = selectedCaseWorkspace;
    const response = await upsertInspectionOutcome(caseId, payload, auth, useStubAuth, bearerToken);
    const refreshedCaseWorkspace = await getCaseWorkspace(caseId, auth, useStubAuth, bearerToken).catch(() => {
      if (!currentCaseWorkspace) {
        throw new Error("Đã lưu nhưng không tải lại được workspace hồ sơ.");
      }
      return {
        ...currentCaseWorkspace,
        inspection: {
          ...currentCaseWorkspace.inspection,
          outcome_row_version: response.row_version,
          inspected_on: response.inspected_on,
          inspected_to_on: response.inspected_to_on,
          outcome_result: response.outcome_result,
          final_evaluation: response.final_evaluation,
          minutes_recorded_on: response.minutes_recorded_on,
          minutes_recorded_time: response.minutes_recorded_time,
          compliance_due_on: response.compliance_due_on,
        },
      };
    });
    setSelectedCaseWorkspace(refreshedCaseWorkspace);
    setCaseWorkspaceError(null);
    await refreshSelectedFacilityWorkspace(caseId).catch(() => undefined);
  }

  async function handleInspectionPeriodSegmentsSave(payload: import("../types").InspectionPeriodSegmentsUpsertRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") throw new Error("Chưa chọn hồ sơ để cập nhật các đợt kiểm tra.");
    const caseId = selectedHistory.id;
    await upsertInspectionPeriodSegments(caseId, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(caseId);
    await refreshSelectedFacilityWorkspace(caseId).catch(() => undefined);
  }

  async function handleCreateApprovalSubmission(stage: "PCT" | "CT", payload: import("../types").InspectionApprovalSubmissionCreateRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") throw new Error("Chưa chọn hồ sơ để tạo trình phê duyệt.");
    const caseId = selectedHistory.id;
    const response = await createInspectionApprovalSubmission(caseId, stage, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(caseId);
    return response;
  }

  async function handleCompleteApprovalSubmission(submissionId: string, payload: import("../types").InspectionApprovalSubmissionCompleteRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") throw new Error("Chưa chọn hồ sơ để hoàn tất trình phê duyệt.");
    const response = await completeInspectionApprovalSubmission(submissionId, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(selectedHistory.id);
    return response;
  }

  async function handleCaseTransition(payload: import("../types").CaseTransitionRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") throw new Error("Chưa chọn hồ sơ để chuyển trạng thái.");
    const caseId = selectedHistory.id;
    try {
      await transitionCase(caseId, payload, auth, useStubAuth, bearerToken);
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      if (status === 409) {
        await Promise.all([
          refreshSelectedCaseWorkspace(caseId).catch(() => undefined),
          refreshSelectedFacilityWorkspace(caseId).catch(() => undefined),
        ]);
      }
      throw error;
    }
    await refreshSelectedCaseWorkspace(caseId);
    await refreshSelectedFacilityWorkspace(caseId).catch(() => undefined);
  }

  async function handleFinalizeInspectionOutcome(payload: InspectionFinalEvaluationRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để hoàn tất đánh giá.");
    }
    const caseId = selectedHistory.id;
    await finalizeInspectionOutcome(caseId, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(caseId);
    await refreshSelectedFacilityWorkspace(caseId).catch(() => undefined);
  }

  async function handleInspectionTeamSave(payload: InspectionTeamUpsertRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật đoàn kiểm tra.");
    }
    const caseId = selectedHistory.id;
    try {
      await upsertInspectionTeam(caseId, payload, auth, useStubAuth, bearerToken);
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      if (status === 409) await refreshSelectedCaseWorkspace(caseId).catch(() => undefined);
      throw error;
    }
    await refreshSelectedCaseWorkspace(caseId);
  }

  function handleLoadInspectionTeamIdentityOptions(): Promise<InspectionTeamIdentityOption[]> {
    return listInspectionTeamIdentityOptions(auth, useStubAuth, bearerToken);
  }

  async function handleEvaluationScopeSave(payload: EvaluationScopeUpsertRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật.");
    }
    const caseId = selectedHistory.id;
    await upsertEvaluationScope(caseId, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(caseId);
  }

  async function handleCaseAssessmentSave(payload: CaseAssessmentUpsertRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật.");
    }
    const caseId = selectedHistory.id;
    const currentCaseWorkspace = selectedCaseWorkspace;
    const response = await upsertCaseAssessment(caseId, payload, auth, useStubAuth, bearerToken);
    const refreshedCaseWorkspace = await getCaseWorkspace(caseId, auth, useStubAuth, bearerToken).catch(() => {
      if (!currentCaseWorkspace) {
        throw new Error("Đã lưu nhưng không tải lại được workspace xử lý.");
      }
      return {
        ...currentCaseWorkspace,
        processing: {
          ...currentCaseWorkspace.processing,
          row_version: response.row_version,
          assessed_on: response.assessed_on,
          assessor_name: response.assessor_name,
          assessment_result: response.assessment_result,
          notes: response.notes,
        },
      };
    });
    setSelectedCaseWorkspace(refreshedCaseWorkspace);
    setCaseWorkspaceError(null);
  }

  async function refreshSelectedCaseWorkspace(caseId: string, preferredCycleId?: string | null) {
    const payload = await getCaseWorkspace(caseId, auth, useStubAuth, bearerToken);
    setSelectedCaseWorkspace(payload);
    setCaseWorkspaceError(null);
    setSelectedRemediationCycleId((current) => resolveSelectedRemediationCycleId(payload, preferredCycleId ?? current));
    return payload;
  }

  async function handleCreateCapaCycle(payload: CapaCycleCreateRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật.");
    }
    const caseId = selectedHistory.id;
    const response = await createCapaCycle(caseId, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(caseId, response.capa_cycle_id);
  }

  async function handleUpdateCapaCycle(cycleId: string, payload: CapaCycleUpdateRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật.");
    }
    const caseId = selectedHistory.id;
    await updateCapaCycle(cycleId, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(caseId, cycleId);
  }

  async function handleSubmitCapaCycle(cycleId: string, payload: CapaCycleSubmitRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật.");
    }
    const caseId = selectedHistory.id;
    await submitCapaCycle(cycleId, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(caseId, cycleId);
  }

  async function handleAssessCapaCycle(cycleId: string, payload: CapaCycleAssessRequest) {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ để cập nhật.");
    }
    const caseId = selectedHistory.id;
    await assessCapaCycle(cycleId, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(caseId, cycleId);
  }

  async function refreshBusinessEligibilityAfterMutation(certificateId: string) {
    if (!selectedResult) return;
    const [detailPayload, listPayload] = await Promise.all([
      getBusinessEligibilityDetail(certificateId, auth, useStubAuth, bearerToken),
      listSiteBusinessEligibilityCertificates(selectedResult.site_id, auth, useStubAuth, bearerToken),
    ]);
    setSelectedEligibilityCertificateId(certificateId);
    setEligibilityCertificateDetail(detailPayload);
    setEligibilityCertificateDetailError(null);
    setEligibilityCertificates(listPayload.items);
    setEligibilityIssueReadiness(listPayload.issue_readiness);
  }

  async function handleIssueBusinessEligibility(payload: BusinessEligibilityIssueRequest) {
    if (!selectedResult) {
      throw new Error("Chưa chọn cơ sở để cấp GCN đủ điều kiện.");
    }
    const result = await issueBusinessEligibility(selectedResult.site_id, payload, auth, useStubAuth, bearerToken);
    await refreshBusinessEligibilityAfterMutation(result.business_eligibility_certificate_id);
  }

  async function handleBusinessEligibilityLatestVersionUpdate(payload: BusinessEligibilityLatestVersionUpsertRequest) {
    if (!selectedEligibilityCertificateId) {
      throw new Error("Chưa chọn GCN đủ điều kiện để cập nhật.");
    }
    try {
      await upsertBusinessEligibilityLatestVersion(
        selectedEligibilityCertificateId,
        payload,
        auth,
        useStubAuth,
        bearerToken,
      );
      await refreshBusinessEligibilityAfterMutation(selectedEligibilityCertificateId);
    } catch (error) {
      const apiError = error as Error & { status?: number };
      if (apiError.status === 409) {
        try {
          await refreshBusinessEligibilityAfterMutation(selectedEligibilityCertificateId);
        } catch {
          // Preserve the mutation conflict as the actionable error when refresh also fails.
        }
        const staleError = new Error("Dữ liệu GCN đủ điều kiện đã thay đổi. Hãy kiểm tra lại rồi lưu lại.") as Error & { status?: number };
        staleError.status = 409;
        throw staleError;
      }
      throw error;
    }
  }

  async function handleBusinessEligibilityPromote(expectedVersion: number) {
    if (!selectedEligibilityCertificateId) {
      throw new Error("Chưa chọn GCN đủ điều kiện để cập nhật.");
    }
    setEligibilityPromotionPending(true);
    setEligibilityPromotionError(null);
    try {
      await promoteBusinessEligibilityCurrent(
        selectedEligibilityCertificateId,
        expectedVersion,
        auth,
        useStubAuth,
        bearerToken,
      );
      await refreshBusinessEligibilityAfterMutation(selectedEligibilityCertificateId);
    } catch (error) {
      const apiError = error as Error & { status?: number };
      if (apiError.status === 409 && selectedEligibilityCertificateId) {
        try {
          await refreshBusinessEligibilityAfterMutation(selectedEligibilityCertificateId);
        } catch {
          // Keep the original promotion conflict as the actionable error.
        }
      }
      setEligibilityPromotionError(error instanceof Error ? error.message : "Không thể cập nhật GCN đủ điều kiện hiện hành.");
    } finally {
      setEligibilityPromotionPending(false);
    }
  }

  async function handleGxpCertificatePromote(expectedVersion: number) {
    if (!selectedGxpCertificateId || !selectedResult) {
      throw new Error("Chưa chọn giấy chứng nhận để cập nhật.");
    }
    setGxpCertificatePromotionPending(true);
    setGxpCertificatePromotionError(null);
    try {
      await promoteGxpCertificateCurrent(selectedGxpCertificateId, expectedVersion, auth, useStubAuth, bearerToken);
      const [detailPayload, listPayload] = await Promise.all([
        getGxpCertificateDetail(selectedGxpCertificateId, auth, useStubAuth, bearerToken),
        listSiteGxpCertificates(
          selectedResult.site_id,
          auth,
          useStubAuth,
          selectedResult.gxp_type,
          selectedResult.line_code,
          bearerToken,
          selectedResult.production_line_id,
        ),
      ]);
      setGxpCertificateDetail(detailPayload);
      setGxpCertificates(listPayload.items);
    } catch (error) {
      setGxpCertificatePromotionError(error instanceof Error ? error.message : "Không thể cập nhật chứng nhận hiện hành.");
    } finally {
      setGxpCertificatePromotionPending(false);
    }
  }

  async function handleGxpCertificateLatestVersionUpdate(payload: CertificateLatestVersionUpsertRequest) {
    if (!selectedGxpCertificateId || !selectedResult) {
      throw new Error("Chưa chọn giấy chứng nhận để cập nhật.");
    }
    try {
      await upsertGxpCertificateLatestVersion(selectedGxpCertificateId, payload, auth, useStubAuth, bearerToken);
      const [detailPayload, listPayload] = await Promise.all([
        getGxpCertificateDetail(selectedGxpCertificateId, auth, useStubAuth, bearerToken),
        listSiteGxpCertificates(
          selectedResult.site_id,
          auth,
          useStubAuth,
          selectedResult.gxp_type,
          selectedResult.line_code,
          bearerToken,
          selectedResult.production_line_id,
        ),
      ]);
      setGxpCertificateDetail(detailPayload);
      setGxpCertificates(listPayload.items);
      setGxpCertificateDetailError(null);
    } catch (error) {
      const apiError = error as Error & { status?: number };
      if (apiError.status === 409) {
        try {
          const detailPayload = await getGxpCertificateDetail(selectedGxpCertificateId, auth, useStubAuth, bearerToken);
          setGxpCertificateDetail(detailPayload);
          setGxpCertificateDetailError(null);
        } catch {
          // Preserve the mutation conflict as the actionable error when refresh also fails.
        }
        const staleError = new Error("Dữ liệu chứng nhận đã thay đổi. Hãy kiểm tra lại rồi lưu lại.") as Error & { status?: number };
        staleError.status = 409;
        throw staleError;
      }
      throw error;
    }
  }

  async function handleIssueGxpCertificate(payload: CertificateIssueRequest) {
    if (!selectedResult || !selectedCaseWorkspace || selectedHistory?.source_type !== "case") {
      throw new Error("Chưa chọn hồ sơ kiểm tra để cấp giấy chứng nhận.");
    }
    if (payload.case_id !== selectedCaseWorkspace.case_summary.id) {
      throw new Error("Ngữ cảnh hồ sơ cấp chứng nhận không còn hợp lệ.");
    }
    const result = await issueGxpCertificate(selectedCaseWorkspace.case_summary.site_id, payload, auth, useStubAuth, bearerToken);
    await refreshSelectedCaseWorkspace(payload.case_id);
    if (selectedFacilityTab === "Giấy chứng nhận GxP") {
      const [detailPayload, listPayload] = await Promise.all([
        getGxpCertificateDetail(result.certificate_id, auth, useStubAuth, bearerToken),
        listSiteGxpCertificates(selectedResult.site_id, auth, useStubAuth, selectedResult.gxp_type, selectedResult.line_code, bearerToken, selectedResult.production_line_id),
      ]);
      setSelectedGxpCertificateId(result.certificate_id);
      setGxpCertificateDetail(detailPayload);
      setGxpCertificates(listPayload.items);
      setGxpCertificateDetailError(null);
    }
  }

  async function handleLoadDocumentDetail(documentId: string): Promise<DocumentDetail> {
    return getDocumentDetail(documentId, auth, useStubAuth, bearerToken);
  }

  async function handleOpenDocument(caseId: string, item: ContextualDocumentAction): Promise<void> {
    if (!item.document_id) {
      throw new Error("Tài liệu chưa có binary hiện hành để mở.");
    }
    let response: Awaited<ReturnType<typeof openCaseDocumentCurrentContent>>;
    if (item.parent_scope === "case") {
      response = await openCaseDocumentCurrentContent(item.parent_id, item.document_id, auth, useStubAuth, bearerToken);
    } else if (item.parent_scope === "capa_cycle") {
      response = await openCapaCycleDocumentCurrentContent(caseId, item.parent_id, item.document_id, auth, useStubAuth, bearerToken);
    } else {
      throw new Error("Phạm vi sở hữu tài liệu chưa được hỗ trợ để mở.");
    }
    const { blob } = response;
    const objectUrl = URL.createObjectURL(blob);
    window.open(objectUrl, "_blank", "noopener");
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  }

  async function handleCreateChangeRequestSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedResult) {
      return;
    }
    setCreateChangeRequestPending(true);
    setCreateChangeRequestError(null);
    const payload: ChangeRequestCreateRequest = {
      scope_label: createChangeRequestDraft.scopeLabel.trim() || null,
      description: createChangeRequestDraft.description.trim() || null,
      submitted_on: createChangeRequestDraft.submittedOn || null,
      requester_name: createChangeRequestDraft.requesterName.trim() || null,
    };
    try {
      const created = await createChangeRequest(
        selectedResult.site_id,
        payload,
        auth,
        useStubAuth,
        bearerToken,
      );
      const changeRequestId = created.change_request_id;
      const [changeWorkspace] = await Promise.all([
        getChangeRequestWorkspace(changeRequestId, auth, useStubAuth, bearerToken),
        refreshSelectedFacilityWorkspace(changeRequestId),
      ]);
      setSelectedChangeRequestWorkspace(changeWorkspace);
      setChangeRequestWorkspaceError(null);
      setSelectedFacilityTab(DEFAULT_FACILITY_TAB);
      setSelectedHistoryId(changeRequestId);
      setActiveTab("Đề nghị");
      resetCreateChangeRequestState();
    } catch (error) {
      setCreateChangeRequestError(error instanceof Error ? error.message : "Không tạo được yêu cầu thay đổi.");
      setCreateChangeRequestPending(false);
    }
  }

  async function handleCreateInspectionCaseSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedResult) {
      return;
    }
    setCreateInspectionCasePending(true);
    setCreateInspectionCaseError(null);
    try {
      const created = await createInspectionCase(
        selectedResult.site_id,
        {
          gxp_type: selectedResult.gxp_type ?? "",
          line_code: selectedResult.line_code ?? null,
          production_line_id: selectedResult.production_line_id,
          applicable_standard: applicableStandardInput.trim() || null,
          source_case_id: selectedHistory?.source_type === "case" ? selectedHistory.id : null,
        },
        auth,
        useStubAuth,
        bearerToken,
      );
      await refreshWorkspaceAfterCreate(created.case_id);
      resetCreateInspectionCaseState();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Không mở được hồ sơ tái đánh giá.";
      setCreateInspectionCaseError(message);
      setCreateInspectionCasePending(false);
    }
  }

  if (statusError) {
    return <ErrorState message={statusError} />;
  }
  if (!canLoadSecureApi) {
    return <EmptyState title="Cần đăng nhập" description="Đăng nhập để dùng Tra cứu trên authenticated API thật." />;
  }
  if (resultsError && results.length === 0) {
    return <ErrorState message={resultsError} />;
  }

  return (
    <section className="page-section search-page">
      <div className="search-workspace search-workspace-split search-workspace-a4">
        <FacilityTable
          filters={{
            facilityName,
            certificateScope,
          }}
          hasMore={hasMoreResults}
          hiddenFilters={{
            generalQuery,
            province,
            changeRequestStates,
            certificateState,
            certificateExpiringWithinDays,
          }}
          loading={resultsLoading}
          onFilterChange={updateFilter}
          onGxpTypeChange={(value) => updateFilter("gxpType", value)}
          onReachEnd={loadMoreResults}
          onSelect={selectResultFromTable}
          rows={results}
          selectedResultKey={selectedResultKey}
          selectedGxpType={gxpType}
        />
        <div className="action-stack">
          <ActionCard
            actions={workspace?.action_readiness}
            onActionSelect={(actionKey) => {
              if (actionKey !== "create_reassessment_case" && actionKey !== "create_change_request") {
                return;
              }
              setSelectedActionKey((current) => (current === actionKey ? null : actionKey));
              setCreateInspectionCaseError(null);
              setCreateChangeRequestError(null);
            }}
            onActionButtonRef={(actionKey, element) => {
              if (actionKey === "create_reassessment_case") {
                reassessmentTriggerRef.current = element;
              }
            }}
            selectedActionKey={selectedActionKey}
          />
        </div>
      </div>

      {reassessmentDialogOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <section
            aria-labelledby="reassessment-dialog-title"
            aria-modal="true"
            className="panel reassessment-dialog"
            role="dialog"
          >
            <header className="panel-header reassessment-dialog-header">
              <div>
                <h2 id="reassessment-dialog-title">Tạo hồ sơ tái đánh giá</h2>
                <p>{createReassessmentAction.detail}</p>
              </div>
            </header>
            <dl className="detail-grid compact-detail-grid reassessment-context-grid">
              <div>
                <dt>Cơ sở</dt>
                <dd>{selectedResult.facility_name}</dd>
              </div>
              <div>
                <dt>GxP</dt>
                <dd>{selectedResult.gxp_type ?? "Chưa chọn"}</dd>
              </div>
              <div>
                <dt>Dây chuyền</dt>
                <dd>{selectedResult.line_code ?? "Toàn cơ sở"}</dd>
              </div>
            </dl>
            <form className="stack-form reassessment-form" onSubmit={handleCreateInspectionCaseSubmit}>
              <label className="reassessment-form-field">
                <span>Tiêu chuẩn áp dụng</span>
                <input
                  aria-label="Tiêu chuẩn áp dụng"
                  disabled={createInspectionCasePending}
                  name="applicable_standard"
                  onChange={(event) => setApplicableStandardInput(event.target.value)}
                  ref={reassessmentInputRef}
                  value={applicableStandardInput}
                />
              </label>
              {createInspectionCaseError ? (
                <p className="form-error" role="alert">
                  {createInspectionCaseError}
                </p>
              ) : null}
              <div className="panel-actions reassessment-dialog-actions">
                <button disabled={createInspectionCasePending} type="submit">
                  {createInspectionCasePending ? "Đang tạo..." : "Tạo hồ sơ tái đánh giá"}
                </button>
                <button disabled={createInspectionCasePending} onClick={closeReassessmentDialog} type="button">
                  Hủy
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {changeRequestDialogOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <section aria-labelledby="change-request-dialog-title" aria-modal="true" className="panel reassessment-dialog" role="dialog">
            <header className="panel-header reassessment-dialog-header">
              <div>
                <h2 id="change-request-dialog-title">Tạo yêu cầu thay đổi</h2>
                <p>{createChangeRequestAction?.detail}</p>
              </div>
            </header>
            <form className="stack-form reassessment-form" onSubmit={handleCreateChangeRequestSubmit}>
              <label><span>Phạm vi</span><input aria-label="Phạm vi yêu cầu thay đổi" disabled={createChangeRequestPending} onChange={(event) => setCreateChangeRequestDraft((current) => ({ ...current, scopeLabel: event.target.value }))} value={createChangeRequestDraft.scopeLabel} /></label>
              <label><span>Ngày đề nghị</span><input aria-label="Ngày tạo yêu cầu thay đổi" disabled={createChangeRequestPending} onChange={(event) => setCreateChangeRequestDraft((current) => ({ ...current, submittedOn: event.target.value }))} type="date" value={createChangeRequestDraft.submittedOn} /></label>
              <label><span>Đơn vị/người đề nghị</span><input aria-label="Người tạo yêu cầu thay đổi" disabled={createChangeRequestPending} onChange={(event) => setCreateChangeRequestDraft((current) => ({ ...current, requesterName: event.target.value }))} value={createChangeRequestDraft.requesterName} /></label>
              <label><span>Mô tả</span><textarea aria-label="Mô tả yêu cầu thay đổi" disabled={createChangeRequestPending} onChange={(event) => setCreateChangeRequestDraft((current) => ({ ...current, description: event.target.value }))} value={createChangeRequestDraft.description} /></label>
              {createChangeRequestError ? <p className="form-error" role="alert">{createChangeRequestError}</p> : null}
              <div className="panel-actions reassessment-dialog-actions">
                <button disabled={createChangeRequestPending} type="submit">{createChangeRequestPending ? "Đang tạo..." : "Tạo yêu cầu thay đổi"}</button>
                <button disabled={createChangeRequestPending} onClick={closeChangeRequestDialog} type="button">Hủy</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {!resultsLoading && resultsTotalCount === 0 ? (
        <EmptyState title="Không có kết quả" description="Không tìm thấy cơ sở phù hợp với bộ lọc hiện tại." />
      ) : null}

      {deepLinkError ? <p className="form-error" role="alert">{deepLinkError}</p> : null}

      {resultsTotalCount > 0 ? (
        deepLinkError ? null : workspaceError ? (
          <ErrorState message={workspaceError} />
        ) : workspaceLoading || !workspace ? (
          <section className="panel panel-tight facility-workspace-panel">
            <EmptyState title="Đang tải workspace" description="Đang đồng bộ ngữ cảnh cơ sở, dây chuyền và chứng nhận hiện hành." />
          </section>
        ) : (
          <FacilityWorkspaceTabs
            activeEventTab={activeTab}
            caseWorkspace={selectedCaseWorkspace}
            caseWorkspaceError={caseWorkspaceError}
            caseWorkspaceLoading={caseWorkspaceLoading}
            changeRequestWorkspace={selectedChangeRequestWorkspace}
            changeRequestWorkspaceError={changeRequestWorkspaceError}
            changeRequestWorkspaceLoading={changeRequestWorkspaceLoading}
            changeRequestMutations={{
              onUpdateHeader: handleChangeRequestHeaderUpdate,
              onCreateDetail: handleChangeRequestDetailCreate,
              onUpdateDetail: handleChangeRequestDetailUpdate,
              onUpsertApproval: handleChangeApprovalUpsert,
              onTransition: handleChangeRequestTransition,
              onIssueCertificateSuccessor: handleChangeRequestCertificateSuccessorIssue,
            }}
            eligibilityCertificateDetail={eligibilityCertificateDetail}
            eligibilityCertificateDetailError={eligibilityCertificateDetailError}
            eligibilityCertificateDetailLoading={eligibilityCertificateDetailLoading}
            eligibilityCertificates={eligibilityCertificates}
            eligibilityCertificatesError={eligibilityCertificatesError}
            eligibilityCertificatesLoading={eligibilityCertificatesLoading}
            eligibilityIssueReadiness={eligibilityIssueReadiness}
            eligibilityBasisCertificates={eligibilityBasisCertificates}
            eligibilityBasisLoading={eligibilityBasisLoading}
            eligibilityBasisError={eligibilityBasisError}
            eligibilityPromotionError={eligibilityPromotionError}
            eligibilityPromotionPending={eligibilityPromotionPending}
            gxpCertificateDetail={gxpCertificateDetail}
            gxpCertificateDetailError={gxpCertificateDetailError}
            gxpCertificateDetailLoading={gxpCertificateDetailLoading}
            gxpCertificatePromotionError={gxpCertificatePromotionError}
            gxpCertificatePromotionPending={gxpCertificatePromotionPending}
            gxpCertificates={gxpCertificates}
            gxpCertificatesError={gxpCertificatesError}
            gxpCertificatesLoading={gxpCertificatesLoading}
            history={workspace.history}
            onEligibilityCertificateSelect={setSelectedEligibilityCertificateId}
            onIssueBusinessEligibility={handleIssueBusinessEligibility}
            onEligibilityCertificateEditLatestVersion={handleBusinessEligibilityLatestVersionUpdate}
            onEligibilityCertificatePromote={handleBusinessEligibilityPromote}
            onEventTabChange={setActiveTab}
            onFacilityTabChange={setSelectedFacilityTab}
            onGxpCertificateSelect={setSelectedGxpCertificateId}
            onGxpCertificatePromote={handleGxpCertificatePromote}
            onGxpCertificateEditLatestVersion={handleGxpCertificateLatestVersionUpdate}
            onIssueCertificate={handleIssueGxpCertificate}
            onHistorySelect={(historyId) => {
              setHistoryResolution("none");
              setDeepLinkError(null);
              setSelectedHistoryId(historyId);
            }}
            onCaseApplicationSave={handleCaseApplicationSave}
            onCaseAssessmentSave={handleCaseAssessmentSave}
            onAssessCapaCycle={handleAssessCapaCycle}
            onCreateCapaCycle={handleCreateCapaCycle}
            onInspectionOutcomeSave={handleInspectionOutcomeSave}
            onInspectionPeriodSegmentsSave={handleInspectionPeriodSegmentsSave}
            onCreateApprovalSubmission={handleCreateApprovalSubmission}
            onCompleteApprovalSubmission={handleCompleteApprovalSubmission}
            onTransitionCase={handleCaseTransition}
            onFinalizeInspectionOutcome={handleFinalizeInspectionOutcome}
            onInspectionTeamSave={handleInspectionTeamSave}
            onLoadInspectionTeamIdentityOptions={handleLoadInspectionTeamIdentityOptions}
            onEvaluationScopeSave={handleEvaluationScopeSave}
            onInspectionPlanSave={handleInspectionPlanSave}
            onLoadDocumentDetail={handleLoadDocumentDetail}
            onOpenDocument={handleOpenDocument}
            onResolveInspectionFolder={handleResolveInspectionFolder}
            onSelectedRemediationCycleChange={setSelectedRemediationCycleId}
            onSubmitCapaCycle={handleSubmitCapaCycle}
            onUpdateCapaCycle={handleUpdateCapaCycle}
            selectedEligibilityCertificateId={selectedEligibilityCertificateId}
            selectedFacilityTab={selectedFacilityTab}
            selectedGxpCertificateId={selectedGxpCertificateId}
            selectedHistory={selectedHistory}
            selectedHistoryId={selectedHistoryId}
            selectedRemediationCycleId={selectedRemediationCycleId}
            summary={workspace.summary}
          />
        )
      ) : null}
    </section>
  );
}
