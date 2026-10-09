// Captions verified against FilterForm.frm initialization and UTF-16 FRX strings.
// These controls deliberately have no filter handler or request ownership.
type Group = { title: string; options: string[]; dates: string[]; doseRows?: Array<{ label: string; options: string[] }> };
const columns: Group[][] = [
  [
    { title: "Tình trạng chứng chỉ, tuân thủ", options: ["Chưa có chứng chỉ", "Đã có chứng chỉ", "Chứng chỉ còn hạn", "Chứng chỉ hết hạn", "Còn tuân thủ", "Không tuân thủ"], dates: ["Thời gian cấp", "Thời gian hết hạn", "Thời gian ktra giám sát"] },
    { title: "", options: ["Cơ sở mới", "Dây chuyền mới"], dates: [] },
  ],
  [
    { title: "Tình trạng đăng ký", options: ["Đăng ký mới", "Đã tái đăng ký"], dates: ["Thời gian đăng ký"] },
    { title: "Tình trạng kiểm tra", options: ["Chưa kiểm tra", "Có quyết định, chưa KT", "Đã kiểm tra"], dates: ["Thời gian kiểm tra"] },
    { title: "Tiến độ xử lý", options: ["Đang xử lý", "Đã hoàn thành"], dates: [] },
  ],
  [
    { title: "Loại sản phẩm", options: ["Tân dược", "Đông dược", "Vắc xin", "Sinh phẩm", "Nguyên liệu tân dược", "Nguyên liệu đông dược"], dates: [] },
    { title: "Dạng bào chế", options: ["Vi sinh", "Nhỏ mắt", "Nang mềm", "Dung dịch thẩm phân", "Dược liệu đã chế biến", "Đạn, trứng", "Viên nội tiết", "Vỏ nang", "Cao dược liệu", "Ống hít"], dates: [], doseRows: [
      { label: "Tiêm bột:", options: ["Non-beta", "Peni", "Cepha", "Khác", "Đông khô"] },
      { label: "Tiêm nước:", options: ["Non-beta", "Peni", "Cepha", "Khác", "Dịch truyền"] },
      { label: "Viên, cốm, bột:", options: ["Non-beta", "Peni", "Cepha", "Dược liệu", "Hoàn cứng, hoàn mềm", "Sủi bọt"] },
      { label: "Nước uống:", options: ["Non-beta", "Peni", "Cepha", "Dược liệu"] },
      { label: "Nước dg ngoài:", options: ["Non-beta", "Dược liệu"] },
      { label: "Kem, gel, mỡ:", options: ["Non-beta", "Dược liệu"] },
    ] },
    { title: "Tình trạng hiệu lực", options: ["Còn hiệu lực", "Hết hiệu lực"], dates: [] },
  ],
];

export function LegacyUnavailableFilters() {
  return <section aria-label="Điều kiện legacy chưa khả dụng" className="legacy-unavailable-filters">
    <p>Các điều kiện legacy bên dưới chưa được hỗ trợ trên web.</p>
    <div className="legacy-unavailable-columns">
      {columns.map((groups, column) => <div key={column}>
        {groups.map(group => <fieldset disabled key={group.title}>
          {group.title ? <legend>{group.title}</legend> : null}
          {group.doseRows?.map(row => <div className="legacy-disabled-dose-row" key={row.label}>
            <span>{row.label}</span>
            <div>{row.options.map(option => <label key={option}><input aria-label={`${row.label} ${option}`} type="checkbox" />{option}</label>)}</div>
          </div>)}
          {group.options.map(label => <label key={label}><input type="checkbox" />{label}</label>)}
          {group.dates.map(label => <div className="legacy-disabled-date-range" key={label}>
            <label><input type="checkbox" />{label}</label>
            <label>Từ:<input aria-label={`${label} — từ`} type="date" /></label>
            <label>Đến:<input aria-label={`${label} — đến`} type="date" /></label>
          </div>)}
        </fieldset>)}
      </div>)}
    </div>
  </section>;
}
