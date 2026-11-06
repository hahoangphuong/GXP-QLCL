import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import type { ApiAccess } from "../App";
import { searchSitesByName } from "../lib/api";
import type { Site } from "../types";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_RESULTS = 20;

function verifiedSites(value: Site[]): Site[] {
  if (!Array.isArray(value) || value.length > MAX_RESULTS) throw new Error("Kết quả tìm cơ sở không hợp lệ.");
  const seen = new Set<string>();
  for (const site of value) {
    if (!site || !UUID.test(site.id) || !UUID.test(site.company_id)
      || typeof site.site_name !== "string" || !site.site_name.trim()
      || (site.province_name !== null && typeof site.province_name !== "string")
      || seen.has(site.id.toLowerCase())) {
      throw new Error("Kết quả tìm cơ sở có định danh canonical không hợp lệ.");
    }
    seen.add(site.id.toLowerCase());
  }
  return value;
}

type SearchResult = {
  owner: object;
  query: string;
  status: "loading" | "ready" | "error";
  rows: Site[];
};

export function EligibilitySitePicker({
  access, onSelect,
}: {
  access: ApiAccess;
  onSelect: (siteId: string) => void;
}) {
  const { auth, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [
    auth.username, auth.role, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration,
  ]);
  const requestGeneration = useRef(0);
  const [query, setQuery] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResult | null>(null);
  useEffect(() => () => { requestGeneration.current += 1; }, [owner]);
  const visible = canLoadSecureApi && result?.owner === owner && result.query === query.trim()
    ? result : null;

  function editQuery(value: string) {
    requestGeneration.current += 1;
    setQuery(value);
    setValidation(null);
    setResult(null);
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canLoadSecureApi) return;
    const q = query.trim();
    if (q.length < 2 || q.length > 80 || /[\u0000-\u001f\u007f]/.test(q)) {
      setValidation("Nhập từ 2 đến 80 ký tự tên cơ sở hợp lệ.");
      setResult(null);
      return;
    }
    setValidation(null);
    const generation = ++requestGeneration.current;
    setResult({ owner, query: q, status: "loading", rows: [] });
    void searchSitesByName(q, auth, useStubAuth, bearerToken)
      .then(rows => {
        const valid = verifiedSites(rows);
        if (generation === requestGeneration.current) {
          setResult({ owner, query: q, status: "ready", rows: valid });
        }
      })
      .catch(() => {
        if (generation === requestGeneration.current) {
          setResult({ owner, query: q, status: "error", rows: [] });
        }
      });
  }

  if (!canLoadSecureApi) return null;
  return <section className="eligibility-site-picker" aria-label="Tìm Site theo tên cơ sở">
    <form onSubmit={search}>
      <label htmlFor="eligibility-site-name-search">Tìm cơ sở theo tên</label>
      <div className="report-actions">
        <input id="eligibility-site-name-search" value={query} maxLength={80}
          onChange={event => editQuery(event.target.value)} placeholder="Nhập tên cơ sở (ít nhất 2 ký tự)" />
        <button type="submit">Tìm cơ sở</button>
      </div>
      {validation && <p role="alert">{validation}</p>}
    </form>
    <p className="muted-copy">Kết quả từ danh mục Site có phân quyền (tối đa 20). Chọn đúng cơ sở theo tên và tỉnh/thành để tra cứu chứng nhận.</p>
    {visible?.status === "loading" && <p role="status">Đang tìm cơ sở...</p>}
    {visible?.status === "error" && <p role="alert">Không thể tìm cơ sở hoặc kết quả có định danh không hợp lệ.</p>}
    {visible?.status === "ready" && visible.rows.length === 0 && <p role="status">Không tìm thấy cơ sở phù hợp.</p>}
    {visible?.status === "ready" && visible.rows.length > 0 && <div className="table-scroll">
      <table className="dense-table">
        <thead><tr><th>Cơ sở</th><th>Tỉnh/thành</th><th>Site UUID canonical</th><th>Chọn</th></tr></thead>
        <tbody>{visible.rows.map(site => <tr key={site.id}>
          <td>{site.site_name}</td>
          <td>{site.province_name ?? "Chưa ghi nhận"}</td>
          <td className="multiline-cell">{site.id}</td>
          <td><button type="button" onClick={() => onSelect(site.id)}
            aria-label={`Chọn Site ${site.site_name} — ${site.id}`}>Chọn Site</button></td>
        </tr>)}</tbody>
      </table>
    </div>}
  </section>;
}
