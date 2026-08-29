import { useEffect, useState, type ReactNode } from "react";

import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate, formatHistoryEventType, formatStatusLabel } from "../../lib/presentation";
import type {
  BusinessEligibilityDetail,
  CaseWorkspace,
  CaseWorkspaceRemediationCycle,
  FacilityHistoryItem,
  GxpCertificateDetail,
} from "../../types";
import { BusinessEligibilityDetailFields } from "./BusinessEligibilityDetailFields";
import { DetailValue } from "./DetailValue";
import { GxpCertificateDetailFields } from "./GxpCertificateDetailFields";

const EVENT_TABS = ["Hồ sơ", "Kiểm tra", "Khắc phục", "Xử lý", "Chứng nhận GxP", "Chứng nhận ĐĐK"] as const;

const PROCESSING_EVENT_LABELS: Record<string, string> = {
  application_submitted: "Tiếp nhận hồ sơ",
  assessment_completed: "Thẩm định hoàn tất",
  plan_created: "Lập kế hoạch",
  decision_issued: "Ban hành quyết định",
  inspection_executed: "Thực hiện kiểm tra",
  outcome_recorded: "Ghi nhận kết quả",
  certificate_issued: "Cấp chứng nhận",
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

function EmptySection({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <WorkspaceSection title={title}>
      <EmptyState title="Chưa có dữ liệu" description={description} />
    </WorkspaceSection>
  );
}

function LinkedGxpCertificates({
  items,
}: {
  items: GxpCertificateDetail[];
}) {
  const [selectedCertificateId, setSelectedCertificateId] = useState<string | null>(items[0]?.certificate_id ?? null);

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
          <table className="dense-table certificate-history-table">
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
                  onClick={() => setSelectedCertificateId(item.certificate_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedCertificateId(item.certificate_id);
                    }
                  }}
                  tabIndex={0}
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
        {selectedCertificate ? <GxpCertificateDetailFields detail={selectedCertificate} /> : null}
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
    <div className="certificate-workspace-split event-linked-certificate-workspace">
      <section className="panel panel-tight certificate-list-panel">
        <div className="panel-header">
          <h3>Chứng nhận ĐĐK liên kết</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table className="dense-table eligibility-history-table">
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
                  onClick={() => setSelectedCertificateId(item.business_eligibility_certificate_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedCertificateId(item.business_eligibility_certificate_id);
                    }
                  }}
                  tabIndex={0}
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

      <section className="panel panel-tight certificate-detail-panel">
        {selectedCertificate ? <BusinessEligibilityDetailFields detail={selectedCertificate} /> : null}
      </section>
    </div>
  );
}

function RemediationWorkspace({
  cycles,
}: {
  cycles: CaseWorkspaceRemediationCycle[];
}) {
  const [selectedCycleId, setSelectedCycleId] = useState<string | null>(cycles.at(-1)?.capa_cycle_id ?? null);

  useEffect(() => {
    setSelectedCycleId((current) =>
      current && cycles.some((item) => item.capa_cycle_id === current) ? current : cycles.at(-1)?.capa_cycle_id ?? null,
    );
  }, [cycles]);

  const selectedCycle = cycles.find((item) => item.capa_cycle_id === selectedCycleId) ?? cycles.at(-1) ?? null;

  if (cycles.length === 0) {
    return (
      <EmptyState
        title="Chưa có vòng khắc phục"
        description="Legacy snapshot hiện chưa cung cấp round CAPA cho lựa chọn này hoặc hồ sơ chưa phát sinh khắc phục."
      />
    );
  }

  return (
    <div className="event-step-stack">
      <section className="panel panel-tight">
        <div className="panel-header">
          <h3>Lịch sử khắc phục</h3>
          <span className="panel-meta">{cycles.length} vòng</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table className="dense-table capa-cycle-table">
            <thead>
              <tr>
                <th>Lần</th>
                <th>Ngày nhận</th>
                <th>Ngày xử lý</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {cycles.map((cycle) => (
                <tr
                  aria-selected={selectedCycleId === cycle.capa_cycle_id}
                  className={selectedCycleId === cycle.capa_cycle_id ? "selected" : ""}
                  key={cycle.capa_cycle_id}
                  onClick={() => setSelectedCycleId(cycle.capa_cycle_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedCycleId(cycle.capa_cycle_id);
                    }
                  }}
                  tabIndex={0}
                >
                  <td>{cycle.round_no}</td>
                  <td>{formatCompactDate(cycle.submitted_on)}</td>
                  <td>{formatCompactDate(cycle.assessed_on)}</td>
                  <td>{formatStatusLabel(cycle.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selectedCycle ? (
        <WorkspaceSection title={`Chi tiết vòng CAPA ${selectedCycle.round_no}`}>
          <div className="detail-grid compact-grid">
            <DetailValue label="Ngày yêu cầu" value={formatCompactDate(selectedCycle.requested_on)} />
            <DetailValue label="Ngày nhận" value={formatCompactDate(selectedCycle.submitted_on)} />
            <DetailValue label="Ngày xử lý" value={formatCompactDate(selectedCycle.assessed_on)} />
            <DetailValue label="Người xử lý" value={selectedCycle.assessor_name} />
            <DetailValue label="Kết quả" value={selectedCycle.result} />
            <DetailValue label="Trạng thái" value={formatStatusLabel(selectedCycle.status)} />
            <DetailValue label="Ghi chú" multiline value={selectedCycle.notes} />
          </div>
        </WorkspaceSection>
      ) : null}
    </div>
  );
}

function renderCaseStepContent(activeTab: string, caseWorkspace: CaseWorkspace) {
  if (activeTab === "Hồ sơ") {
    return (
      <div className="event-step-stack">
        <WorkspaceSection title="Thông tin hồ sơ">
          <div className="detail-grid compact-grid">
            <DetailValue label="Mã hồ sơ" value={caseWorkspace.application.dossier_code ?? caseWorkspace.case_summary.legacy_inspection_code} />
            <DetailValue label="Loại kiểm tra" value={caseWorkspace.case_summary.inspection_type} />
            <DetailValue label="GxP" value={caseWorkspace.case_summary.gxp_type} />
            <DetailValue label="Dây chuyền" value={caseWorkspace.case_summary.scope_code} />
            <DetailValue label="Tiêu chuẩn" value={caseWorkspace.case_summary.applicable_standard} />
            <DetailValue label="Năm mở hồ sơ" value={String(caseWorkspace.case_summary.opened_year ?? "")} />
            <DetailValue label="Ngày nộp" value={formatCompactDate(caseWorkspace.application.submitted_on)} />
            <DetailValue label="Trạng thái hồ sơ" value={formatStatusLabel(caseWorkspace.case_summary.state)} />
          </div>
        </WorkspaceSection>
        <WorkspaceSection title="Phạm vi">
          <div className="detail-grid compact-grid">
            <DetailValue label="Phạm vi đề nghị" value={caseWorkspace.application.dossier_reference} multiline />
            <DetailValue label="Phạm vi đánh giá" value={caseWorkspace.inspection.outcome_result} multiline />
          </div>
        </WorkspaceSection>
        <WorkspaceSection title="Xử lý hồ sơ">
          <div className="detail-grid compact-grid">
            <DetailValue label="Chuyên viên phụ trách" value={caseWorkspace.application.assigned_specialist} />
            <DetailValue label="Người nộp hồ sơ" value={caseWorkspace.application.applicant_name} />
          </div>
        </WorkspaceSection>
        <EmptySection
          title="Tài liệu"
          description="Step read model hiện chưa có owner API cho typed document checklist của hồ sơ này, nên chưa render nút tài liệu giả."
        />
      </div>
    );
  }

  if (activeTab === "Kiểm tra") {
    const inspection = caseWorkspace.inspection;
    const hasInspectionData = Boolean(
      inspection.decision_reference ||
        inspection.decision_document_hint ||
        inspection.plan_start_on ||
        inspection.plan_end_on ||
        inspection.planning_sheet_name ||
        inspection.inspected_on ||
        inspection.inspected_to_on ||
        inspection.executed_on ||
        inspection.bbkt_reference ||
        inspection.outcome_result ||
        inspection.team_display_text,
    );
    if (!hasInspectionData) {
      return (
        <EmptyState
          title="Chưa có dữ liệu kiểm tra"
          description="Case này chưa có inspection plan/team/outcome canonical đủ để hiển thị chi tiết kiểm tra."
        />
      );
    }
    return (
      <div className="event-step-stack">
        <WorkspaceSection title="Điều phối kiểm tra">
          <div className="detail-grid compact-grid">
            <DetailValue label="Quyết định kiểm tra" value={inspection.decision_reference} />
            <DetailValue label="Kế hoạch" value={inspection.planning_sheet_name} />
            <DetailValue label="Gợi ý tài liệu quyết định" value={inspection.decision_document_hint} />
            <DetailValue label="Ngày kiểm tra từ" value={formatCompactDate(inspection.inspected_on || inspection.plan_start_on)} />
            <DetailValue label="Ngày kiểm tra đến" value={formatCompactDate(inspection.inspected_to_on || inspection.plan_end_on)} />
            <DetailValue label="Thời điểm thực hiện" value={formatCompactDate(inspection.executed_on)} />
          </div>
        </WorkspaceSection>
        <WorkspaceSection title="Kết quả đánh giá">
          <div className="detail-grid compact-grid">
            <DetailValue label="Biên bản đánh giá" value={inspection.bbkt_reference} />
            <DetailValue label="Đoàn kiểm tra" multiline value={inspection.team_display_text} />
            <DetailValue label="Kết quả / phạm vi đánh giá" multiline value={inspection.outcome_result} />
          </div>
        </WorkspaceSection>
      </div>
    );
  }

  if (activeTab === "Khắc phục") {
    return <RemediationWorkspace cycles={caseWorkspace.remediation.cycles} />;
  }

  if (activeTab === "Xử lý") {
    const processing = caseWorkspace.processing;
    const hasProcessingData = Boolean(
      processing.assessed_on ||
        processing.assessor_name ||
        processing.assessment_result ||
        processing.notes ||
        processing.events.length > 0,
    );
    if (!hasProcessingData) {
      return (
        <EmptyState
          title="Chưa có dữ liệu xử lý"
          description="Canonical model hiện chưa có đủ dữ liệu xử lý hành chính riêng cho hồ sơ này."
        />
      );
    }
    return (
      <div className="event-step-stack">
        <WorkspaceSection title="Kết luận xử lý">
          <div className="detail-grid compact-grid">
            <DetailValue label="Ngày xử lý" value={formatCompactDate(processing.assessed_on)} />
            <DetailValue label="Người xử lý" value={processing.assessor_name} />
            <DetailValue label="Kết luận" multiline value={processing.assessment_result} />
            <DetailValue label="Ghi chú" multiline value={processing.notes} />
          </div>
        </WorkspaceSection>
        <WorkspaceSection title="Các mốc xử lý hành chính">
          {processing.events.length > 0 ? (
            <div className="table-scroll table-scroll-history">
              <table className="dense-table event-milestone-table">
                <thead>
                  <tr>
                    <th>Mốc</th>
                    <th>Ngày</th>
                    <th>Nội dung</th>
                  </tr>
                </thead>
                <tbody>
                  {processing.events.map((event, index) => (
                    <tr key={`${event.event_type}:${event.occurred_at ?? "none"}:${index}`}>
                      <td>{PROCESSING_EVENT_LABELS[event.event_type] ?? event.event_type}</td>
                      <td>{formatCompactDate(event.occurred_at)}</td>
                      <td>{event.payload ?? "Chưa có"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="Chưa có mốc xử lý" description="Chưa có inspection event hành chính nào được canonicalize cho hồ sơ này." />
          )}
        </WorkspaceSection>
      </div>
    );
  }

  if (activeTab === "Chứng nhận GxP") {
    return <LinkedGxpCertificates items={caseWorkspace.linked_gxp_certificates} />;
  }

  return <LinkedBusinessEligibilityCertificates items={caseWorkspace.linked_business_eligibility_certificates} />;
}

export function EventWorkspace({
  selectedHistory,
  caseWorkspace,
  caseWorkspaceLoading,
  caseWorkspaceError,
  activeTab,
  onTabChange,
}: {
  selectedHistory: FacilityHistoryItem | null;
  caseWorkspace: CaseWorkspace | null;
  caseWorkspaceLoading: boolean;
  caseWorkspaceError: string | null;
  activeTab: string;
  onTabChange: (tab: string) => void;
}) {
  if (!selectedHistory) {
    return (
      <EmptyState
        title="Chưa chọn sự kiện"
        description="Chọn một dòng lịch sử để xem vùng detail nghiệp vụ bên dưới."
      />
    );
  }

  return (
    <section className="event-workspace">
      <div className="panel-header">
        <div>
          <h3>{selectedHistory.reference_code ?? selectedHistory.event_type}</h3>
        </div>
        <StatusBadge value={selectedHistory.state} />
      </div>
      <nav aria-label="Quy trình xử lý sự kiện" className="workflow-stepper">
        <ol className="workflow-step-list">
          {EVENT_TABS.map((tab, index) => (
            <li key={tab}>
              <button
                aria-current={activeTab === tab ? "step" : undefined}
                className={activeTab === tab ? "workflow-step active" : "workflow-step"}
                onClick={() => onTabChange(tab)}
                type="button"
              >
                <span className="workflow-step-index">{index + 1}</span>
                <span>{tab}</span>
              </button>
            </li>
          ))}
        </ol>
      </nav>
      <div className="workspace-body event-workspace-body">
        {selectedHistory.source_type === "change_request" ? (
          <div className="event-step-stack">
            <WorkspaceSection title="Thông tin thay đổi">
              <div className="detail-grid compact-grid">
                <DetailValue label="Phân loại" value={formatHistoryEventType(selectedHistory.event_type)} />
                <DetailValue label="Mã tham chiếu" value={selectedHistory.reference_code ?? "Chưa có"} />
                <DetailValue label="Trạng thái" value={formatStatusLabel(selectedHistory.state)} />
                <DetailValue label="Ngày tiếp nhận" value={formatCompactDate(selectedHistory.occurred_on)} />
                <DetailValue label="Phạm vi" multiline value={selectedHistory.standard ?? "Chưa có dữ liệu chi tiết từ backend"} />
              </div>
            </WorkspaceSection>
            <EmptySection
              title="Workspace thay đổi"
              description="Change request read workspace canonical chưa được tách riêng trong vòng này, nên pane phải chỉ hiển thị summary fail-closed cho lựa chọn thay đổi."
            />
          </div>
        ) : caseWorkspaceLoading ? (
          <EmptyState title="Đang tải workspace hồ sơ" description="Đang lấy dữ liệu đọc theo case đã chọn từ authenticated API." />
        ) : caseWorkspaceError ? (
          <EmptyState
            title="Không tải được workspace hồ sơ"
            description="Workspace read model cho hồ sơ đang chọn hiện không sẵn sàng. Vui lòng chọn lại hoặc thử sau."
          />
        ) : caseWorkspace ? (
          renderCaseStepContent(activeTab, caseWorkspace)
        ) : (
          <EmptyState title="Chưa có workspace hồ sơ" description="Backend chưa trả dữ liệu workspace cho lựa chọn case hiện tại." />
        )}
      </div>
    </section>
  );
}
