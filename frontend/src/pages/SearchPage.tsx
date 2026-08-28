import { startTransition, useDeferredValue, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { ActionCard } from "../features/search/ActionCard";
import { FacilityTable } from "../features/search/FacilityTable";
import { FacilityWorkspaceTabs } from "../features/search/FacilityWorkspaceTabs";
import { getCaseDetail, getFacilityWorkspace, searchFacilities } from "../lib/api";
import type { CaseDetail, FacilitySearchResult, FacilityWorkspace } from "../types";

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
  const [selectedCaseDetail, setSelectedCaseDetail] = useState<CaseDetail | null>(null);
  const [caseDetailLoading, setCaseDetailLoading] = useState(false);
  const [caseDetailError, setCaseDetailError] = useState<string | null>(null);

  const selectedResult = results.find((item) => item.result_key === selectedResultKey) ?? null;
  const selectedHistory = workspace?.history.find((item) => item.id === selectedHistoryId) ?? null;
  const hasMoreResults = results.length < resultsTotalCount;

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
    if (!access.canLoadSecureApi) {
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
      access.auth,
      access.useStubAuth,
      access.bearerToken,
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
    access,
    caseStates,
    certificateExpiringWithinDays,
    certificateState,
    changeRequestStates,
    deferredCertificateScope,
    deferredFacilityName,
    gxpType,
    province,
    resultsOffset,
  ]);

  useEffect(() => {
    if (!selectedResult || !access.canLoadSecureApi) {
      setWorkspace(null);
      return;
    }
    let cancelled = false;
    setWorkspaceLoading(true);
    void getFacilityWorkspace(
      selectedResult.site_id,
      access.auth,
      access.useStubAuth,
      selectedResult.gxp_type,
      selectedResult.line_code,
      access.bearerToken,
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
  }, [access, selectedResult]);

  useEffect(() => {
    setSelectedCaseDetail(null);
    setCaseDetailError(null);
    setCaseDetailLoading(false);
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      return;
    }
    let cancelled = false;
    setCaseDetailLoading(true);
    void getCaseDetail(selectedHistory.id, access.auth, access.useStubAuth, access.bearerToken)
      .then((payload) => {
        if (!cancelled) {
          setSelectedCaseDetail(payload);
          setCaseDetailError(null);
          setCaseDetailLoading(false);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setSelectedCaseDetail(null);
          setCaseDetailError(error.message);
          setCaseDetailLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [access, selectedHistory]);

  function resetDependentContext() {
    setResultsOffset(0);
    setSelectedResultKey(null);
    setSelectedHistoryId(null);
    setSelectedFacilityTab(DEFAULT_FACILITY_TAB);
    setActiveTab(DEFAULT_EVENT_TAB);
    setWorkspace(null);
    setWorkspaceError(null);
    setSelectedCaseDetail(null);
    setCaseDetailError(null);
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
  if (!access.canLoadSecureApi) {
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
            caseDetail={selectedCaseDetail}
            caseDetailError={caseDetailError}
            caseDetailLoading={caseDetailLoading}
            history={workspace.history}
            onEventTabChange={setActiveTab}
            onFacilityTabChange={setSelectedFacilityTab}
            onHistorySelect={setSelectedHistoryId}
            selectedFacilityTab={selectedFacilityTab}
            selectedHistory={selectedHistory}
            selectedHistoryId={selectedHistoryId}
            summary={workspace.summary}
          />
        )
      ) : null}
    </section>
  );
}
