import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { ContextualDocumentSection } from "./ContextualDocumentSection";
export { ContextualDocumentSection } from "./ContextualDocumentSection";

import { EmptyState } from "../../components/EmptyState";
import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import type {
  BusinessEligibilityDetail,
  CapaCycleAssessRequest,
  CapaCycleCreateRequest,
  CapaCycleSubmitRequest,
  CapaCycleUpdateRequest,
  CaseApplicationUpsertRequest,
  CaseAssessmentUpsertRequest,
  CaseInspectionPlanReadinessState,
  CaseWorkspace,
  ChangeRequestWorkspace,
  ContextualDocumentAction,
  DocumentChecklistItem,
  DocumentDetail,
  FacilityHistoryItem,
  GxpCertificateDetail,
  CertificateIssueRequest,
  InspectionOutcomeUpsertRequest,
  InspectionFinalEvaluationRequest,
  InspectionTeamIdentityOption,
  InspectionTeamUpsertRequest,
  InspectionFolderLookup,
  InspectionPlanUpsertRequest,
  EvaluationScopeUpsertRequest,
} from "../../types";
import { BusinessEligibilityDetailFields } from "./BusinessEligibilityDetailFields";
import { CaseApplicationWorkspace } from "./CaseApplicationWorkspace";
import { CaseInspectionWorkspace } from "./CaseInspectionWorkspace";
import { CaseProcessingWorkspace } from "./CaseProcessingWorkspace";
import { CaseCertificateIssueWorkspace } from "./CaseCertificateIssueWorkspace";
import { CaseRemediationWorkspace } from "./CaseRemediationWorkspace";
import { CaseNextActions, type CaseGuidanceTarget } from "./CaseNextActions";
import { ChangeRequestMutationWorkspace, type ChangeRequestMutationHandlers } from "./ChangeRequestMutationWorkspace";
import { EvaluationScopeWorkspace } from "./EvaluationScopeWorkspace";
import { GxpCertificateDetailFields } from "./GxpCertificateDetailFields";
import { useCertificateRows } from "./useCertificateRows";

const CASE_EVENT_TABS = ["Hồ sơ", "Kiểm tra", "Khắc phục", "Xử lý", "Chứng nhận GxP", "Chứng nhận ĐĐK"] as const;
export const CASE_EVENT_LABELS: Record<string, string> = {
  "Hồ sơ": "Hồ sơ đăng ký", "Kiểm tra": "Kiểm tra thực tế", "Khắc phục": "Báo cáo khắc phục",
  "Xử lý": "Xử lý tiếp", "Chứng nhận GxP": "Cấp chứng nhận GPs", "Chứng nhận ĐĐK": "Cấp chứng nhận ĐĐK",
};
const CHANGE_REQUEST_EVENT_TABS = ["Đề nghị", "Chi tiết", "Xử lý", "Tài liệu"] as const;
const GUIDANCE_SELECTORS: Record<CaseGuidanceTarget, string> = {
  application: "[data-case-application]", assessment: "[data-case-assessment]", inspection: "[data-case-inspection]",
  plan: "[data-case-plan]", team: "[data-case-team]", period: "[data-case-period]", capa: "[data-case-capa]",
  final: "[data-case-final-evaluation]", approval: "[data-case-approval-history]", certificate: "[data-case-certificate-issue]", lifecycle: "[data-case-lifecycle]",
};
function guidanceTab(target: CaseGuidanceTarget): string {
  return target === "certificate" ? "Chứng nhận GxP" : target === "capa" ? "Khắc phục" : target === "application" || target === "assessment" ? "Hồ sơ" : "Kiểm tra";
}

/** Read-only CT-to-issuance navigation; backend readiness remains authoritative. */
export function CaseApprovalCertificateHandoff({ workspace, activeTab, onNavigate }: {
  workspace: CaseWorkspace;
  activeTab: string;
  onNavigate: (tab: "Kiểm tra" | "Chứng nhận GxP") => void;
}) {
  const caseId = workspace.case_summary.id;
  const approvals = (workspace.inspection?.approval_submissions ?? []).filter(item => item.case_id === caseId);
  const completedCt = approvals.filter(item => item.stage === "CT" && item.completed_on !== null);
  const readiness = workspace.certificate_issue_readiness;
  const mayIssue = readiness?.action_key === "issue_certificate" && readiness.available === true
    && readiness.certificate_type === workspace.case_summary.gxp_type;
  if (activeTab === "Kiểm tra" && completedCt.length > 0 && mayIssue) {
    return <div className="case-approval-certificate-handoff">
      <p className="workspace-note">{completedCt.length} trình CT đã hoàn tất. Backend cho phép thao tác cấp GCN; cần kiểm tra nội dung trước khi cấp.</p>
      <button className="secondary" type="button" onClick={() => onNavigate("Chứng nhận GxP")}>Đến cấp giấy chứng nhận GxP</button>
    </div>;
  }
  if (activeTab === "Chứng nhận GxP" && approvals.some(item => item.stage === "CT")) {
    return <div className="case-approval-certificate-handoff">
      <button className="secondary" type="button" onClick={() => onNavigate("Kiểm tra")}>Xem lại lịch sử trình PCT / CT</button>
    </div>;
  }
  return null;
}


const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  available: "Đã có tài liệu",
  missing: "Chưa có tài liệu",
};

const DOCUMENT_PARENT_SCOPE_LABELS: Record<string, string> = {
  case: "Hồ sơ",
  capa_cycle: "CAPA",
  change_request: "Thay đổi",
};

function WorkspaceSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="workspace-section">
      <h4>{title}</h4>
      {children}
    </section>
  );
}

function DocumentChecklistSection({
  items,
  emptyDescription,
}: {
  items: DocumentChecklistItem[];
  emptyDescription: string;
}) {
  if (items.length === 0) {
    return <EmptyState title="Chưa có checklist tài liệu" description={emptyDescription} />;
  }

  return (
    <div className="table-scroll table-scroll-history">
      <table className="dense-table event-document-table" aria-label="Checklist tài liệu thay đổi">
        <thead>
          <tr>
            <th>Loại tài liệu</th>
            <th>Phạm vi</th>
            <th>Trạng thái</th>
            <th>Tệp hiện có</th>
            <th>Ngày</th>
            <th>Định dạng</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.checklist_key}>
              <td title={item.family_code ?? ""}>
                <div className="cell-stack">
                  <strong>{item.label}</strong>
                  {item.title ? <span>{item.title}</span> : null}
                </div>
              </td>
              <td>{DOCUMENT_PARENT_SCOPE_LABELS[item.parent_scope] ?? item.parent_scope}</td>
              <td>{DOCUMENT_STATUS_LABELS[item.status] ?? item.status}</td>
              <td title={item.original_filename ?? ""}>{item.original_filename ?? "Chưa có"}</td>
              <td>{formatCompactDate(item.issued_on)}</td>
              <td>{item.available_variant_types.length > 0 ? item.available_variant_types.join(", ") : "Chưa có"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LinkedGxpCertificates({
  items,
  openableCertificateIds = [],
  onOpenCertificate,
}: {
  items: GxpCertificateDetail[];
  openableCertificateIds?: string[];
  onOpenCertificate?: (certificateId: string) => void;
}) {
  const [selectedCertificateId, setSelectedCertificateId] = useState<string | null>(items[0]?.certificate_id ?? null);

  const rowProps = useCertificateRows(items.map(item => item.certificate_id), selectedCertificateId, setSelectedCertificateId, false);

  useEffect(() => {
    setSelectedCertificateId((current) =>
      current && items.some((item) => item.certificate_id === current) ? current : items[0]?.certificate_id ?? null,
    );
  }, [items]);

  const selectedCertificate = items.find((item) => item.certificate_id === selectedCertificateId) ?? items[0] ?? null;

  if (items.length === 0) {
    return (
      <EmptyState
        title="Chưa có chứng nhận GxP liên kết"
        description="Đợt kiểm tra đang chọn chưa có certificate record canonical liên kết trực tiếp theo case."
      />
    );
  }

  return (
    <div className="certificate-workspace-split event-linked-certificate-workspace">
      <section className="panel panel-tight certificate-list-panel">
        <div className="panel-header">
          <h3>Chứng nhận GxP liên kết</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table aria-label="Chứng nhận GxP liên kết" className="dense-table certificate-history-table">
            <thead>
              <tr>
                <th className="col-gxp">GxP</th>
                <th className="col-line">Dây chuyền</th>
                <th className="col-cert-number">Số GCN</th>
                <th className="col-date">Ngày cấp</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  aria-selected={selectedCertificateId === item.certificate_id}
                  className={selectedCertificateId === item.certificate_id ? "selected" : ""}
                  key={item.certificate_id}
                  {...rowProps(item.certificate_id)}
                >
                  <td>{item.certificate_type}</td>
                  <td>{item.line_code ?? "Cơ sở"}</td>
                  <td title={item.certificate_number ?? ""}>
                    <div className="cell-stack">
                      <strong>{item.certificate_number ?? "Chưa có"}</strong>
                      {item.latest_flag ? <span>Hiện hành</span> : null}
                    </div>
                  </td>
                  <td>{formatCompactDate(item.issue_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel panel-tight certificate-detail-panel">
        {selectedCertificate ? <>
          <GxpCertificateDetailFields detail={selectedCertificate} presentation="case" />
          {onOpenCertificate && openableCertificateIds.includes(selectedCertificate.certificate_id) ? (
            <div className="panel-actions">
              <button type="button" className="secondary" onClick={() => onOpenCertificate(selectedCertificate.certificate_id)}>
                Xem chứng nhận trong sổ GxP
              </button>
            </div>
          ) : null}
        </> : null}
      </section>
    </div>
  );
}

function LinkedBusinessEligibilityCertificates({
  items,
}: {
  items: BusinessEligibilityDetail[];
}) {
  const [selectedCertificateId, setSelectedCertificateId] = useState<string | null>(
    items[0]?.business_eligibility_certificate_id ?? null,
  );

  const rowProps = useCertificateRows(items.map(item => item.business_eligibility_certificate_id), selectedCertificateId, setSelectedCertificateId, false);

  useEffect(() => {
    setSelectedCertificateId((current) =>
      current && items.some((item) => item.business_eligibility_certificate_id === current)
        ? current
        : items[0]?.business_eligibility_certificate_id ?? null,
    );
  }, [items]);

  const selectedCertificate =
    items.find((item) => item.business_eligibility_certificate_id === selectedCertificateId) ?? items[0] ?? null;

  if (items.length === 0) {
    return (
      <EmptyState
        title="Chưa có chứng nhận ĐĐK liên kết"
        description="Không tìm thấy liên kết canonical từ certificate của đợt kiểm tra này sang giấy chứng nhận đủ điều kiện."
      />
    );
  }

  return (
    <div className="certificate-workspace-split event-linked-certificate-workspace case-business-eligibility-workspace">
      <section className="panel panel-tight certificate-list-panel">
        <div className="panel-header">
          <h3>Giấy ĐĐK đã cấp căn cứ GCN GPs này</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table aria-label="Giấy ĐĐK đã cấp căn cứ GCN GPs này" className="dense-table eligibility-history-table">
            <thead>
              <tr>
                <th className="col-cert-number">Số GCN</th>
                <th className="col-date">Ngày cấp</th>
                <th className="col-sequence">Lần</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  aria-selected={selectedCertificateId === item.business_eligibility_certificate_id}
                  className={selectedCertificateId === item.business_eligibility_certificate_id ? "selected" : ""}
                  key={item.business_eligibility_certificate_id}
                  {...rowProps(item.business_eligibility_certificate_id)}
                >
                  <td title={item.certificate_number ?? ""}>
                    <div className="cell-stack">
                      <strong>{item.certificate_number ?? "Chưa có"}</strong>
                      {item.latest_flag ? <span>Hiện hành</span> : null}
                    </div>
                  </td>
                  <td>{formatCompactDate(item.issued_on)}</td>
                  <td>{item.issuance_sequence_text ? `Lần ${item.issuance_sequence_text}` : "Chưa có"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-label="Chi tiết giấy ĐĐK liên kết" className="panel panel-tight certificate-detail-panel">
        {selectedCertificate ? <BusinessEligibilityDetailFields detail={selectedCertificate} /> : null}
      </section>
    </div>
  );
}

function renderCaseStepContent(
  accessGeneration: number | null,
  activeTab: string,
  caseWorkspace: CaseWorkspace,
  documentNavigationKey: string | null | undefined,
  onCaseApplicationSave: (payload: CaseApplicationUpsertRequest) => Promise<void>,
  onCaseAssessmentSave: (payload: CaseAssessmentUpsertRequest) => Promise<void>,
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>,
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>,
  onInspectionPeriodSegmentsSave: (payload: import("../../types").InspectionPeriodSegmentsUpsertRequest) => Promise<void>,
  onCreateApprovalSubmission: (stage: "PCT" | "CT", payload: import("../../types").InspectionApprovalSubmissionCreateRequest) => Promise<import("../../types").InspectionApprovalSubmissionMutationResponse>,
  onCompleteApprovalSubmission: (submissionId: string, payload: import("../../types").InspectionApprovalSubmissionCompleteRequest) => Promise<import("../../types").InspectionApprovalSubmissionMutationResponse>,
  onTransitionCase: (payload: import("../../types").CaseTransitionRequest) => Promise<void>,
  onInspectionTeamSave: (payload: InspectionTeamUpsertRequest) => Promise<void>,
  onLoadInspectionTeamIdentityOptions: () => Promise<InspectionTeamIdentityOption[]>,
  selectedRemediationCycleId: string | null,
  onSelectedRemediationCycleChange: (cycleId: string | null) => void,
  onCreateCapaCycle: (payload: CapaCycleCreateRequest) => Promise<void>,
  onUpdateCapaCycle: (cycleId: string, payload: CapaCycleUpdateRequest) => Promise<void>,
  onSubmitCapaCycle: (cycleId: string, payload: CapaCycleSubmitRequest) => Promise<void>,
  onAssessCapaCycle: (cycleId: string, payload: CapaCycleAssessRequest) => Promise<void>,
  onResolveInspectionFolder: () => Promise<InspectionFolderLookup>,
  onOpenDocument: (caseId: string, item: ContextualDocumentAction, isCurrentDocument?: () => boolean) => Promise<void>,
  onLoadDocumentDetail: (documentId: string) => Promise<DocumentDetail>,
  onCreateDocument: (
    caseId: string,
    item: ContextualDocumentAction,
    action: ContextualDocumentAction["actions"][number],
  ) => Promise<void>,
  inspectionPlanReadiness: CaseInspectionPlanReadinessState | null,
  onRetryInspectionPlanReadiness: () => void,
  onIssueCertificate: (payload: CertificateIssueRequest) => Promise<void>,
  openableCertificateIds: string[],
  onOpenLinkedCertificate?: (certificateId: string) => void,
  onFinalizeInspectionOutcome?: (payload: InspectionFinalEvaluationRequest) => Promise<void>,
) {
  const documentItems = caseWorkspace.contextual_document_actions.filter((item) => {
    if (item.workflow_step !== activeTab) {
      return false;
    }
    if (item.parent_scope === "capa_cycle") {
      return item.parent_id === selectedRemediationCycleId;
    }
    return item.parent_scope === "case";
  });

  if (activeTab === "Hồ sơ") {
    return (
      <div className="registration-workspace">
        <div className="registration-form-pane">
        <CaseApplicationWorkspace
          accessGeneration={accessGeneration}
          assessment={<CaseProcessingWorkspace caseWorkspace={caseWorkspace} onSave={onCaseAssessmentSave} view="assessment" />}
          caseWorkspace={caseWorkspace}
          onResolveInspectionFolder={onResolveInspectionFolder}
          onSave={onCaseApplicationSave}
        />
        </div>
        <div className="registration-document-column">
        <ContextualDocumentSection
          initialSelectionKey={documentNavigationKey}
          contextKey={JSON.stringify([caseWorkspace.case_summary.site_id, caseWorkspace.case_summary.gxp_type, caseWorkspace.case_summary.production_line_id, caseWorkspace.case_summary.id, activeTab, selectedRemediationCycleId])}
          items={documentItems}
          onCreateDocument={(item, action) =>
            onCreateDocument(caseWorkspace.case_summary.id, item, action)
          }
          onLoadDocumentDetail={onLoadDocumentDetail}
          onOpenDocument={(item, isCurrentDocument) => onOpenDocument(caseWorkspace.case_summary.id, item, isCurrentDocument)}
        />
        </div>
      </div>
    );
  }

  if (activeTab === "Kiểm tra") {
    return (
      <div className="inspection-workflow-layout">
        <CaseInspectionWorkspace
          caseWorkspace={caseWorkspace}
          onInspectionOutcomeSave={onInspectionOutcomeSave}
          onInspectionPeriodSegmentsSave={onInspectionPeriodSegmentsSave}
          onCreateApprovalSubmission={onCreateApprovalSubmission}
          onCompleteApprovalSubmission={onCompleteApprovalSubmission}
          onTransitionCase={onTransitionCase}
          onInspectionPlanSave={onInspectionPlanSave}
          onInspectionTeamSave={onInspectionTeamSave}
          onLoadInspectionTeamIdentityOptions={onLoadInspectionTeamIdentityOptions}
          onFinalizeInspectionOutcome={onFinalizeInspectionOutcome}
        />
        <div className="inspection-document-column">
          <ContextualDocumentSection
            initialSelectionKey={documentNavigationKey}
            contextKey={JSON.stringify([caseWorkspace.case_summary.site_id, caseWorkspace.case_summary.gxp_type, caseWorkspace.case_summary.production_line_id, caseWorkspace.case_summary.id, activeTab, selectedRemediationCycleId])}
            createReadiness={inspectionPlanReadiness}
            items={documentItems}
            onCreateDocument={(item, action) =>
              onCreateDocument(caseWorkspace.case_summary.id, item, action)
            }
            onLoadDocumentDetail={onLoadDocumentDetail}
            onOpenDocument={(item, isCurrentDocument) => onOpenDocument(caseWorkspace.case_summary.id, item, isCurrentDocument)}
            onRetryCreateReadiness={onRetryInspectionPlanReadiness}
          />
        </div>
      </div>
    );
  }

  if (activeTab === "Khắc phục") {
    return (
      <div className="remediation-workflow-layout">
        <CaseRemediationWorkspace
          caseWorkspace={caseWorkspace}
          onAssessCycle={onAssessCapaCycle}
          onCreateCycle={onCreateCapaCycle}
          onSelectedCycleChange={onSelectedRemediationCycleChange}
          onSubmitCycle={onSubmitCapaCycle}
          onUpdateCycle={onUpdateCapaCycle}
          selectedCycleId={selectedRemediationCycleId}
        />
        <div className="remediation-document-column">
          <ContextualDocumentSection
            initialSelectionKey={documentNavigationKey}
            contextKey={JSON.stringify([caseWorkspace.case_summary.site_id, caseWorkspace.case_summary.gxp_type, caseWorkspace.case_summary.production_line_id, caseWorkspace.case_summary.id, activeTab, selectedRemediationCycleId])}
            items={documentItems}
            onCreateDocument={(item, action) =>
              onCreateDocument(caseWorkspace.case_summary.id, item, action)
            }
            onLoadDocumentDetail={onLoadDocumentDetail}
            onOpenDocument={(item, isCurrentDocument) => onOpenDocument(caseWorkspace.case_summary.id, item, isCurrentDocument)}
          />
        </div>
      </div>
    );
  }

  if (activeTab === "Xử lý") {
    return (
      <div className="processing-workflow-layout">
        <CaseProcessingWorkspace caseWorkspace={caseWorkspace} onSave={onCaseAssessmentSave} view="timeline" />
        <div className="processing-document-column">
          <ContextualDocumentSection
            initialSelectionKey={documentNavigationKey}
            contextKey={JSON.stringify([caseWorkspace.case_summary.site_id, caseWorkspace.case_summary.gxp_type, caseWorkspace.case_summary.production_line_id, caseWorkspace.case_summary.id, activeTab, selectedRemediationCycleId])}
            items={documentItems}
            onCreateDocument={(item, action) =>
              onCreateDocument(caseWorkspace.case_summary.id, item, action)
            }
            onLoadDocumentDetail={onLoadDocumentDetail}
            onOpenDocument={(item, isCurrentDocument) => onOpenDocument(caseWorkspace.case_summary.id, item, isCurrentDocument)}
          />
        </div>
      </div>
    );
  }

  if (activeTab === "Chứng nhận GxP") {
    return (
      <div className="case-gxp-workflow-layout">
        <div className="case-gxp-certificate-pane">
          <LinkedGxpCertificates
            items={caseWorkspace.linked_gxp_certificates}
            openableCertificateIds={openableCertificateIds}
            onOpenCertificate={onOpenLinkedCertificate}
          />
          <CaseCertificateIssueWorkspace
            caseId={caseWorkspace.case_summary.id}
            onIssue={onIssueCertificate}
            readiness={caseWorkspace.certificate_issue_readiness}
          />
        </div>
        <div className="case-gxp-document-column">
          <ContextualDocumentSection
            initialSelectionKey={documentNavigationKey}
            contextKey={JSON.stringify([caseWorkspace.case_summary.site_id, caseWorkspace.case_summary.gxp_type, caseWorkspace.case_summary.production_line_id, caseWorkspace.case_summary.id, activeTab, selectedRemediationCycleId])}
            items={documentItems}
            onCreateDocument={(item, action) =>
              onCreateDocument(caseWorkspace.case_summary.id, item, action)
            }
            onLoadDocumentDetail={onLoadDocumentDetail}
            onOpenDocument={(item, isCurrentDocument) => onOpenDocument(caseWorkspace.case_summary.id, item, isCurrentDocument)}
          />
        </div>
      </div>
    );
  }

  return <LinkedBusinessEligibilityCertificates items={caseWorkspace.linked_business_eligibility_certificates} />;
}

function renderChangeRequestStepContent(
  activeTab: string,
  changeRequestWorkspace: ChangeRequestWorkspace,
  handlers: ChangeRequestMutationHandlers,
) {
  if (activeTab !== "Tài liệu") {
    return (
      <ChangeRequestMutationWorkspace
        activeTab={activeTab}
        handlers={handlers}
        workspace={changeRequestWorkspace}
      />
    );
  }

  return (
    <WorkspaceSection title="Checklist tài liệu thay đổi">
      <DocumentChecklistSection
        emptyDescription="Canonical document owner hiện chưa có document row hoặc family checklist nào được gắn cho yêu cầu thay đổi này."
        items={changeRequestWorkspace.documents.items}
      />
    </WorkspaceSection>
  );
}

export function EventWorkspace({
  documentNavigationKey,
  accessGeneration = 0,
  selectedHistory,
  caseWorkspace,
  caseWorkspaceLoading,
  caseWorkspaceError,
  changeRequestWorkspace,
  changeRequestWorkspaceLoading,
  changeRequestWorkspaceError,
  changeRequestMutations,
  activeTab,
  onTabChange,
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
  onLoadDocumentDetail,
  onCreateDocument,
  inspectionPlanReadiness,
  onRetryInspectionPlanReadiness,
  onIssueCertificate,
  openableCertificateIds = [],
  onOpenLinkedCertificate,
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
  selectedHistory: FacilityHistoryItem | null;
  caseWorkspace: CaseWorkspace | null;
  caseWorkspaceLoading: boolean;
  caseWorkspaceError: string | null;
  changeRequestWorkspace: ChangeRequestWorkspace | null;
  changeRequestWorkspaceLoading: boolean;
  changeRequestWorkspaceError: string | null;
  changeRequestMutations: ChangeRequestMutationHandlers;
  activeTab: string;
  onTabChange: (tab: string) => void;
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
  onLoadDocumentDetail: (documentId: string) => Promise<DocumentDetail>;
  onCreateDocument: (
    caseId: string,
    item: ContextualDocumentAction,
    action: ContextualDocumentAction["actions"][number],
  ) => Promise<void>;
  inspectionPlanReadiness: CaseInspectionPlanReadinessState | null;
  onRetryInspectionPlanReadiness: () => void;
  onIssueCertificate: (payload: CertificateIssueRequest) => Promise<void>;
  openableCertificateIds?: string[];
  onOpenLinkedCertificate?: (certificateId: string) => void;
  selectedRemediationCycleId: string | null;
  onSelectedRemediationCycleChange: (cycleId: string | null) => void;
  onCreateCapaCycle: (payload: CapaCycleCreateRequest) => Promise<void>;
  onUpdateCapaCycle: (cycleId: string, payload: CapaCycleUpdateRequest) => Promise<void>;
  onSubmitCapaCycle: (cycleId: string, payload: CapaCycleSubmitRequest) => Promise<void>;
  onAssessCapaCycle: (cycleId: string, payload: CapaCycleAssessRequest) => Promise<void>;
  onResolveInspectionFolder: () => Promise<InspectionFolderLookup>;
  onFinalizeInspectionOutcome?: (payload: InspectionFinalEvaluationRequest) => Promise<void>;
}) {
  const rootRef = useRef<HTMLElement>(null);
  const pendingLifecycleFocus = useRef<{ caseId: string; target: CaseGuidanceTarget } | null>(null);
  useLayoutEffect(() => {
    const request = pendingLifecycleFocus.current;
    if (!request) return;
    const { caseId, target: targetName } = request;
    if (selectedHistory?.id !== caseId || selectedHistory.source_type !== "case") {
      pendingLifecycleFocus.current = null;
      return;
    }
    const targetTab = guidanceTab(targetName);
    if (activeTab === targetTab && !caseWorkspaceLoading && !caseWorkspaceError && caseWorkspace?.case_summary.id === caseId) {
      const target = rootRef.current?.querySelector<HTMLElement>(GUIDANCE_SELECTORS[targetName]);
      if (target) { pendingLifecycleFocus.current = null; target.focus(); }
    }
  }, [activeTab, caseWorkspace, caseWorkspaceError, caseWorkspaceLoading, selectedHistory]);
  if (!selectedHistory) {
    return (
      <EmptyState
        title="Chưa chọn sự kiện"
        description="Chọn một dòng lịch sử để xem vùng detail nghiệp vụ bên dưới."
      />
    );
  }

  // The old payload can survive until its owner's effect runs; fail closed in this render.
  if (caseWorkspace?.case_summary.id !== selectedHistory.id) caseWorkspace = null;
  if (changeRequestWorkspace?.id !== selectedHistory.id) changeRequestWorkspace = null;

  const tabs = selectedHistory.source_type === "change_request" ? CHANGE_REQUEST_EVENT_TABS : CASE_EVENT_TABS;
  const effectiveActiveTab = tabs.some((tab) => tab === activeTab) ? activeTab : tabs[0];

  return (
    <section className="event-workspace" ref={rootRef}>
      <nav aria-label="Quy trình xử lý sự kiện" className="workflow-stepper">
        <ol className="workflow-step-list">
          {tabs.map((tab, index) => (
            <li key={tab}>
              <button
                aria-label={selectedHistory.source_type === "case" ? CASE_EVENT_LABELS[tab] ?? tab : tab}
                aria-current={effectiveActiveTab === tab ? "step" : undefined}
                className={effectiveActiveTab === tab ? "workflow-step active" : "workflow-step"}
                onClick={() => { pendingLifecycleFocus.current = null; onTabChange(tab); }}
                type="button"
              >
                <span className="workflow-step-index">{index + 1}</span>
                <span>{selectedHistory.source_type === "case" ? CASE_EVENT_LABELS[tab] ?? tab : tab}</span>
              </button>
            </li>
          ))}
        </ol>
      </nav>
      <div className={selectedHistory.source_type === "case" && caseWorkspace ? "workspace-body event-workspace-body has-scope-context" : "workspace-body event-workspace-body"}>
        <div className="event-step-content">
        {selectedHistory.source_type === "case" && caseWorkspace && !caseWorkspaceLoading && !caseWorkspaceError ? <CaseNextActions workspace={caseWorkspace} onNavigate={(target, cycleId) => {
          if (cycleId) onSelectedRemediationCycleChange(cycleId);
          pendingLifecycleFocus.current = { caseId: selectedHistory.id, target };
          const tab = guidanceTab(target);
          if (effectiveActiveTab === tab) {
            pendingLifecycleFocus.current = null;
            rootRef.current?.querySelector<HTMLElement>(GUIDANCE_SELECTORS[target])?.focus();
          } else onTabChange(tab);
        }} /> : null}
        {selectedHistory.source_type === "case" && caseWorkspace && !caseWorkspaceLoading && !caseWorkspaceError && effectiveActiveTab !== "Kiểm tra" ? (
          <div className="case-transition-navigation">
            <span>Trạng thái hồ sơ: {formatStatusLabel(caseWorkspace.case_summary.state)}</span>
            {(caseWorkspace.transition_actions ?? []).length > 0 ? <button type="button" className="secondary" onClick={() => { pendingLifecycleFocus.current = { caseId: selectedHistory.id, target: "lifecycle" }; onTabChange("Kiểm tra"); }}>Xem chuyển trạng thái hồ sơ</button> : null}
            {effectiveActiveTab === "Khắc phục" && caseWorkspace.inspection.final_evaluation_readiness?.available ? <button type="button" className="secondary" onClick={() => { pendingLifecycleFocus.current = { caseId: selectedHistory.id, target: "final" }; onTabChange("Kiểm tra"); }}>Đến đánh giá cuối cùng</button> : null}
          </div>
        ) : null}
        {selectedHistory.source_type === "case" && caseWorkspace && !caseWorkspaceLoading && !caseWorkspaceError ? (
          <CaseApprovalCertificateHandoff workspace={caseWorkspace} activeTab={effectiveActiveTab} onNavigate={(tab) => {
            pendingLifecycleFocus.current = { caseId: selectedHistory.id, target: tab === "Chứng nhận GxP" ? "certificate" : "approval" };
            onTabChange(tab);
          }} />
        ) : null}
        {selectedHistory.source_type === "change_request" ? (
          changeRequestWorkspaceLoading ? (
            <EmptyState title="Đang tải workspace thay đổi" description="Đang lấy dữ liệu đọc theo yêu cầu thay đổi đã chọn từ authenticated API." />
          ) : changeRequestWorkspaceError ? (
            <EmptyState
              title="Không tải được workspace thay đổi"
              description={changeRequestWorkspaceError}
            />
          ) : changeRequestWorkspace ? (
            renderChangeRequestStepContent(effectiveActiveTab, changeRequestWorkspace, changeRequestMutations)
          ) : (
            <EmptyState title="Chưa có workspace thay đổi" description="Backend chưa trả dữ liệu workspace cho lựa chọn thay đổi hiện tại." />
          )
        ) : caseWorkspaceLoading ? (
          <EmptyState title="Đang tải workspace hồ sơ" description="Đang lấy dữ liệu đọc theo case đã chọn từ authenticated API." />
        ) : caseWorkspaceError ? (
          <EmptyState
            title="Không tải được workspace hồ sơ"
            description={caseWorkspaceError}
          />
        ) : caseWorkspace ? (
          renderCaseStepContent(
            accessGeneration,
            effectiveActiveTab,
            caseWorkspace,
            documentNavigationKey,
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
            selectedRemediationCycleId,
            onSelectedRemediationCycleChange,
            onCreateCapaCycle,
            onUpdateCapaCycle,
            onSubmitCapaCycle,
            onAssessCapaCycle,
            onResolveInspectionFolder,
            onOpenDocument,
            onLoadDocumentDetail,
            onCreateDocument,
            inspectionPlanReadiness,
            onRetryInspectionPlanReadiness,
            onIssueCertificate,
            openableCertificateIds,
            onOpenLinkedCertificate,
            onFinalizeInspectionOutcome,
          )
        ) : (
          <EmptyState title="Chưa có workspace hồ sơ" description="Backend chưa trả dữ liệu workspace cho lựa chọn case hiện tại." />
        )}
        </div>
        {selectedHistory.source_type === "case" && caseWorkspace ? (
          <div className="event-scope-context">
            <EvaluationScopeWorkspace caseWorkspace={caseWorkspace} onSave={onEvaluationScopeSave} />
          </div>
        ) : null}
      </div>
    </section>
  );
}
