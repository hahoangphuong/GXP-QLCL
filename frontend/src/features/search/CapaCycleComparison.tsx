import { useState } from "react";

import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import type { CaseWorkspaceRemediationCycle } from "../../types";

// Purely read-only presentation of cycles returned by the canonical Case API.
// Selection uses CAPA UUID, never round number or table index as a relationship.
export function CapaCycleComparison({ cycles }: { cycles: CaseWorkspaceRemediationCycle[] }) {
  const [leftId, setLeftId] = useState(() => cycles.at(-2)?.capa_cycle_id ?? "");
  const [rightId, setRightId] = useState(() => cycles.at(-1)?.capa_cycle_id ?? "");
  if (cycles.length < 2) return null;

  const left = cycles.find(cycle => cycle.capa_cycle_id === leftId) ?? cycles.at(-2)!;
  const right = cycles.find(cycle => cycle.capa_cycle_id === rightId) ?? cycles.at(-1)!;
  const fields = [
    ["Trạng thái", formatStatusLabel(left.status), formatStatusLabel(right.status)],
    ["Số công văn đến", left.incoming_reference ?? "", right.incoming_reference ?? ""],
    ["Ngày yêu cầu", formatCompactDate(left.requested_on), formatCompactDate(right.requested_on)],
    ["Ngày tiếp nhận", formatCompactDate(left.submitted_on), formatCompactDate(right.submitted_on)],
    ["Ngày đánh giá", formatCompactDate(left.assessed_on), formatCompactDate(right.assessed_on)],
    ["Kết quả đánh giá", left.result ? formatStatusLabel(left.result) : "", right.result ? formatStatusLabel(right.result) : ""],
    ["Người đánh giá", left.assessor_name ?? "", right.assessor_name ?? ""],
    ["Ghi chú", left.notes ?? "", right.notes ?? ""],
  ] as const;
  const distinct = left.capa_cycle_id !== right.capa_cycle_id;

  return <details className="workspace-section" aria-label="So sánh các vòng khắc phục">
    <summary>So sánh hai vòng khắc phục</summary>
    <div className="panel-actions">
      <label>Vòng khắc phục thứ nhất
        <select aria-label="Vòng khắc phục thứ nhất" value={left.capa_cycle_id} onChange={event => setLeftId(event.target.value)}>
          {cycles.map(cycle => <option key={cycle.capa_cycle_id} value={cycle.capa_cycle_id}>Vòng {cycle.round_no} — {formatStatusLabel(cycle.status)}</option>)}
        </select>
      </label>
      <label>Vòng khắc phục thứ hai
        <select aria-label="Vòng khắc phục thứ hai" value={right.capa_cycle_id} onChange={event => setRightId(event.target.value)}>
          {cycles.map(cycle => <option key={cycle.capa_cycle_id} value={cycle.capa_cycle_id}>Vòng {cycle.round_no} — {formatStatusLabel(cycle.status)}</option>)}
        </select>
      </label>
    </div>
    {!distinct ? <p role="status">Chọn hai vòng khắc phục khác nhau để đối chiếu.</p> :
      <div className="table-scroll">
        <table className="dense-table" aria-label="Đối chiếu dữ liệu hai vòng CAPA">
          <thead><tr><th>Thông tin</th><th>Vòng {left.round_no}</th><th>Vòng {right.round_no}</th><th>Đối chiếu</th></tr></thead>
          <tbody>{fields.map(([label, before, after]) =>
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>{before || "—"}</td>
              <td>{after || "—"}</td>
              <td>{before === after ? "Không đổi" : "Khác nhau"}</td>
            </tr>)}</tbody>
        </table>
      </div>}
  </details>;
}
