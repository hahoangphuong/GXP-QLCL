import { useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import type {
  BusinessEligibilityDetail,
  BusinessEligibilityIssueActionReadiness,
  BusinessEligibilityIssueRequest,
  BusinessEligibilityLatestVersionUpsertRequest,
  CapaCycleAssessRequest,
  CapaCycleCreateRequest,
  CapaCycleSubmitRequest,
  CapaCycleUpdateRequest,
  BusinessEligibilityListItem,
  CaseApplicationUpsertRequest,
  CaseAssessmentUpsertRequest,
  CaseWorkspace,
  ChangeRequestWorkspace,
  ContextualDocumentAction,
  DocumentDetail,
  FacilityHistoryItem,
  FacilityWorkspaceSummary,
  GxpCertificateDetail,
  GxpCertificateListItem,
  CertificateLatestVersionUpsertRequest,
  CertificateIssueRequest,
  InspectionOutcomeUpsertRequest,
  InspectionFinalEvaluationRequest,
  InspectionTeamIdentityOption,
  InspectionTeamUpsertRequest,
  EvaluationScopeUpsertRequest,
  InspectionPlanUpsertRequest,
  InspectionFolderLookup,
} from "../../types";
import { StatusBadge } from "../../components/StatusBadge";
import { EventWorkspace } from "./EventWorkspace";
import type { ChangeRequestMutationHandlers } from "./ChangeRequestMutationWorkspace";
import { BusinessEligibilityWorkspace } from "./BusinessEligibilityWorkspace";
import { FacilitySummary } from "./FacilitySummary";
import { GxpCertificateWorkspace } from "./GxpCertificateWorkspace";
import { FACILITY_TABS, type FacilityTab } from "./facilityTabs";

export function FacilityWorkspaceTabs({
  summary,
  selectedFacilityTab,
  onFacilityTabChange,
  selectedHistory,
  caseWorkspace,
  caseWorkspaceLoading,
  caseWorkspaceError,
  changeRequestWorkspace,
  changeRequestWorkspaceLoading,
  changeRequestWorkspaceError,
  changeRequestMutations,
  activeEventTab,
  onEventTabChange,
  gxpCertificates,
  gxpCertificatesLoading,
  gxpCertificatesError,
  selectedGxpCertificateId,
  onGxpCertificateSelect,
  gxpCertificateDetail,
  gxpCertificateDetailLoading,
  gxpCertificateDetailError,
  onGxpCertificatePromote,
  onGxpCertificateEditLatestVersion,
  onIssueCertificate,
  gxpCertificatePromotionError,
  gxpCertificatePromotionPending,
  eligibilityCertificates,
  eligibilityCertificatesLoading,
  eligibilityCertificatesError,
  selectedEligibilityCertificateId,
  onEligibilityCertificateSelect,
  eligibilityCertificateDetail,
  eligibilityCertificateDetailLoading,
  eligibilityCertificateDetailError,
  eligibilityIssueReadiness,
  eligibilityBasisCertificates,
  eligibilityBasisLoading,
  eligibilityBasisError,
  eligibilityPromotionError,
  eligibilityPromotionPending,
  onIssueBusinessEligibility,
  onEligibilityCertificateEditLatestVersion,
  onEligibilityCertificatePromote,
  onCaseApplicationSave,
  onCaseAssessmentSave,
  onInspectionPlanSave,
  onInspectionOutcomeSave,
  onInspectionPeriodSegmentsSave,
  onCreateApprovalSubmission,
  onCompleteApprovalSubmission,
  onTransitionCase,
  onInspectionTeamSave,
  onLoadInspectionTeamIdentityOptions,
  onEvaluationScopeSave,
  onOpenDocument,
  onCreateDocument,
  onLoadDocumentDetail,
  selectedRemediationCycleId,
  onSelectedRemediationCycleChange,
  onCreateCapaCycle,
  onUpdateCapaCycle,
  onSubmitCapaCycle,
  onAssessCapaCycle,
  onResolveInspectionFolder,
  onFinalizeInspectionOutcome,
}: {
  summary: FacilityWorkspaceSummary;
  selectedFacilityTab: FacilityTab;
  onFacilityTabChange: (tab: FacilityTab) => void;
  selectedHistory: FacilityHistoryItem | null;
  caseWorkspace: CaseWorkspace | null;
  caseWorkspaceLoading: boolean;
  caseWorkspaceError: string | null;
  changeRequestWorkspace: ChangeRequestWorkspace | null;
  changeRequestWorkspaceLoading: boolean;
  changeRequestWorkspaceError: string | null;
  changeRequestMutations: ChangeRequestMutationHandlers;
  activeEventTab: string;
  onEventTabChange: (tab: string) => void;
  gxpCertificates: GxpCertificateListItem[];
  gxpCertificatesLoading: boolean;
  gxpCertificatesError: string | null;
  selectedGxpCertificateId: string | null;
  onGxpCertificateSelect: (certificateId: string) => void;
  gxpCertificateDetail: GxpCertificateDetail | null;
  gxpCertificateDetailLoading: boolean;
  gxpCertificateDetailError: string | null;
  onGxpCertificatePromote: (expectedVersion: number) => Promise<void>;
  onGxpCertificateEditLatestVersion: (payload: CertificateLatestVersionUpsertRequest) => Promise<void>;
  onIssueCertificate: (payload: CertificateIssueRequest) => Promise<void>;
  gxpCertificatePromotionError: string | null;
  gxpCertificatePromotionPending: boolean;
  eligibilityCertificates: BusinessEligibilityListItem[];
  eligibilityCertificatesLoading: boolean;
  eligibilityCertificatesError: string | null;
  selectedEligibilityCertificateId: string | null;
  onEligibilityCertificateSelect: (certificateId: string) => void;
  eligibilityCertificateDetail: BusinessEligibilityDetail | null;
  eligibilityCertificateDetailLoading: boolean;
  eligibilityCertificateDetailError: string | null;
  eligibilityIssueReadiness: BusinessEligibilityIssueActionReadiness | null;
  eligibilityBasisCertificates: GxpCertificateListItem[];
  eligibilityBasisLoading: boolean;
  eligibilityBasisError: string | null;
  eligibilityPromotionError: string | null;
  eligibilityPromotionPending: boolean;
  onIssueBusinessEligibility: (payload: BusinessEligibilityIssueRequest) => Promise<void>;
  onEligibilityCertificateEditLatestVersion: (payload: BusinessEligibilityLatestVersionUpsertRequest) => Promise<void>;
  onEligibilityCertificatePromote: (expectedVersion: number) => Promise<void>;
  onCaseApplicationSave: (payload: CaseApplicationUpsertRequest) => Promise<void>;
  onCaseAssessmentSave: (payload: CaseAssessmentUpsertRequest) => Promise<void>;
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
  onInspectionPeriodSegmentsSave: (payload: import("../../types").InspectionPeriodSegmentsUpsertRequest) => Promise<void>;
  onCreateApprovalSubmission: (stage: "PCT" | "CT", payload: import("../../types").InspectionApprovalSubmissionCreateRequest) => Promise<import("../../types").InspectionApprovalSubmissionMutationResponse>;
  onCompleteApprovalSubmission: (submissionId: string, payload: import("../../types").InspectionApprovalSubmissionCompleteRequest) => Promise<import("../../types").InspectionApprovalSubmissionMutationResponse>;
  onTransitionCase: (payload: import("../../types").CaseTransitionRequest) => Promise<void>;
  onInspectionTeamSave: (payload: InspectionTeamUpsertRequest) => Promise<void>;
  onLoadInspectionTeamIdentityOptions: () => Promise<InspectionTeamIdentityOption[]>;
  onEvaluationScopeSave: (payload: EvaluationScopeUpsertRequest) => Promise<void>;
  onOpenDocument: (caseId: string, item: ContextualDocumentAction, isCurrentDocument?: () => boolean) => Promise<void>;
  onCreateDocument: (
    caseId: string,
    item: ContextualDocumentAction,
    action: ContextualDocumentAction["actions"][number],
  ) => Promise<void>;
  onLoadDocumentDetail: (documentId: string) => Promise<DocumentDetail>;
  selectedRemediationCycleId: string | null;
  onSelectedRemediationCycleChange: (cycleId: string | null) => void;
  onCreateCapaCycle: (payload: CapaCycleCreateRequest) => Promise<void>;
  onUpdateCapaCycle: (cycleId: string, payload: CapaCycleUpdateRequest) => Promise<void>;
  onSubmitCapaCycle: (cycleId: string, payload: CapaCycleSubmitRequest) => Promise<void>;
  onAssessCapaCycle: (cycleId: string, payload: CapaCycleAssessRequest) => Promise<void>;
  onResolveInspectionFolder: () => Promise<InspectionFolderLookup>;
  onFinalizeInspectionOutcome?: (payload: InspectionFinalEvaluationRequest) => Promise<void>;
}) {
  const tabGroupId = useId();
  const selectedIndex = FACILITY_TABS.indexOf(selectedFacilityTab);
  const [focusedIndex, setFocusedIndex] = useState(selectedIndex);
  const tabListRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useLayoutEffect(() => {
    setFocusedIndex(selectedIndex);
    // External selection updates the entry point without stealing focus from
    // history rows or form controls outside this tablist.
    if (tabListRef.current?.contains(document.activeElement)) tabRefs.current[selectedIndex]?.focus();
  }, [selectedIndex, summary.site_id, summary.selected_gxp_type, summary.selected_production_line_id, summary.selected_line_code, summary.production_line_identity_state]);

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    switch (event.key) {
      case "ArrowLeft": next = (index + FACILITY_TABS.length - 1) % FACILITY_TABS.length; break;
      case "ArrowRight": next = (index + 1) % FACILITY_TABS.length; break;
      case "Home": next = 0; break;
      case "End": next = FACILITY_TABS.length - 1; break;
      case "Enter":
      case " ":
        event.preventDefault();
        onFacilityTabChange(FACILITY_TABS[index]);
        return;
      default: return;
    }
    event.preventDefault();
    setFocusedIndex(next);
    tabRefs.current[next]?.focus();
  }

  const selectedTabContent = (
    <>
    {selectedFacilityTab === "Thông tin chung" ? (
      <FacilitySummary summary={summary} />
    ) : null}

    {selectedFacilityTab === "Các đợt kiểm tra & thay đổi" ? (
      <div className="event-workspace-detail-pane detail-pane">
        <EventWorkspace
          activeTab={activeEventTab}
          caseWorkspace={caseWorkspace}
          caseWorkspaceError={caseWorkspaceError}
          caseWorkspaceLoading={caseWorkspaceLoading}
          changeRequestWorkspace={changeRequestWorkspace}
          changeRequestWorkspaceError={changeRequestWorkspaceError}
          changeRequestWorkspaceLoading={changeRequestWorkspaceLoading}
          changeRequestMutations={changeRequestMutations}
          onCaseApplicationSave={onCaseApplicationSave}
          onCaseAssessmentSave={onCaseAssessmentSave}
          onAssessCapaCycle={onAssessCapaCycle}
          onResolveInspectionFolder={onResolveInspectionFolder}
          onCreateCapaCycle={onCreateCapaCycle}
          onInspectionOutcomeSave={onInspectionOutcomeSave}
          onInspectionPeriodSegmentsSave={onInspectionPeriodSegmentsSave}
          onCreateApprovalSubmission={onCreateApprovalSubmission}
          onCompleteApprovalSubmission={onCompleteApprovalSubmission}
          onTransitionCase={onTransitionCase}
          onFinalizeInspectionOutcome={onFinalizeInspectionOutcome}
          onInspectionTeamSave={onInspectionTeamSave}
          onLoadInspectionTeamIdentityOptions={onLoadInspectionTeamIdentityOptions}
          onEvaluationScopeSave={onEvaluationScopeSave}
          onInspectionPlanSave={onInspectionPlanSave}
          onIssueCertificate={onIssueCertificate}
          onCreateDocument={onCreateDocument}
          onLoadDocumentDetail={onLoadDocumentDetail}
          onOpenDocument={onOpenDocument}
          onSelectedRemediationCycleChange={onSelectedRemediationCycleChange}
          onSubmitCapaCycle={onSubmitCapaCycle}
          onTabChange={onEventTabChange}
          onUpdateCapaCycle={onUpdateCapaCycle}
          selectedRemediationCycleId={selectedRemediationCycleId}
          selectedHistory={selectedHistory}
        />
      </div>
    ) : null}

    {selectedFacilityTab === "Giấy chứng nhận GxP" ? (
      <GxpCertificateWorkspace
        detail={gxpCertificateDetail}
        detailError={gxpCertificateDetailError}
        detailLoading={gxpCertificateDetailLoading}
        items={gxpCertificates}
        listError={gxpCertificatesError}
        listLoading={gxpCertificatesLoading}
        onSelectCertificate={onGxpCertificateSelect}
      onPromoteCurrent={onGxpCertificatePromote}
      onEditLatestVersion={onGxpCertificateEditLatestVersion}
        promotionError={gxpCertificatePromotionError}
        promotionPending={gxpCertificatePromotionPending}
        selectedCertificateId={selectedGxpCertificateId}
      />
    ) : null}

    {selectedFacilityTab === "Giấy chứng nhận đủ điều kiện" ? (
      <BusinessEligibilityWorkspace
        detail={eligibilityCertificateDetail}
        detailError={eligibilityCertificateDetailError}
        detailLoading={eligibilityCertificateDetailLoading}
        items={eligibilityCertificates}
        listError={eligibilityCertificatesError}
        listLoading={eligibilityCertificatesLoading}
        issueReadiness={eligibilityIssueReadiness}
        basisCertificates={eligibilityBasisCertificates}
        basisLoading={eligibilityBasisLoading}
        basisError={eligibilityBasisError}
        onIssue={onIssueBusinessEligibility}
        onEditLatestVersion={onEligibilityCertificateEditLatestVersion}
        onPromoteCurrent={onEligibilityCertificatePromote}
        promotionError={eligibilityPromotionError}
        promotionPending={eligibilityPromotionPending}
        onSelectCertificate={onEligibilityCertificateSelect}
        selectedCertificateId={selectedEligibilityCertificateId}
      />
    ) : null}
    </>
  );

  return (
    <section className="panel panel-tight facility-workspace-panel">
      <header className="facility-context-bar">
        <div className="facility-context-identity">
          <span className="facility-context-icon" aria-hidden="true">CS</span>
          <div>
            <div className="facility-context-title-line">
              <h2>{summary.facility_name}</h2>
              <span className="facility-context-code">{summary.context_code ?? summary.facility_code ?? "Chưa có mã"}</span>
            </div>
            <p>{summary.address ?? summary.company_name}</p>
          </div>
        </div>
        <dl className="facility-context-facts">
          <div><dt>GxP</dt><dd>{summary.selected_gxp_type ?? (summary.gxp_types.join(", ") || "Chưa có")}</dd></div>
          <div><dt>Dây chuyền</dt><dd>{summary.selected_line_code ?? "Toàn cơ sở"}</dd></div>
          <div><dt>Tỉnh/thành</dt><dd>{summary.province_name ?? "Chưa có"}</dd></div>
          <div><dt>Trạng thái gần nhất</dt><dd><StatusBadge value={summary.current_state} /></dd></div>
        </dl>
      </header>
      <div
        className="workspace-tabs facility-tabs tab-strip tab-strip-primary"
        role="tablist"
        aria-label="Tab nghiệp vụ cơ sở"
        ref={tabListRef}
        onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setFocusedIndex(selectedIndex); }}
      >
        {FACILITY_TABS.map((tab, index) => (
          <button
            aria-selected={selectedFacilityTab === tab}
            aria-controls={`${tabGroupId}-panel-${index}`}
            id={`${tabGroupId}-tab-${index}`}
            className={selectedFacilityTab === tab ? "workspace-tab active" : "workspace-tab"}
            key={tab}
            ref={(element) => { tabRefs.current[index] = element; }}
            tabIndex={focusedIndex === index ? 0 : -1}
            onFocus={() => setFocusedIndex(index)}
            onKeyDown={(event) => handleTabKeyDown(event, index)}
            onClick={() => { setFocusedIndex(index); onFacilityTabChange(tab); }}
            role="tab"
            type="button"
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="facility-tab-body">
        {FACILITY_TABS.map((tab, index) => (
          <div
            className="facility-tab-panel"
            key={tab}
            id={`${tabGroupId}-panel-${index}`}
            role="tabpanel"
            aria-labelledby={`${tabGroupId}-tab-${index}`}
            hidden={selectedFacilityTab !== tab}
            tabIndex={0}
          >
            {selectedFacilityTab === tab ? selectedTabContent : null}
          </div>
        ))}
      </div>
    </section>
  );
}
