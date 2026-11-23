import { useEffect, useId, useLayoutEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import type { ApiAccess } from "../../App";
import { correctCompanyProfile, correctSiteProfile, getCompany, getSite } from "../../lib/api";
import type { CompanyDetail, CompanyProfileCorrection, CompanyProfileExpected, SiteDetail, SiteProfileCorrection, SiteProfileExpected } from "../../types";

type Kind = "company" | "site";
export type ProfileReadback = { kind: "company"; value: CompanyDetail } | { kind: "site"; value: SiteDetail };
type Profile = { kind: "company"; id: string; expected: CompanyProfileExpected }
  | { kind: "site"; id: string; expected: SiteProfileExpected };
type Field<Key extends string> = { key: Key; label: string; limit: number; required?: boolean; multiline?: boolean };
const fields: { company: readonly Field<keyof CompanyProfileCorrection["changes"]>[];
  site: readonly Field<keyof SiteProfileCorrection["changes"]>[] } = {
  company: [
    { key: "legal_name", label: "Tên pháp nhân", limit: 512, required: true },
    { key: "english_name", label: "Tên tiếng Anh", limit: 512 },
    { key: "short_name", label: "Tên viết tắt", limit: 128 },
    { key: "legal_address", label: "Địa chỉ pháp lý", limit: 10000, required: true, multiline: true },
    { key: "legal_address_en", label: "Địa chỉ tiếng Anh", limit: 10000, multiline: true },
  ],
  site: [
    { key: "site_name", label: "Tên cơ sở", limit: 512, required: true },
    { key: "site_name_en", label: "Tên tiếng Anh", limit: 512 },
    { key: "site_address", label: "Địa chỉ cơ sở", limit: 10000, required: true, multiline: true },
    { key: "site_address_en", label: "Địa chỉ tiếng Anh", limit: 10000, multiline: true },
    { key: "province_name", label: "Tỉnh/thành phố", limit: 255 },
    { key: "short_name", label: "Tên viết tắt", limit: 255 },
  ],
};
const labels: Record<Kind, string> = { company: "Công ty", site: "Cơ sở" };
type Phase = "edit" | "saving" | "conflict" | "unknown" | "saved" | "denied";
type Draft = { profile: Profile; inputs: Record<string, string>; reason: string; phase: Phase;
  message?: string; readbackError?: string; latest?: Profile; auditId?: string };
export type ProfileDrafts = { entries: Map<string, Draft>; pending: Set<string> };

function profileFrom(record: ProfileReadback): Profile {
  if (record.kind === "company") {
    const { id, legal_name, legal_address, english_name, short_name, legal_address_en, is_inactive } = record.value;
    if (!id || typeof legal_name !== "string" || typeof is_inactive !== "boolean") throw new Error("Hồ sơ Công ty không đầy đủ.");
    return { kind: "company", id, expected: { legal_name, legal_address: legal_address ?? null, english_name: english_name ?? null,
      short_name: short_name ?? null, legal_address_en: legal_address_en ?? null, is_inactive } };
  }
  const { id, company_id, site_name, site_address, site_name_en, site_address_en, province_name, short_name } = record.value;
  if (!id || !company_id || typeof site_name !== "string") throw new Error("Hồ sơ Cơ sở không đầy đủ.");
  return { kind: "site", id, expected: { company_id, site_name, site_address: site_address ?? null,
    site_name_en: site_name_en ?? null, site_address_en: site_address_en ?? null,
    province_name: province_name ?? null, short_name: short_name ?? null } };
}

function fieldValue(profile: Profile, key: string) {
  const value = (profile.expected as Record<string, unknown>)[key];
  return typeof value === "string" ? value : "";
}

function readInputs(profile: Profile) {
  return Object.fromEntries(fields[profile.kind].map(({ key }) => [key, fieldValue(profile, key)]));
}

function errorStatus(error: unknown) {
  return error instanceof Error && "status" in error ? error.status : null;
}

function readError(error: unknown) {
  if (errorStatus(error) === 403) return "Bạn không đủ quyền đọc hoặc hiệu chỉnh hồ sơ.";
  if (errorStatus(error) === 404) return "Bản ghi không còn tồn tại.";
  return error instanceof Error ? error.message : "Không đọc được hồ sơ.";
}

export function ProfileCorrectionActions({ access, siteId, drafts, onReadback }: {
  access: ApiAccess; siteId: string; drafts: ProfileDrafts; onReadback: (record: ProfileReadback) => void;
}) {
  const [kind, setKind] = useState<Kind | null>(null);
  return <div className="profile-correction">
    <div className="profile-correction-actions">
      {(["company", "site"] as const).map(value => <button className="secondary" type="button" key={value}
        aria-expanded={kind === value} onClick={() => setKind(value)}>Sửa thông tin {labels[value]}</button>)}
    </div>
    {kind && <ProfileEditor key={kind} kind={kind} siteId={siteId} access={access} drafts={drafts}
      onReadback={onReadback} onClose={() => setKind(null)} />}
  </div>;
}

function ProfileEditor({ kind, siteId, access, drafts, onReadback, onClose }: {
  kind: Kind; siteId: string; access: ApiAccess; drafts: ProfileDrafts;
  onReadback: (record: ProfileReadback) => void; onClose: () => void;
}) {
  const owner = JSON.stringify([siteId, kind]);
  const [draft, setDraft] = useState(() => drafts.entries.get(owner));
  const [loadError, setLoadError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const heading = useId();
  const live = useRef(false);
  const command = useRef(false);
  const readCommand = useRef(false);
  const { auth, useStubAuth, bearerToken } = access;

  useLayoutEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      const entry = drafts.entries.get(owner);
      if (entry?.phase === "saving") drafts.entries.set(owner, { ...entry, phase: "unknown",
        message: "Chưa xác định được kết quả của lần lưu trước. Hãy kiểm tra hồ sơ trước khi tiếp tục." });
    };
  }, [drafts, owner]);

  useEffect(() => {
    if (drafts.entries.has(owner)) return;
    let active = true;
    void (async () => {
      try {
        const site = await getSite(siteId, auth, useStubAuth, bearerToken);
        if (!active) return;
        if (site.id !== siteId || !site.company_id) throw new Error("Hồ sơ không khớp Cơ sở đã chọn.");
        const value: ProfileReadback = kind === "site" ? { kind, value: site }
          : { kind, value: await getCompany(site.company_id, auth, useStubAuth, bearerToken) };
        if (!active) return;
        if (value.kind === "company" && value.value.id !== site.company_id) throw new Error("Hồ sơ không khớp Công ty của Cơ sở.");
        const profile = profileFrom(value);
        const entry: Draft = { profile, inputs: readInputs(profile), reason: "", phase: "edit" };
        drafts.entries.set(owner, entry);
        setDraft(entry);
      } catch (error) {
        if (active) setLoadError(readError(error));
      }
    })();
    return () => { active = false; };
  }, [auth, bearerToken, drafts, kind, owner, siteId, useStubAuth]);

  function publish(entry: Draft) {
    if (!live.current) return;
    drafts.entries.set(owner, entry);
    setDraft(entry);
  }

  async function readCurrent(profile: Profile) {
    if (profile.kind === "company") {
      const site = await getSite(siteId, auth, useStubAuth, bearerToken);
      if (!live.current) return null;
      if (site.id !== siteId || site.company_id !== profile.id) throw new Error("Công ty của Cơ sở đã thay đổi.");
    }
    const record: ProfileReadback = profile.kind === "company"
      ? { kind: "company", value: await getCompany(profile.id, auth, useStubAuth, bearerToken) }
      : { kind: "site", value: await getSite(profile.id, auth, useStubAuth, bearerToken) };
    if (!live.current) return null;
    const latest = profileFrom(record);
    if (latest.id !== profile.id || (profile.kind === "site" && latest.kind === "site"
      && latest.expected.company_id !== profile.expected.company_id)) throw new Error("Hồ sơ đọc lại không khớp định danh đã duyệt.");
    return { record, latest };
  }

  async function review(entry: Draft) {
    if (readCommand.current) return;
    readCommand.current = true;
    setLoading(true);
    const reviewing = { ...entry, latest: undefined, readbackError: undefined };
    publish(reviewing);
    try {
      const result = await readCurrent(entry.profile);
      if (!result) return;
      onReadback(result.record);
      publish({ ...reviewing, latest: result.latest });
    } catch (error) {
      publish({ ...reviewing, readbackError: readError(error) });
    } finally {
      readCommand.current = false;
      if (live.current) setLoading(false);
    }
  }

  const edited = draft ? fields[kind].filter(({ key }) =>
    draft.inputs[key] !== fieldValue(draft.profile, key)
    && draft.inputs[key].trim() !== fieldValue(draft.profile, key)) : [];
  const requiredMissing = edited.some(({ key, required }) => required && !draft?.inputs[key].trim());
  const canSave = draft?.phase === "edit" && edited.length > 0 && !requiredMissing && Boolean(draft.reason.trim());

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft || !canSave || command.current) return;
    const { profile } = draft;
    const entity = JSON.stringify([profile.kind, profile.id]);
    if (drafts.pending.has(entity)) {
      publish({ ...draft, message: "Hồ sơ này đang có một yêu cầu lưu chưa hoàn tất." });
      return;
    }
    drafts.pending.add(entity);
    command.current = true;
    const changes = Object.fromEntries(edited.map(({ key }) => [key, draft.inputs[key].trim() || null]));
    const reason = draft.reason.trim();
    publish({ ...draft, phase: "saving", message: undefined, readbackError: undefined });
    try {
      let auditId: string;
      try {
        const payload = profile.kind === "company"
          ? await correctCompanyProfile(profile.id, { expected: profile.expected, changes, reason } satisfies CompanyProfileCorrection, auth, useStubAuth, bearerToken)
          : await correctSiteProfile(profile.id, { expected: profile.expected, changes, reason } satisfies SiteProfileCorrection, auth, useStubAuth, bearerToken);
        if (payload.id !== profile.id || !payload.audit_event_id || (profile.kind === "site"
          && (!("company_id" in payload) || payload.company_id !== profile.expected.company_id))) throw new Error("Phản hồi lưu không khớp hồ sơ.");
        auditId = payload.audit_event_id;
      } catch (error) {
        if (!live.current) return;
        const status = errorStatus(error);
        const entry: Draft = status === 409 ? { ...draft, phase: "conflict", message: "Hồ sơ đã thay đổi hoặc đang bị khóa. Đối chiếu dữ liệu trước khi tiếp tục." }
          : status === 401 || status === 403 || status === 404 ? { ...draft, phase: "denied", message: status === 401 ? "Phiên đăng nhập không còn hợp lệ." : readError(error) }
          : status === 422 ? { ...draft, phase: "edit", message: "Dữ liệu hiệu chỉnh không hợp lệ. Kiểm tra các trường và lý do." }
          : { ...draft, phase: "unknown", message: "Chưa xác định được kết quả lưu. Có thể đọc lại hồ sơ để đối chiếu; dữ liệu trùng khớp không xác nhận lần lưu." };
        publish(entry);
        if (entry.phase === "conflict") await review(entry);
        return;
      }
      if (!live.current) return;
      const saved: Draft = { ...draft, phase: "saved", auditId, message: "Đã lưu hiệu chỉnh." };
      publish(saved);
      await review(saved);
    } finally {
      drafts.pending.delete(entity);
      command.current = false;
    }
  }

  function close() {
    if (draft && (draft.phase === "edit" || draft.phase === "saved" || draft.phase === "denied")) drafts.entries.delete(owner);
    onClose();
  }

  return <section className="profile-correction-editor" aria-labelledby={heading}>
    <h4 id={heading}>Hiệu chỉnh hồ sơ {labels[kind]}</h4>
    {!draft ? <><p role={loadError ? "alert" : "status"}>{loadError ?? "Đang đọc hồ sơ hiện tại…"}</p>
      <button type="button" className="secondary" onClick={close}>Đóng</button></> :
      <form onSubmit={event => { void save(event); }}>
        <fieldset disabled={draft.phase !== "edit"} className="profile-correction-fields">
          <legend>Thông tin đăng ký</legend>
          {fields[kind].map(({ key, label, limit, multiline }) => {
            const props = { value: draft.inputs[key], maxLength: limit, onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
              publish({ ...draft, inputs: { ...draft.inputs, [key]: event.target.value } }) };
            return <label key={key}>{label}{multiline ? <textarea rows={2} {...props} /> : <input type="text" {...props} />}</label>;
          })}
          <label>Lý do hiệu chỉnh<textarea rows={2} required maxLength={10000} value={draft.reason}
            onChange={event => publish({ ...draft, reason: event.target.value })} /></label>
        </fieldset>
        {requiredMissing && <p role="alert">Tên và địa chỉ đang hiệu chỉnh không được để trống.</p>}
        {draft.phase === "saving" && <p role="status">Đang lưu hiệu chỉnh…</p>}
        {draft.message && <p role={draft.phase === "saved" ? "status" : "alert"}>{draft.message}</p>}
        {draft.readbackError && <p role="alert">Đọc lại hồ sơ: {draft.readbackError}</p>}
        {draft.auditId && <p>Mã audit: {draft.auditId}</p>}
        {draft.latest && draft.phase !== "saved" && <div className="table-scroll"><table className="dense-table">
          <caption>Đối chiếu hồ sơ hiện tại với bản nháp</caption>
          <thead><tr><th>Trường</th><th>Khi mở</th><th>Hiện tại</th><th>Bản nháp</th></tr></thead>
          <tbody>{fields[kind].map(({ key, label }) => <tr key={key}><th scope="row">{label}</th>
            <td>{fieldValue(draft.profile, key) || "—"}</td><td>{fieldValue(draft.latest!, key) || "—"}</td>
            <td>{draft.inputs[key] || "—"}</td></tr>)}</tbody>
        </table></div>}
        <div className="profile-correction-actions">
          {draft.phase === "edit" && <button type="submit" disabled={!canSave}>Lưu thay đổi</button>}
          {draft.phase === "conflict" && draft.latest && <button type="button" disabled={loading} onClick={() => {
            const latest = draft.latest!;
            const inputs = readInputs(latest);
            for (const { key } of edited) inputs[key] = draft.inputs[key];
            publish({ profile: latest, inputs, reason: draft.reason, phase: "edit" });
          }}>Dùng dữ liệu mới để sửa tiếp</button>}
          {(draft.phase === "unknown" || draft.phase === "conflict" || (draft.phase === "saved" && !draft.latest))
            && <button className="secondary" type="button" disabled={loading} onClick={() => { void review(draft); }}>Kiểm tra hồ sơ hiện tại</button>}
          {draft.phase === "unknown" && draft.latest && <button className="secondary" type="button" disabled={loading}
            onClick={() => { drafts.entries.delete(owner); onClose(); }}>Kết thúc đối chiếu và bỏ bản nháp</button>}
          <button className="secondary" type="button" disabled={draft.phase === "saving" || loading} onClick={close}>Đóng</button>
        </div>
      </form>}
  </section>;
}
