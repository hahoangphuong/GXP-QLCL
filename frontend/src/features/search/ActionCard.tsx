import type { FacilitySearchResult } from "../../types";

const ACTIONS = ["Công ty mới", "Cơ sở mới", "D.chuyền mới", "Tái đánh giá", "Thay đổi"] as const;

export function ActionCard({ selectedResult }: { selectedResult: FacilitySearchResult | null }) {
  return (
    <section className="panel panel-tight action-panel">
      <div className="panel-header">
        <h3>Xử lý</h3>
      </div>
      {selectedResult ? (
        <>
          <p className="panel-meta action-context" title={selectedResult.facility_name}>
            {selectedResult.context_code ?? selectedResult.facility_code ?? "Chưa có mã"} · {selectedResult.facility_name}
          </p>
          <div className="action-grid" aria-label="Thao tác theo ngữ cảnh cơ sở">
            {ACTIONS.map((action) => (
              <button disabled key={action} type="button">
                {action}
              </button>
            ))}
          </div>
        </>
      ) : (
        <p className="panel-meta action-context">Chọn một cơ sở/dây chuyền để mở các thao tác theo ngữ cảnh.</p>
      )}
    </section>
  );
}
