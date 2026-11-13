import type { HistoryState } from "./usePersistedCertificateHistory";
import type { GxpCertificateVersionHistory, BusinessEligibilityVersionHistory } from "../../types";
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
  CaseInspectionPlanReadinessState,
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
import { EventWorkspace } from "./EventWorkspace";
import type { ChangeRequestMutationHandlers } from "./ChangeRequestMutationWorkspace";
import { BusinessEligibilityWorkspace } from "./BusinessEligibilityWorkspace";
import { FacilitySummary } from "./FacilitySummary";
import { GxpCertificateWorkspace } from "./GxpCertificateWorkspace";
import { FACILITY_TABS, FACILITY_TAB_LABELS, type FacilityTab } from "./facilityTabs";
import type { EligibilitySourceState } from "./useBusinessEligibilitySourceEvidence";
import type { CertificateDocumentMetadataState } from "./useCertificateDocumentMetadata";

export function FacilityWorkspaceTabs({
  documentNavigationKey,
  accessGeneration = 0,
  gxpVersionHistory,
  eligibilityVersionHistory,
  eligibilitySourceEvidence,
  gxpDocumentMetadata,
  eligibilityDocumentMetadata,
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
  onNavigateCaseCertificate,
  onOpenGxpCertificateOwningCase,
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
  inspectionPlanReadiness,
  onRetryInspectionPlanReadiness,
  onInspectionOutcomeSave,
  onInspectionPeriodSegmentsSave,
  onCreateApprovalSubmission,
  onCompleteApprovalSubmission,
  onBindApprovalDocument,
  onReadApprovalDocuments,
  onApprovalDocumentsConfirmed,
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
  documentNavigationKey?: string | null;
  accessGeneration?: number | null;
  gxpVersionHistory?: HistoryState<GxpCertificateVersionHistory>;
  eligibilityVersionHistory?: HistoryState<BusinessEligibilityVersionHistory>;
  eligibilitySourceEvidence?: EligibilitySourceState;
  gxpDocumentMetadata?: CertificateDocumentMetadataState;
  eligibilityDocumentMetadata?: CertificateDocumentMetadataState;
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
  onNavigateCaseCertificate?: (certificateId: string) => void;
  onOpenGxpCertificateOwningCase?: (caseId: string, certificateId: string, siteId: string) => void;
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
  inspectionPlanReadiness: CaseInspectionPlanReadinessState | null;
  onRetryInspectionPlanReadiness: () => void;
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
  onInspectionPeriodSegmentsSave: (payload: import("../../types").InspectionPeriodSegmentsUpsertRequest) => Promise<void>;
  onCreateApprovalSubmission: (stage: "PCT" | "CT", payload: import("../../types").InspectionApprovalSubmissionCreateRequest) => Promise<import("../../types").InspectionApprovalSubmissionMutationResponse>;
  onCompleteApprovalSubmission: (submissionId: string, payload: import("../../types").InspectionApprovalSubmissionCompleteRequest) => Promise<import("../../types").InspectionApprovalSubmissionMutationResponse>;
  onBindApprovalDocument?: (id: string, payload: import("../../types").ApprovalDocumentBindRequest) => Promise<import("../../types").ApprovalDocumentBindingResponse>;
  onReadApprovalDocuments?: (id: string) => Promise<import("../../types").ApprovalDocumentReadback>;
  onApprovalDocumentsConfirmed?: (caseId: string) => Promise<void>;
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

  // Return to the *same* canonical Case that issued the selected Certificate.
  // This is navigation only: completion eligibility and any transition remain backend-owned.
  const certificateCaseReturnAvailable =
    selectedFacilityTab === "Giấy chứng nhận GxP"
    && selectedHistory?.source_type === "case"
    && !caseWorkspaceLoading && !caseWorkspaceError
    && caseWorkspace?.case_summary.id === selectedHistory.id
    && caseWorkspace.case_summary.site_id === summary.site_id
    && !gxpCertificatesLoading && !gxpCertificatesError
    && !gxpCertificateDetailLoading && !gxpCertificateDetailError
    && !!selectedGxpCertificateId
    && gxpCertificates.some(item => item.certificate_id === selectedGxpCertificateId
      && item.case_id === selectedHistory.id && item.site_id === summary.site_id)
    && gxpCertificateDetail?.certificate_id === selectedGxpCertificateId
    && gxpCertificateDetail.case_id === selectedHistory.id
    && gxpCertificateDetail.site_id === summary.site_id;

  // Only offer this path for a UUID listed in both the selected Case and the
  // currently loaded site/GxP/line Certificate list. The destination loader
  // still verifies the selected Certificate detail before presenting it.
  const openableLinkedCertificateIds = selectedHistory?.source_type === "case"
    && !caseWorkspaceLoading && !caseWorkspaceError
    && caseWorkspace?.case_summary.id === selectedHistory.id
    && caseWorkspace.case_summary.site_id === summary.site_id
    && !gxpCertificatesLoading && !gxpCertificatesError
    && Array.isArray(caseWorkspace.linked_gxp_certificates)
    ? caseWorkspace.linked_gxp_certificates.filter(linked =>
      linked.case_id === selectedHistory.id
      && linked.site_id === summary.site_id
      && gxpCertificates.some(listed =>
        listed.certificate_id === linked.certificate_id
        && listed.case_id === selectedHistory.id
        && listed.site_id === summary.site_id
        && listed.certificate_type === linked.certificate_type
      )
    ).map(linked => linked.certificate_id)
    : [];

  function openLinkedCertificate(certificateId: string) {
    // Validate again on the click, not only when deciding whether to display.
    if (!openableLinkedCertificateIds.includes(certificateId)) return;
    onGxpCertificateSelect(certificateId);
    onFacilityTabChange("Giấy chứng nhận GxP");
  }

  // Case-linked action readiness is keyed by the Certificate aggregate UUID.
  // The destination loader revalidates that UUID against the selected facility
  // list/detail; no list position, number, or version is used as identity.
  const caseLinkedCertificateIds = selectedHistory?.source_type === "case"
    && !caseWorkspaceLoading && !caseWorkspaceError
    && caseWorkspace?.case_summary.id === selectedHistory.id
    && caseWorkspace.case_summary.site_id === summary.site_id
    ? (caseWorkspace.linked_gxp_certificates ?? [])
      .filter((linked) => linked.case_id === selectedHistory.id && linked.site_id === summary.site_id)
      .map((linked) => linked.certificate_id)
    : [];

  function navigateCaseCertificate(certificateId: string) {
    if (!caseLinkedCertificateIds.includes(certificateId)) return;
    onNavigateCaseCertificate?.(certificateId);
  }

  const selectedTabContent = (
    <>
    {selectedFacilityTab === "Thông tin chung" ? (
      <FacilitySummary summary={summary} />
    ) : null}

    {selectedFacilityTab === "Các đợt kiểm tra & thay đổi" ? (
      <div className="event-workspace-detail-pane detail-pane">
        <EventWorkspace
          documentNavigationKey={documentNavigationKey}
          accessGeneration={accessGeneration}
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
          onBindApprovalDocument={onBindApprovalDocument}
          onReadApprovalDocuments={onReadApprovalDocuments}
          onApprovalDocumentsConfirmed={onApprovalDocumentsConfirmed}
          onTransitionCase={onTransitionCase}
          onFinalizeInspectionOutcome={onFinalizeInspectionOutcome}
          onInspectionTeamSave={onInspectionTeamSave}
          onLoadInspectionTeamIdentityOptions={onLoadInspectionTeamIdentityOptions}
          onEvaluationScopeSave={onEvaluationScopeSave}
          onInspectionPlanSave={onInspectionPlanSave}
          inspectionPlanReadiness={inspectionPlanReadiness}
          onRetryInspectionPlanReadiness={onRetryInspectionPlanReadiness}
          onIssueCertificate={onIssueCertificate}
          openableCertificateIds={openableLinkedCertificateIds}
          onOpenLinkedCertificate={openLinkedCertificate}
          onNavigateCaseCertificate={navigateCaseCertificate}
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

    {certificateCaseReturnAvailable ? (
      <div className="case-transition-navigation">
        <span>Chứng nhận đang chọn thuộc hồ sơ kiểm tra hiện tại.</span>
        <button type="button" className="secondary" onClick={() => {
          onEventTabChange("Kiểm tra");
          onFacilityTabChange("Các đợt kiểm tra & thay đổi");
        }}>Quay lại Case để kiểm tra hoàn tất</button>
      </div>
    ) : null}

    {selectedFacilityTab === "Giấy chứng nhận GxP" ? (
      <GxpCertificateWorkspace
        ownerSiteId={summary.site_id}
        documentMetadata={gxpDocumentMetadata}
        versionHistory={gxpVersionHistory}
        detail={gxpCertificateDetail}
        detailError={gxpCertificateDetailError}
        detailLoading={gxpCertificateDetailLoading}
        items={gxpCertificates}
        listError={gxpCertificatesError}
        listLoading={gxpCertificatesLoading}
        onSelectCertificate={onGxpCertificateSelect}
        onOpenOwningCase={onOpenGxpCertificateOwningCase}
      onPromoteCurrent={onGxpCertificatePromote}
      onEditLatestVersion={onGxpCertificateEditLatestVersion}
        promotionError={gxpCertificatePromotionError}
        promotionPending={gxpCertificatePromotionPending}
        selectedCertificateId={selectedGxpCertificateId}
      />
    ) : null}

    {selectedFacilityTab === "Giấy chứng nhận đủ điều kiện" ? (
      <BusinessEligibilityWorkspace
        siteId={summary.site_id}
        documentMetadata={eligibilityDocumentMetadata}
        versionHistory={eligibilityVersionHistory}
        sourceEvidence={eligibilitySourceEvidence}
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
            {FACILITY_TAB_LABELS[tab]}
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
