import { startTransition, useDeferredValue, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { EventWorkspace } from "../features/search/EventWorkspace";
import { FacilitySummary } from "../features/search/FacilitySummary";
import { FacilityTable } from "../features/search/FacilityTable";
import { HistoryTable } from "../features/search/HistoryTable";
import { SearchToolbar } from "../features/search/SearchToolbar";
import { getCaseDetail, getFacilityWorkspace, searchFacilities } from "../lib/api";
import type { CaseDetail, FacilitySearchResult, FacilityWorkspace } from "../types";

const DEFAULT_TAB = "Hồ sơ";

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
  const [caseState, setCaseState] = useState(searchParams.get("case_state") ?? "");
  const [certificateState, setCertificateState] = useState(searchParams.get("certificate_state") ?? "");
  const [certificateExpiringWithinDays, setCertificateExpiringWithinDays] = useState(
    searchParams.get("certificate_expiring_within_days") ?? "",
  );
  const deferredQuery = useDeferredValue(query);

  const [results, setResults] = useState<FacilitySearchResult[]>([]);
  const [resultsLoading, setResultsLoading] = useState(true);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(searchParams.get("site_id"));
  const [workspace, setWorkspace] = useState<FacilityWorkspace | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null);
  const [selectedCaseDetail, setSelectedCaseDetail] = useState<CaseDetail | null>(null);
  const [caseDetailError, setCaseDetailError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(DEFAULT_TAB);

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
    if (caseState) {
      nextParams.set("case_state", caseState);
    }
    if (certificateState) {
      nextParams.set("certificate_state", certificateState);
    }
    if (certificateExpiringWithinDays) {
      nextParams.set("certificate_expiring_within_days", certificateExpiringWithinDays);
    }
    if (selectedSiteId) {
      nextParams.set("site_id", selectedSiteId);
    }
    setSearchParams(nextParams, { replace: true });
  }, [
    deferredQuery,
    gxpType,
    province,
    caseState,
    certificateState,
    certificateExpiringWithinDays,
    selectedSiteId,
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
        case_state: caseState || null,
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
          setSelectedSiteId(null);
          return;
        }
        const hasSelection = selectedSiteId && payload.some((item) => item.site_id === selectedSiteId);
        if (!hasSelection) {
          setSelectedSiteId(payload[0].site_id);
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
  }, [access, deferredQuery, gxpType, province, caseState, certificateState, certificateExpiringWithinDays, selectedSiteId]);

  useEffect(() => {
    if (!selectedSiteId || !access.canLoadSecureApi) {
      setWorkspace(null);
      return;
    }
    let cancelled = false;
    setWorkspaceLoading(true);
    void getFacilityWorkspace(selectedSiteId, access.auth, access.useStubAuth, access.bearerToken)
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
  }, [access, selectedSiteId]);

  const selectedHistory = workspace?.history.find((item) => item.id === selectedHistoryId) ?? null;

  useEffect(() => {
    if (!selectedHistory || selectedHistory.source_type !== "case") {
      setSelectedCaseDetail(null);
      setCaseDetailError(null);
      return;
    }
    let cancelled = false;
    void getCaseDetail(selectedHistory.id, access.auth, access.useStubAuth, access.bearerToken)
      .then((payload) => {
        if (!cancelled) {
          setSelectedCaseDetail(payload);
          setCaseDetailError(null);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setCaseDetailError(error.message);
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
        setCaseState(value);
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
    setCaseState("");
    setCertificateState("");
    setCertificateExpiringWithinDays("");
    setSelectedSiteId(null);
    setActiveTab(DEFAULT_TAB);
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
    <section className="page-section">
      <SearchToolbar
        filters={{ query, gxpType, province, caseState, certificateState, certificateExpiringWithinDays }}
        onChange={(field, value) => updateFilter(field, value)}
        onClear={clearFilters}
      />

      {resultsLoading ? <EmptyState title="Đang tra cứu" description="Đang tải danh sách cơ sở từ backend." /> : null}
      {!resultsLoading && results.length === 0 ? (
        <EmptyState title="Không có kết quả" description="Không tìm thấy cơ sở phù hợp với bộ lọc hiện tại." />
      ) : null}

      {results.length > 0 ? (
        <>
          <div className="search-layout">
            <FacilityTable rows={results} selectedSiteId={selectedSiteId} onSelect={setSelectedSiteId} />
            {workspaceError ? (
              <ErrorState message={workspaceError} />
            ) : workspaceLoading || !workspace ? (
              <EmptyState title="Đang tải ngữ cảnh" description="Đang lấy facility summary và history của cơ sở được chọn." />
            ) : (
              <FacilitySummary summary={workspace.summary} />
            )}
          </div>
          {workspaceError ? null : workspaceLoading || !workspace ? null : (
            <>
              <HistoryTable rows={workspace.history} selectedHistoryId={selectedHistoryId} onSelect={setSelectedHistoryId} />
              {caseDetailError ? (
                <ErrorState message={caseDetailError} />
              ) : (
                <EventWorkspace
                  activeTab={activeTab}
                  caseDetail={selectedCaseDetail}
                  onTabChange={setActiveTab}
                  selectedHistory={selectedHistory}
                />
              )}
            </>
          )}
        </>
      ) : null}
    </section>
  );
}
