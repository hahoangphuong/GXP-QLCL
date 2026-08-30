import { startTransition, useDeferredValue, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { ActionCard } from "../features/search/ActionCard";
import { FacilityTable } from "../features/search/FacilityTable";
import { FacilityWorkspaceTabs } from "../features/search/FacilityWorkspaceTabs";
import {
  getBusinessEligibilityDetail,
  getCaseWorkspace,
  getChangeRequestWorkspace,
  getFacilityWorkspace,
  getGxpCertificateDetail,
  listSiteBusinessEligibilityCertificates,
  listSiteGxpCertificates,
  searchFacilities,
} from "../lib/api";
import type {
  BusinessEligibilityDetail,
  BusinessEligibilityListItem,
  CaseWorkspace,
  ChangeRequestWorkspace,
  FacilitySearchResult,
  FacilityWorkspace,
  GxpCertificateDetail,
  GxpCertificateListItem,
} from "../types";

const DEFAULT_EVENT_TAB = "Hồ sơ";
const DEFAULT_FACILITY_TAB = "Các đợt kiểm tra & thay đổi";
const RESULT_PAGE_SIZE = 100;
const GXP_FILTER_OPTIONS = new Set(["ALL", "GMP", "GLP", "GMPbb"]);

function normalizeGxpSelection(value: string | null): string {
  return value && GXP_FILTER_OPTIONS.has(value) ? value : "ALL";
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

export function SearchPage({
  access,
  statusError,
}: {
  access: ApiAccess;
  statusError: string | null;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [facilityName, setFacilityName] = useState(searchParams.get("facility_name") ?? searchParams.get("q") ?? "");
  const [certificateScope, setCertificateScope] = useState(searchParams.get("certificate_scope") ?? "");
  const [gxpType, setGxpType] = useState(normalizeGxpSelection(searchParams.get("gxp_type")));
  const [province] = useState(searchParams.get("province") ?? "");
  const [caseStates, setCaseStates] = useState<string[]>(searchParams.getAll("case_state"));
  const [certificateState] = useState(searchParams.get("certificate_state") ?? "");
  const [certificateExpiringWithinDays] = useState(searchParams.get("certificate_expiring_within_days") ?? "");
  const [changeRequestStates] = useState<string[]>(searchParams.getAll("change_request_state"));
  const [resultsOffset, setResultsOffset] = useState(0);
  const [selectedResultKey, setSelectedResultKey] = useState<string | null>(searchParams.get("result_key"));
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(searchParams.get("history_id"));
  const [selectedFacilityTab, setSelectedFacilityTab] = useState(searchParams.get("facility_tab") ?? DEFAULT_FACILITY_TAB);
  const [activeTab, setActiveTab] = useState(searchParams.get("event_tab") ?? DEFAULT_EVENT_TAB);
  const deferredFacilityName = useDeferredValue(facilityName);
  const deferredCertificateScope = useDeferredValue(certificateScope);

  const [results, setResults] = useState<FacilitySearchResult[]>([]);
  const [resultsLoading, setResultsLoading] = useState(true);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [resultsTotalCount, setResultsTotalCount] = useState(0);
  const [workspace, setWorkspace] = useState<FacilityWorkspace | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
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
  const [eligibilityCertificates, setEligibilityCertificates] = useState<BusinessEligibilityListItem[]>([]);
  const [eligibilityCertificatesLoading, setEligibilityCertificatesLoading] = useState(false);
  const [eligibilityCertificatesError, setEligibilityCertificatesError] = useState<string | null>(null);
  const [selectedEligibilityCertificateId, setSelectedEligibilityCertificateId] = useState<string | null>(null);
  const [eligibilityCertificateDetail, setEligibilityCertificateDetail] = useState<BusinessEligibilityDetail | null>(null);
  const [eligibilityCertificateDetailLoading, setEligibilityCertificateDetailLoading] = useState(false);
  const [eligibilityCertificateDetailError, setEligibilityCertificateDetailError] = useState<string | null>(null);
  const { auth, useStubAuth, bearerToken, canLoadSecureApi } = access;

  const selectedResult = results.find((item) => item.result_key === selectedResultKey) ?? null;
  const selectedHistory = workspace?.history.find((item) => item.id === selectedHistoryId) ?? null;
  const hasMoreResults = results.length < resultsTotalCount;

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
  }

  useEffect(() => {
    const nextParams = new URLSearchParams();
    if (deferredFacilityName.trim()) {
      nextParams.set("facility_name", deferredFacilityName.trim());
    }
    if (deferredCertificateScope.trim()) {
      nextParams.set("certificate_scope", deferredCertificateScope.trim());
    }
    if (gxpType !== "ALL") {
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
    if (selectedResult) {
      nextParams.set("result_key", selectedResult.result_key);
      nextParams.set("site_id", selectedResult.site_id);
      if (selectedResult.line_code) {
        nextParams.set("line_code", selectedResult.line_code);
      }
      if (selectedResult.gxp_type) {
        nextParams.set("context_gxp", selectedResult.gxp_type);
      }
    }
    if (selectedHistoryId) {
      nextParams.set("history_id", selectedHistoryId);
    }
    if (selectedFacilityTab !== DEFAULT_FACILITY_TAB) {
      nextParams.set("facility_tab", selectedFacilityTab);
    }
    if (activeTab !== DEFAULT_EVENT_TAB) {
      nextParams.set("event_tab", activeTab);
    }
    setSearchParams(nextParams, { replace: true });
  }, [
    activeTab,
    caseStates,
    certificateExpiringWithinDays,
    certificateState,
    changeRequestStates,
    deferredCertificateScope,
    deferredFacilityName,
    gxpType,
    province,
    selectedFacilityTab,
    selectedHistoryId,
    selectedResult,
    setSearchParams,
  ]);

  useEffect(() => {
    if (!canLoadSecureApi) {
      setResultsLoading(false);
      setResults([]);
      setResultsTotalCount(0);
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
        facility_name: deferredFacilityName.trim() || undefined,
        certificate_scope: deferredCertificateScope.trim() || undefined,
        gxp_type: gxpType === "ALL" ? null : gxpType,
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
        setResults((current) => (isFirstPage ? payload.items : appendUniqueResults(current, payload.items)));
        setResultsTotalCount(payload.total_count);
        setResultsError(null);
        setResultsLoading(false);
        if (isFirstPage) {
          if (payload.items.length === 0) {
            setSelectedResultKey(null);
            setSelectedHistoryId(null);
            setWorkspace(null);
            resetCertificateWorkspaceState();
            return;
          }
          const hasSelection = selectedResultKey && payload.items.some((item) => item.result_key === selectedResultKey);
          if (!hasSelection) {
            setSelectedResultKey(payload.items[0].result_key);
          }
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
    gxpType,
    province,
    resultsOffset,
    useStubAuth,
  ]);

  useEffect(() => {
    if (!selectedResult || !canLoadSecureApi) {
      setWorkspace(null);
      setSelectedCaseWorkspace(null);
      setCaseWorkspaceError(null);
      setCaseWorkspaceLoading(false);
      setSelectedChangeRequestWorkspace(null);
      setChangeRequestWorkspaceError(null);
      setChangeRequestWorkspaceLoading(false);
      resetCertificateWorkspaceState();
      return;
    }
    let cancelled = false;
    setWorkspaceLoading(true);
    resetCertificateWorkspaceState();
    void getFacilityWorkspace(
      selectedResult.site_id,
      auth,
      useStubAuth,
      selectedResult.gxp_type,
      selectedResult.line_code,
      bearerToken,
    )
      .then((payload) => {
        if (!cancelled) {
          setWorkspace(payload);
          setWorkspaceError(null);
          setWorkspaceLoading(false);
          setSelectedHistoryId((current) =>
            current && payload.history.some((row) => row.id === current) ? current : payload.history[0]?.id ?? null,
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
    setSelectedCaseWorkspace(null);
    setCaseWorkspaceError(null);
    setCaseWorkspaceLoading(false);
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      return;
    }
    let cancelled = false;
    setCaseWorkspaceLoading(true);
    void getCaseWorkspace(selectedHistory.id, auth, useStubAuth, bearerToken)
      .then((payload) => {
        if (!cancelled) {
          setSelectedCaseWorkspace(payload);
          setCaseWorkspaceError(null);
          setCaseWorkspaceLoading(false);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setSelectedCaseWorkspace(null);
          setCaseWorkspaceError(error.message);
          setCaseWorkspaceLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, selectedHistory, useStubAuth]);

  useEffect(() => {
    setSelectedChangeRequestWorkspace(null);
    setChangeRequestWorkspaceError(null);
    setChangeRequestWorkspaceLoading(false);
    if (!selectedHistory || selectedHistory.source_type !== "change_request") {
      return;
    }
    let cancelled = false;
    setChangeRequestWorkspaceLoading(true);
    void getChangeRequestWorkspace(selectedHistory.id, auth, useStubAuth, bearerToken)
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
  }, [auth, bearerToken, selectedHistory, useStubAuth]);

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

  function resetDependentContext() {
    setResultsOffset(0);
    setSelectedResultKey(null);
    setSelectedHistoryId(null);
    setSelectedFacilityTab(DEFAULT_FACILITY_TAB);
    setActiveTab(DEFAULT_EVENT_TAB);
    setWorkspace(null);
    setWorkspaceError(null);
    setSelectedCaseWorkspace(null);
    setCaseWorkspaceError(null);
    setCaseWorkspaceLoading(false);
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

  function clearFilters() {
    setFacilityName("");
    setCertificateScope("");
    setGxpType("ALL");
    setCaseStates([]);
    resetDependentContext();
  }

  function loadMoreResults() {
    if (resultsLoading || !hasMoreResults) {
      return;
    }
    setResultsOffset(results.length);
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
            caseState: caseStates.length === 1 ? caseStates[0] : "",
            gxpType,
          }}
          hasMore={hasMoreResults}
          hiddenFilters={{
            province,
            changeRequestStates,
            certificateState,
            certificateExpiringWithinDays,
          }}
          loading={resultsLoading}
          onClear={clearFilters}
          onFilterChange={updateFilter}
          onReachEnd={loadMoreResults}
          onSelect={setSelectedResultKey}
          rows={results}
          selectedResultKey={selectedResultKey}
          showGxpColumn={gxpType === "ALL"}
          totalCount={resultsTotalCount}
        />
        <ActionCard />
      </div>

      {!resultsLoading && resultsTotalCount === 0 ? (
        <EmptyState title="Không có kết quả" description="Không tìm thấy cơ sở phù hợp với bộ lọc hiện tại." />
      ) : null}

      {resultsTotalCount > 0 ? (
        workspaceError ? (
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
            eligibilityCertificateDetail={eligibilityCertificateDetail}
            eligibilityCertificateDetailError={eligibilityCertificateDetailError}
            eligibilityCertificateDetailLoading={eligibilityCertificateDetailLoading}
            eligibilityCertificates={eligibilityCertificates}
            eligibilityCertificatesError={eligibilityCertificatesError}
            eligibilityCertificatesLoading={eligibilityCertificatesLoading}
            gxpCertificateDetail={gxpCertificateDetail}
            gxpCertificateDetailError={gxpCertificateDetailError}
            gxpCertificateDetailLoading={gxpCertificateDetailLoading}
            gxpCertificates={gxpCertificates}
            gxpCertificatesError={gxpCertificatesError}
            gxpCertificatesLoading={gxpCertificatesLoading}
            history={workspace.history}
            onEligibilityCertificateSelect={setSelectedEligibilityCertificateId}
            onEventTabChange={setActiveTab}
            onFacilityTabChange={setSelectedFacilityTab}
            onGxpCertificateSelect={setSelectedGxpCertificateId}
            onHistorySelect={setSelectedHistoryId}
            selectedEligibilityCertificateId={selectedEligibilityCertificateId}
            selectedFacilityTab={selectedFacilityTab}
            selectedGxpCertificateId={selectedGxpCertificateId}
            selectedHistory={selectedHistory}
            selectedHistoryId={selectedHistoryId}
            summary={workspace.summary}
          />
        )
      ) : null}
    </section>
  );
}
