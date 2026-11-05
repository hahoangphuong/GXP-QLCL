import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { getCaseWorkspace } from "../lib/api";

type Resolved = { owner: object; location: string | null; error: string | null };

function caseSearchLocation(caseId: string, summary: {
  id: string;
  site_id: string;
  gxp_type: string;
  production_line_id: string | null;
  production_line_code: string | null;
}): string {
  if (summary.id !== caseId || !summary.site_id || !summary.gxp_type) {
    throw new Error("Hồ sơ trả về không khớp định danh hoặc thiếu ngữ cảnh.");
  }
  const params = new URLSearchParams({
    site_id: summary.site_id,
    gxp_type: summary.gxp_type,
    history_id: caseId,
  });
  if (summary.production_line_id) params.set("production_line_id", summary.production_line_id);
  if (summary.production_line_code) params.set("line_code", summary.production_line_code);
  return "/search?" + params;
}

/** Resolve a Case UUID from the backend before handing it to the editing workspace. */
export function CaseDirectOpen({ access }: { access: ApiAccess }) {
  const { caseId } = useParams();
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [caseId, auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration]);
  const [result, setResult] = useState<Resolved | null>(null);
  const current = result?.owner === owner ? result : null;

  useEffect(() => {
    if (!canLoadSecureApi || !caseId) return;
    let live = true;
    void (async () => {
      try {
        const workspace = await getCaseWorkspace(caseId, auth, useStubAuth, bearerToken);
        if (!live) return;
        const location = caseSearchLocation(caseId, workspace.case_summary);
        setResult({ owner, location, error: null });
      } catch (error) {
        if (live) setResult({ owner, location: null, error: error instanceof Error ? error.message : "Không mở được hồ sơ." });
      }
    })();
    return () => { live = false; };
  }, [owner, caseId, auth, bearerToken, useStubAuth, canLoadSecureApi]);

  if (!canLoadSecureApi) return <section className="page-section"><h2>Cần đăng nhập</h2><p>Đăng nhập để mở hồ sơ được phân quyền.</p></section>;
  if (!caseId) return <p>Thiếu Case UUID.</p>;
  if (current?.location) return <Navigate to={current.location} replace />;
  return <section className="page-section">
    <h2>Định vị hồ sơ</h2>
    {current?.error ? <p role="alert">{current.error}</p> : <p role="status">Đang xác minh Case UUID và ngữ cảnh cơ sở...</p>}
    <Link className="text-link" to="/workflow">Quay lại Bàn công việc</Link>
  </section>;
}
