import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { ApiAccess } from "../../App";
import { searchFacilities } from "../../lib/api";
import type { FacilitySearchResult } from "../../types";

const PAGE_SIZE = 200;
const MAX_CONTEXTS = 10000;
const SUPPORTED_GXP = new Set(["GMP", "GLP", "GMPbb"]);

export function changeRequestSearchLink(row: FacilitySearchResult, siteId: string, changeRequestId: string): string | null {
  if (row.site_id !== siteId || !SUPPORTED_GXP.has(row.gxp_type ?? "") || !row.result_key || !changeRequestId) return null;
  if (row.production_line_identity_state === "canonical" && !row.production_line_id) return null;
  if (row.production_line_identity_state === "legacy_unlinked" && !row.line_code) return null;
  if (row.production_line_identity_state === "facility_wide" && (row.production_line_id || row.line_code)) return null;
  const params = new URLSearchParams({
    site_id: siteId,
    result_key: row.result_key,
    gxp_type: row.gxp_type!,
    context_gxp: row.gxp_type!,
    history_id: changeRequestId,
    facility_tab: "Các đợt kiểm tra & thay đổi",
    event_tab: "Đề nghị",
  });
  if (row.production_line_id) params.set("production_line_id", row.production_line_id);
  if (row.line_code) params.set("line_code", row.line_code);
  return "/search?" + params.toString();
}

export function ChangeRequestContextPicker({
  access, changeRequestId, siteId,
}: { access: ApiAccess; changeRequestId: string; siteId: string }) {
  const { auth, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [auth, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration, siteId, changeRequestId]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const requestRef = useRef<object | null>(null);
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<{
    owner: object; status: "loading" | "ready" | "error"; rows: FacilitySearchResult[]; error?: string;
  } | null>(null);
  const current = state?.owner === owner ? state : null;

  useEffect(() => {
    requestRef.current = null;
    return () => { requestRef.current = null; };
  }, [owner]);

  async function resolveContexts() {
    if (!canLoadSecureApi || requestRef.current) return;
    const token = {};
    requestRef.current = token;
    setOpen(true);
    setState({ owner, status: "loading", rows: [] });
    try {
      const rows: FacilitySearchResult[] = [];
      let total: number | null = null;
      const keys = new Set<string>();
      do {
        const page = await searchFacilities({ site_id: siteId, offset: rows.length, limit: PAGE_SIZE },
          auth, useStubAuth, bearerToken);
        if (requestRef.current !== token || ownerRef.current !== owner) return;
        if (page.offset !== rows.length || !Number.isSafeInteger(page.total_count) ||
            page.total_count < 0 || page.total_count > MAX_CONTEXTS ||
            (total !== null && total !== page.total_count) ||
            page.items.length > PAGE_SIZE ||
            rows.length + page.items.length > page.total_count ||
            (rows.length < page.total_count && page.items.length === 0)) {
          throw new Error("Danh sách ngữ cảnh không đầy đủ hoặc thay đổi khi phân trang. Không thể mở nhầm hồ sơ.");
        }
        total = page.total_count;
        for (const row of page.items) {
          if (row.site_id !== siteId || !row.result_key || keys.has(row.result_key)) {
            throw new Error("Danh sách ngữ cảnh không khớp Site hoặc có kết quả trùng.");
          }
          keys.add(row.result_key);
          rows.push(row);
        }
      } while (rows.length < (total ?? 0));
      setState({ owner, status: "ready", rows });
    } catch (error) {
      if (requestRef.current === token && ownerRef.current === owner)
        setState({ owner, status: "error", rows: [], error: error instanceof Error ? error.message : "Không thể tìm ngữ cảnh." });
    } finally {
      if (requestRef.current === token) requestRef.current = null;
    }
  }

  return <section className="panel">
    <div className="panel-header">
      <h3>Mở workspace xử lý</h3>
      <button type="button" className="secondary" disabled={!canLoadSecureApi || current?.status === "loading"}
        onClick={() => { if (open) { setOpen(false); } else { void resolveContexts(); } }}>
        {open ? "Ẩn lựa chọn" : "Chọn ngữ cảnh xử lý"}
      </button>
    </div>
    <p className="muted-copy">Change Request thuộc Site, không có GxP canonical. Chọn rõ loại GxP và ngữ cảnh dây chuyền từ kết quả Tra cứu; workspace sẽ kiểm tra lại Change Request UUID trong lịch sử trước khi mở.</p>
    {open && (!current || current.status === "loading" ? <p role="status">Đang tìm ngữ cảnh của Site...</p>
      : current.status === "error" ? <p role="alert">{current.error}</p>
      : <div>
        <p>{current.rows.length} ngữ cảnh tại Site; chỉ hiển thị liên kết có GxP và định danh đầy đủ.</p>
        <div className="table-scroll">
          <table className="dense-table">
            <thead><tr><th>GxP</th><th>Ngữ cảnh</th><th>Dây chuyền</th><th>Mở</th></tr></thead>
            <tbody>{current.rows.map(row => {
              const href = changeRequestSearchLink(row, siteId, changeRequestId);
              return <tr key={row.result_key}>
                <td>{row.gxp_type ?? "Chưa phân loại"}</td>
                <td>{row.context_code ?? row.facility_code ?? "Cơ sở"}</td>
                <td>{row.line_code ?? (row.result_grain === "facility" ? "Toàn cơ sở" : "Chưa xác minh")}</td>
                <td>{href ? <Link className="text-link" to={href}>Mở ngữ cảnh này</Link> : "Không hỗ trợ"}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>
        {current.rows.length === 0 && <p>Site này chưa có ngữ cảnh GxP được ghi nhận; không thể tự chọn loại GxP.</p>}
      </div>)}
  </section>;
}
