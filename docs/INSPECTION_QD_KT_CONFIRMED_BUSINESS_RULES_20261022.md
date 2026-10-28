# QĐKT — xác nhận nghiệp vụ ngày 22/10/2026

Tài liệu ghi nhận xác nhận trực tiếp của chủ nghiệp vụ. Đây là hợp đồng ngữ nghĩa nghiệp vụ, không tự nhận rằng importer/schema/VBA hiện tại đã thực hiện đủ mọi quy tắc. Giữ nguyên các artifact provenance từ VBA.

## Nhiều quyết định
- Một Case có thể có QĐKT ban đầu, điều chỉnh hoặc thay thế.
- Các biểu mẫu **tham chiếu quyết định cập nhật nhất**.
- Biểu mẫu QĐKT cho mọi loại quyết định dùng **cùng một template**. Phần nội dung sửa đổi/thay thế người dùng tự biên tập thủ công; backend không tự phát sinh đoạn sửa đổi.
- Cần kiểm chứng định nghĩa quyết định cập nhật nhất, thứ tự ban hành và quan hệ thay thế từ nguồn lưu trữ. Không dùng ID lớn nhất, thứ tự insert hoặc scalar projection bất kỳ để đoán. Gate chỉ nhận đúng một quyết định là tập con an toàn, không phải quy tắc cuối cùng cho Case có nhiều quyết định.

## Địa chỉ và địa danh
- Địa điểm kiểm tra lấy từ địa chỉ cơ sở đã đăng ký và thống nhất ở mọi nơi. Truy vết từ Case đến Site; không sử dụng planning-row tự do nếu trái dữ liệu Site.
- Cần chứng minh phép biến đổi tên địa danh/tỉnh thành trong VBA cho Diadiem và Diadiemx; không tự suy ra bằng các chuỗi con.

## Cơ quan chuyên môn VKN/VKNx
- Cơ sở sản xuất vắc xin hoặc sinh phẩm: Viện Kiểm định quốc gia Vắc xin và Sinh phẩm y tế, không phụ thuộc địa lý.
- Cơ sở sản xuất thuốc từ Đà Nẵng trở ra Bắc: Viện Kiểm nghiệm thuốc Trung ương.
- Các địa phương còn lại: Viện Kiểm nghiệm thuốc Thành phố Hồ Chí Minh.
- VBA có biểu diễn tên đầy đủ và rút gọn tương ứng VKNx và VKN. Trước khi lập mã xác định cần kiểm chứng trường phân loại vắc xin/sinh phẩm, ngưỡng/mã địa phương và bản đồ tỉnh thành của legacy. Không so sánh tên tỉnh theo từ điển, không suy đoán bằng tên công ty.

## Ngày trên bản dự thảo
- Giữ trống ngày ban hành trong biểu mẫu Word đúng format mẫu, vì QĐKT tạo ra chỉ là bản dự thảo.
- Hệ thống văn bản hành chính công sẽ điền ngày khi ban hành chính thức. Không dùng ngày tạo file, ngày máy chủ, ngày quyết định trong Case hoặc Date của VBA để tự điền vào khoảng trống.
- Chỉ sửa bookmark nếu có quy tắc chứng minh không làm mất định dạng trống của template.

## Gate trước khi mở chức năng tạo
Các xác nhận này chưa đủ để mở API tạo Word QĐKT. Phải giải quyết quy tắc chọn quyết định mới nhất, phép biến đổi bookmark, nguồn phân loại và địa lý VKN; kiểm thử đa quyết định, điều chỉnh/thay thế, thiếu địa chỉ/phân loại, tên cơ quan và ngày để trống. Không có quyền tự tạo migration, viết lại dữ liệu hoặc deploy từ tài liệu này.

## Technical lifecycle audit — 28/10/2026

Phần này ghi nhận giới hạn kỹ thuật đã kiểm thử, không bổ sung quyết định nghiệp
vụ hoặc phê duyệt pháp lý mới.

- `require_unique_qdkt_source` là gate cũ cho đúng một source và projection plan
  khớp nguyên tử reference/date/raw. Projection không thay được source row.
- `require_latest_qdkt_reference` là gate riêng cho biểu mẫu tham chiếu: một root
  ordinal 1, hoặc toàn bộ chuỗi ordinal nguyên liên tục 1..N, ID duy nhất và mỗi
  successor `REPLACES` đúng predecessor ngay trước. Ngày không được lùi. Cùng ngày
  chỉ xác định được thứ tự khi quan hệ thay thế rõ; input order không có ý nghĩa.
  Không dùng MAX(id), MAX(date) hoặc chỉ lấy ordinal lớn nhất.
- Duplicate/missing ordinal, bool/float ordinal, ID hoặc atom sai kiểu, source
  không đầy đủ, root có predecessor, nhánh, vòng, link đứt, quan hệ không hỗ trợ
  đều bị chặn. AMENDS/SUPPLEMENTS chưa có policy owner-approved và không được
  chuyển thành REPLACES hoặc bỏ qua để lấy quyết định cũ.

### Nguồn persisted và ownership

Readers Case/Plan/Decision và team dùng scalar SELECT dưới `no_autoflush`, tránh
identity-map cache và pending ORM attributes. Query source join lại ownership
Case–Plan hoặc Case–Team tại thời điểm đọc source; không dùng một ID plan/team
đã sửa trong bộ nhớ để đọc nguồn Case khác. Không refresh/expire object đang
tracked; draft/pending changes của caller được giữ nguyên.
Readiness cũng đọc GxP scalar persisted cho template-contract check, không lấy
giá trị GxP đang sửa trong identity map.

Decision atoms từ reader mang `case_id` và `inspection_plan_id`. Kết quả pure
selector chưa có hai owner identities nên không đủ để compose Case bundle.
Bundle chặn decision/site/team khác Case hoặc decision thiếu Plan ownership.
Hai trường scope là provenance từ trusted internal reader, không phải reviewer
authentication; caller tự gán strings không chứng minh persistence/authorization.

`read_unique_qdkt_source_for_plan` chỉ nhận InspectionPlan persistent thuộc đúng
Session; pending ID/Case ownership bị chặn bằng
`INSPECTION_PLAN_IDENTITY_PENDING`, pending projection bằng
`DECISION_PROJECTION_MISMATCH`. Case readers đọc persisted scalars độc lập với
cache; không flush hoặc sửa object để làm khớp projection.

### Process A/B và legal issuance

- **Process A (`DRAFT_QDKT`)** chỉ đọc registered Site và proposed team. Regression
  SQL tracing chứng minh không query InspectionDecision hoặc InspectionPlan khi
  Case có 0, 1 hoặc 3 quyết định; không có issued reference/date trong source
  contract, không copy quyết định mới nhất và không chuyển Process B bundle
  thành draft source. Constructor không nhận nhãn process khác DRAFT_QDKT.
- **Process B** có thể nhận selected persisted decision atoms có lineage hợp lệ
  làm diagnostic source. Schema InspectionDecision hiện chỉ có reference/date/raw,
  ordinal và lineage, chưa có authenticated external issuance evidence. Vì vậy
  readiness luôn có `QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN` cho purpose lịch sử
  `EXISTING_APPROVED_DECISION_REFERENCE`; tên purpose không chứng minh approved.
  `QdKtDecisionAtoms.legal_issuance_verified` luôn false. Không phát hành văn bản.
- Readiness/source bundle/draft source luôn `ready_to_render=False`; constructor
  từ chối true bằng `QDKT_RENDER_ACTIVATION_FORBIDDEN`.

Blockers cũ vẫn giữ: `SOURCE_DECISION_INCOMPLETE`,
`SOURCE_DECISION_CARDINALITY_UNPROVEN`, `DECISION_IDENTITY_AMBIGUOUS`,
`DECISION_ORDER_UNPROVEN`, `DECISION_ROOT_INVALID`,
`DECISION_REPLACEMENT_LINEAGE_AMBIGUOUS`, `DECISION_PROJECTION_MISMATCH`.
Bundle thiếu/sai scope dùng `QDKT_CASE_SOURCE_IDENTITY_MISMATCH` hoặc
`QDKT_DECISION_PLAN_OWNERSHIP_MISSING`. Đây là data gates, không phải RBAC.

Regression ở `test_inspection_qd_kt_lifecycle_integrity.py` dùng SQLite disposable
và synthetic fixtures; fault injection cấm flush/commit/renderer/storage và SQL
ngoài SELECT. Không tuyên bố atomic snapshot xuyên nhiều query hoặc khả năng
nhìn xuyên transaction isolation: mỗi SELECT vẫn chịu snapshot của transaction.
Không có kiểm chứng production DB, external legal registry, NAS hay Word UAT.

Vẫn cần owner xác nhận lifecycle của điều chỉnh/bổ sung ngoài REPLACES, ý nghĩa
của các quan hệ thiếu/không nhất quán từ nguồn, và contract chứng minh ban hành
chính thức. Renderer legal choice vẫn UNDECIDED, timezone PARTIAL, Word UAT
NOT_EXECUTED; không kích hoạt renderer hoặc đóng #74/#144.
