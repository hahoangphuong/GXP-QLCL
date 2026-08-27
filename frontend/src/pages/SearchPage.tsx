import { startTransition, useDeferredValue, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { FacilityTable } from "../features/search/FacilityTable";
import { HistoryTable } from "../features/search/HistoryTable";
import { SearchToolbar } from "../features/search/SearchToolbar";
import { FacilityWorkspaceTabs } from "../features/search/FacilityWorkspaceTabs";
import { getCaseDetail, getFacilityWorkspace, searchFacilities } from "../lib/api";
import type { CaseDetail, FacilitySearchResult, FacilityWorkspace } from "../types";

const DEFAULT_EVENT_TAB = "Hồ sơ";
const DEFAULT_FACILITY_TAB = "Các đợt kiểm tra & thay đổi";

export function SearchPage({
  access,
  statusError,
}: {
  access: ApiAccess;
  statusError: string | null;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [gxpType, setGxpType] = useState(searchParams.get("gxp_type") ?? "ALL");
  const [province, setProvince] = useState(searchParams.get("province") ?? "");
  const [caseStates, setCaseStates] = useState<string[]>(searchParams.getAll("case_state"));
  const [certificateState, setCertificateState] = useState(searchParams.get("certificate_state") ?? "");
  const [certificateExpiringWithinDays, setCertificateExpiringWithinDays] = useState(
    searchParams.get("certificate_expiring_within_days") ?? "",
  );
  const [changeRequestStates, setChangeRequestStates] = useState<string[]>(searchParams.getAll("change_request_state"));
  const [selectedResultKey, setSelectedResultKey] = useState<string | null>(searchParams.get("result_key"));
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(searchParams.get("history_id"));
  const [selectedFacilityTab, setSelectedFacilityTab] = useState(searchParams.get("facility_tab") ?? DEFAULT_FACILITY_TAB);
  const [activeTab, setActiveTab] = useState(searchParams.get("event_tab") ?? DEFAULT_EVENT_TAB);
  const deferredQuery = useDeferredValue(query);

  const [results, setResults] = useState<FacilitySearchResult[]>([]);
  const [resultsLoading, setResultsLoading] = useState(true);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<FacilityWorkspace | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [selectedCaseDetail, setSelectedCaseDetail] = useState<CaseDetail | null>(null);
  const [caseDetailLoading, setCaseDetailLoading] = useState(false);
  const [caseDetailError, setCaseDetailError] = useState<string | null>(null);

  const selectedResult = results.find((item) => item.result_key === selectedResultKey) ?? null;
  const selectedHistory = workspace?.history.find((item) => item.id === selectedHistoryId) ?? null;

  useEffect(() => {
    const nextParams = new URLSearchParams();
    if (deferredQuery.trim()) {
      nextParams.set("q", deferredQuery.trim());
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
    deferredQuery,
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
      return;
    }
    let cancelled = false;
    setResultsLoading(true);
    void searchFacilities(
      {
        q: deferredQuery.trim() || undefined,
        gxp_type: gxpType === "ALL" ? null : gxpType,
        province: province.trim() || undefined,
        case_state: caseStates,
        change_request_state: changeRequestStates,
        certificate_state: certificateState || null,
        certificate_expiring_within_days: certificateExpiringWithinDays ? Number(certificateExpiringWithinDays) : null,
        limit: 80,
      },
      access.auth,
      access.useStubAuth,
      access.bearerToken,
    )
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setResults(payload);
        setResultsError(null);
        setResultsLoading(false);
        if (payload.length === 0) {
          setSelectedResultKey(null);
          setWorkspace(null);
          return;
        }
        const hasSelection = selectedResultKey && payload.some((item) => item.result_key === selectedResultKey);
        if (!hasSelection) {
          setSelectedResultKey(payload[0].result_key);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setResultsError(error.message);
          setResultsLoading(false);
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
    deferredQuery,
    gxpType,
    province,
    selectedResultKey,
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

  function updateFilter(field: string, value: string) {
    startTransition(() => {
      if (field === "query") {
        setQuery(value);
      } else if (field === "gxpType") {
        setGxpType(value);
      } else if (field === "province") {
        setProvince(value);
      } else if (field === "caseState") {
        setCaseStates(value ? [value] : []);
        setChangeRequestStates([]);
      } else if (field === "certificateState") {
        setCertificateState(value);
      } else if (field === "certificateExpiringWithinDays") {
        setCertificateExpiringWithinDays(value);
      }
    });
  }

  function clearFilters() {
    setQuery("");
    setGxpType("ALL");
    setProvince("");
    setCaseStates([]);
    setChangeRequestStates([]);
    setCertificateState("");
    setCertificateExpiringWithinDays("");
    setSelectedResultKey(null);
    setSelectedHistoryId(null);
    setSelectedFacilityTab(DEFAULT_FACILITY_TAB);
    setActiveTab(DEFAULT_EVENT_TAB);
  }

  if (statusError) {
    return <ErrorState message={statusError} />;
  }
  if (!access.canLoadSecureApi) {
    return <EmptyState title="Cần đăng nhập" description="Đăng nhập để dùng Tra cứu trên authenticated API thật." />;
  }
  if (resultsError) {
    return <ErrorState message={resultsError} />;
  }

  return (
    <section className="page-section search-page">
      <SearchToolbar
        filters={{
          query,
          gxpType,
          province,
          caseState: caseStates.length === 1 ? caseStates[0] : "",
          certificateState,
          certificateExpiringWithinDays,
          changeRequestStates,
        }}
        onChange={(field, value) => updateFilter(field, value)}
        onClear={clearFilters}
      />

      {resultsLoading ? <EmptyState title="Đang tra cứu" description="Đang tải danh sách cơ sở từ backend." /> : null}
      {!resultsLoading && results.length === 0 ? (
        <EmptyState title="Không có kết quả" description="Không tìm thấy cơ sở phù hợp với bộ lọc hiện tại." />
      ) : null}

      {results.length > 0 ? (
        <>
          <div className="search-workspace search-workspace-split">
            <FacilityTable rows={results} selectedResultKey={selectedResultKey} onSelect={setSelectedResultKey} />
            {workspaceError ? (
              <ErrorState message={workspaceError} />
            ) : workspaceLoading || !workspace ? (
              <section className="panel panel-tight history-panel">
                <EmptyState title="Đang tải lịch sử" description="Đang lấy lịch sử theo cơ sở/dây chuyền đang chọn." />
              </section>
            ) : (
              <HistoryTable rows={workspace.history} selectedHistoryId={selectedHistoryId} onSelect={setSelectedHistoryId} />
            )}
          </div>

          {workspaceError ? null : workspaceLoading || !workspace ? (
            <section className="panel panel-tight facility-workspace-panel">
              <EmptyState title="Đang tải workspace" description="Đang đồng bộ ngữ cảnh cơ sở, dây chuyền và chứng nhận hiện hành." />
            </section>
          ) : (
            <FacilityWorkspaceTabs
              activeEventTab={activeTab}
              caseDetail={selectedCaseDetail}
              caseDetailError={caseDetailError}
              caseDetailLoading={caseDetailLoading}
              onEventTabChange={setActiveTab}
              onFacilityTabChange={setSelectedFacilityTab}
              selectedFacilityTab={selectedFacilityTab}
              selectedHistory={selectedHistory}
              summary={workspace.summary}
            />
          )}
        </>
      ) : null}
    </section>
  );
}
