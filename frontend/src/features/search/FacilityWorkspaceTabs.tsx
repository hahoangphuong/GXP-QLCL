import type {
  BusinessEligibilityDetail,
  CapaCycleAssessRequest,
  CapaCycleCreateRequest,
  CapaCycleSubmitRequest,
  CapaCycleUpdateRequest,
  BusinessEligibilityListItem,
  CaseApplicationUpsertRequest,
  CaseAssessmentUpsertRequest,
  CaseWorkspace,
  ChangeRequestWorkspace,
  DocumentDetail,
  FacilityHistoryItem,
  FacilityWorkspaceSummary,
  GxpCertificateDetail,
  GxpCertificateListItem,
  InspectionOutcomeUpsertRequest,
  InspectionPlanUpsertRequest,
} from "../../types";
import { EventWorkspace } from "./EventWorkspace";
import { BusinessEligibilityWorkspace } from "./BusinessEligibilityWorkspace";
import { FacilitySummary } from "./FacilitySummary";
import { GxpCertificateWorkspace } from "./GxpCertificateWorkspace";
import { HistoryTable } from "./HistoryTable";

const FACILITY_TABS = [
  "Thông tin chung",
  "Các đợt kiểm tra & thay đổi",
  "Giấy chứng nhận GxP",
  "Giấy chứng nhận đủ điều kiện",
] as const;

export function FacilityWorkspaceTabs({
  summary,
  history,
  selectedFacilityTab,
  onFacilityTabChange,
  selectedHistory,
  selectedHistoryId,
  onHistorySelect,
  caseWorkspace,
  caseWorkspaceLoading,
  caseWorkspaceError,
  changeRequestWorkspace,
  changeRequestWorkspaceLoading,
  changeRequestWorkspaceError,
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
  eligibilityCertificates,
  eligibilityCertificatesLoading,
  eligibilityCertificatesError,
  selectedEligibilityCertificateId,
  onEligibilityCertificateSelect,
  eligibilityCertificateDetail,
  eligibilityCertificateDetailLoading,
  eligibilityCertificateDetailError,
  onCaseApplicationSave,
  onCaseAssessmentSave,
  onInspectionPlanSave,
  onInspectionOutcomeSave,
  onLoadDocumentDetail,
  selectedRemediationCycleId,
  onSelectedRemediationCycleChange,
  onCreateCapaCycle,
  onUpdateCapaCycle,
  onSubmitCapaCycle,
  onAssessCapaCycle,
}: {
  summary: FacilityWorkspaceSummary;
  history: FacilityHistoryItem[];
  selectedFacilityTab: string;
  onFacilityTabChange: (tab: string) => void;
  selectedHistory: FacilityHistoryItem | null;
  selectedHistoryId: string | null;
  onHistorySelect: (historyId: string) => void;
  caseWorkspace: CaseWorkspace | null;
  caseWorkspaceLoading: boolean;
  caseWorkspaceError: string | null;
  changeRequestWorkspace: ChangeRequestWorkspace | null;
  changeRequestWorkspaceLoading: boolean;
  changeRequestWorkspaceError: string | null;
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
  eligibilityCertificates: BusinessEligibilityListItem[];
  eligibilityCertificatesLoading: boolean;
  eligibilityCertificatesError: string | null;
  selectedEligibilityCertificateId: string | null;
  onEligibilityCertificateSelect: (certificateId: string) => void;
  eligibilityCertificateDetail: BusinessEligibilityDetail | null;
  eligibilityCertificateDetailLoading: boolean;
  eligibilityCertificateDetailError: string | null;
  onCaseApplicationSave: (payload: CaseApplicationUpsertRequest) => Promise<void>;
  onCaseAssessmentSave: (payload: CaseAssessmentUpsertRequest) => Promise<void>;
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
  onLoadDocumentDetail: (documentId: string) => Promise<DocumentDetail>;
  selectedRemediationCycleId: string | null;
  onSelectedRemediationCycleChange: (cycleId: string | null) => void;
  onCreateCapaCycle: (payload: CapaCycleCreateRequest) => Promise<void>;
  onUpdateCapaCycle: (cycleId: string, payload: CapaCycleUpdateRequest) => Promise<void>;
  onSubmitCapaCycle: (cycleId: string, payload: CapaCycleSubmitRequest) => Promise<void>;
  onAssessCapaCycle: (cycleId: string, payload: CapaCycleAssessRequest) => Promise<void>;
}) {
  return (
    <section className="panel panel-tight facility-workspace-panel">
      <div className="workspace-tabs facility-tabs tab-strip tab-strip-primary" role="tablist" aria-label="Tab nghiệp vụ cơ sở">
        {FACILITY_TABS.map((tab) => (
          <button
            aria-selected={selectedFacilityTab === tab}
            className={selectedFacilityTab === tab ? "workspace-tab active" : "workspace-tab"}
            key={tab}
            onClick={() => onFacilityTabChange(tab)}
            role="tab"
            type="button"
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="facility-tab-body">
        {selectedFacilityTab === "Thông tin chung" ? (
          <FacilitySummary summary={summary} />
        ) : null}

        {selectedFacilityTab === "Các đợt kiểm tra & thay đổi" ? (
          <div className="event-workspace-split master-detail-split master-detail-split-history">
            <div className="event-workspace-history-pane master-list-pane">
              <HistoryTable rows={history} selectedHistoryId={selectedHistoryId} onSelect={onHistorySelect} />
            </div>
            <div className="event-workspace-detail-pane detail-pane">
              <EventWorkspace
                activeTab={activeEventTab}
                caseWorkspace={caseWorkspace}
                caseWorkspaceError={caseWorkspaceError}
                caseWorkspaceLoading={caseWorkspaceLoading}
                changeRequestWorkspace={changeRequestWorkspace}
                changeRequestWorkspaceError={changeRequestWorkspaceError}
                changeRequestWorkspaceLoading={changeRequestWorkspaceLoading}
                onCaseApplicationSave={onCaseApplicationSave}
                onCaseAssessmentSave={onCaseAssessmentSave}
                onAssessCapaCycle={onAssessCapaCycle}
                onCreateCapaCycle={onCreateCapaCycle}
                onInspectionOutcomeSave={onInspectionOutcomeSave}
                onInspectionPlanSave={onInspectionPlanSave}
                onLoadDocumentDetail={onLoadDocumentDetail}
                onSelectedRemediationCycleChange={onSelectedRemediationCycleChange}
                onSubmitCapaCycle={onSubmitCapaCycle}
                onTabChange={onEventTabChange}
                onUpdateCapaCycle={onUpdateCapaCycle}
                selectedRemediationCycleId={selectedRemediationCycleId}
                selectedHistory={selectedHistory}
              />
            </div>
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
            onSelectCertificate={onEligibilityCertificateSelect}
            selectedCertificateId={selectedEligibilityCertificateId}
          />
        ) : null}
      </div>
    </section>
  );
}
