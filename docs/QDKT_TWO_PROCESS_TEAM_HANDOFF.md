# QĐKT — hai quy trình độc lập và chuyển giao đoàn kiểm tra

Xác nhận nghiệp vụ ngày 24/10/2026:

1. **KHKT → dự thảo QĐKT DOCX:** người dùng lập kế hoạch và tạo dự thảo trên template. Dự thảo có thành phần đoàn dự kiến. Đây **không phải** quyết định đã phê duyệt, không có số hoặc ngày ban hành được khẳng định từ dự thảo.
2. **Sau khi QĐKT được phê duyệt:** người dùng nhập số QĐKT, ngày ban hành và thành phần đoàn kiểm tra chính thức vào Case. Quy trình nhập thông tin sau phê duyệt là một bước nghiệp vụ riêng, không được tự hoàn thành chỉ vì DOCX đã tạo.

**Cải tiến được giữ lại:** ở bước 2, hệ thống gợi ý đoàn từ bản dự thảo bước 1 để không phải gõ lại. Người dùng kiểm tra/chỉnh sửa và **xác nhận rõ ràng** đoàn chính thức. Nếu danh sách, thứ tự, Case, draft ID hoặc revision thay đổi thì không tự nhận roster cũ là chính thức. Khi roster chỉnh sửa, lưu phiên bản/căn cứ và yêu cầu xác nhận lại; không sửa ngược vào file dự thảo hay hồ sơ lịch sử.

## Ranh giới nguồn dữ liệu

- Thông tin **khởi tạo Case** đến từ dữ liệu người dùng nhập, hoặc kế thừa có kiểm soát từ Case gốc cho hồ sơ Tái/phù hợp. KHKT không cấp dữ liệu khởi tạo Case.
- KHKT là nguồn của **quy trình lập dự thảo QĐKT**, không tự biến nội dung KHKT thành dữ liệu chuẩn của Case sau phê duyệt.
- Cần phân biệt dữ liệu **dự kiến**, **đã xác nhận sau phê duyệt**, và **đã ghi nhận trong quyết định**; không suy ngược trạng thái pháp lý từ một bản DOCX.
- Legacy mapping (bao gồm Case↔db.ktra) chỉ là audit lịch sử, **không phải** dependency để mở tạo Case, dự thảo hoặc xác nhận QĐKT hiện đại.
- Quy tắc 1 Case = 1 Site = 1 GMP certificate tiếp tục áp dụng cho hồ sơ mới; ngoại lệ lịch sử giữ nguyên.

## Phạm vi mã ở phiên này

`inspection_qd_kt_team_handoff.py` là hợp đồng **thuần dữ liệu, không ghi DB** cho chuyển giao team từ draft sang thông tin ban hành: kiểm tra Case, draft, team, revision, roster, số và ngày quyết định và xác nhận người dùng. Nó **chưa** thay thế transaction service, API, RBAC, event/audit log hay trạng thái phê duyệt; những phần này phải tích hợp vào owner nghiệp vụ hiện hữu sau khi xác minh schema/workflow. `ready_to_render=False` vẫn là gate độc lập của renderer chưa hoàn thành.

Do not auto-copy team from KHKT directly into an issued decision, do not bypass user confirmation, and do not make the legacy workbook audit a modern Case workflow prerequisite.


## Lựa chọn đoàn kiểm tra ở bước ghi nhận ban hành

Hợp đồng `inspection_qd_kt_issued_team_choice.py` phân biệt ba con đường
dựa trên lựa chọn rõ ràng của người dùng:

- `DRAFT_UNCHANGED`: giữ nguyên đoàn dự kiến từ đúng draft, đúng Case,
  đúng phiên bản và xác nhận đoàn.
- `DRAFT_EDITED`: lấy đoàn dự kiến làm gợi ý, người dùng sửa danh sách hoặc
  thứ tự, xác nhận đoàn cuối **và** xác nhận riêng rằng thay đổi đã được rà soát.
  Việc sửa không ghi ngược vào draft.
- `USER_ENTERED`: nhập đoàn chính thức độc lập, không buộc có draft và
  không được gắn nhầm provenance của draft.

Cả ba trường hợp đều yêu cầu số quyết định, ngày ban hành và xác nhận người
dùng. Đây vẫn là validation thuần dữ liệu, chưa phải API/service ghi nhận quyết
định đã ban hành. Khi triển khai persistence phải có kiểm tra quyền, audit
event, optimistic locking và provenance, không suy ra phê duyệt từ DOCX.


## Bản chụp dữ liệu hiển thị của đoàn dự thảo (bước tiếp theo)

`inspection_qd_kt_team_snapshot_review.py` cung cấp hợp đồng read-only cho
`DraftTeamSnapshot`: `case_id`, `draft_id`, `document_version_id`,
`team_id`, `team_revision`, và danh sách thành viên có thứ tự với
`inspector_id`, `display_name`, `role`, `job_title` theo đúng dữ liệu
dự định hiển thị tại thời điểm tạo tài liệu. Đây là cấu trúc bất biến ở tầng
Python, **không phải** bằng chứng snapshot đã được lưu bất biến vào CSDL
hoặc đã gắn với DOCX binary trên storage.

`review_issued_team` so sánh danh sách sau phê duyệt với snapshot: thêm,
bỏ, đổi vị trí, tên, vai trò, chức danh đều được nhận biết. Khi chỉ đổi
chức danh mà IDs vẫn giữ nguyên, lựa chọn `DRAFT_UNCHANGED` bị chặn;
`DRAFT_EDITED` phải có `acknowledged_changes=True`. `USER_ENTERED`
không được gắn giả nguồn dự thảo. Không có thao tác ghi vào draft.

Lưu ý: `require_issued_team_choice(display_changed=False)` giữ tương thích
với các caller cũ chỉ có ID. Caller có snapshot đầy đủ phải dùng
`review_issued_team` để phát hiện thay đổi hiển thị; không nên cho phép
một đường ghi issued bypass so sánh này.

**Chưa triển khai:** ownership thực tế trong ORM; snapshot persistence bất
biến và digest DOCX; mapping kiểu hiển thị cho cả bốn template; authorization,
idempotency, optimistic locking, audit event, issued-decision transaction.
Không dùng hợp đồng này để mở `ready_to_render` hoặc xác nhận ban hành.


## Read-only current Case team endpoint

`GET /cases/{case_id}/documents/inspection-qd-kt/current-team`
yêu cầu `document.write` và trả đoàn đang lưu ở Case, không phải snapshot
DOCX hay danh sách chính thức theo từng InspectionDecision.

Response có `source_kind=CURRENT_CASE_TEAM`, `team_revision`,
danh sách `member_id`, `sort_order`, `role_code`, `display_name`,
`identity_kind`, các khóa identity; cùng hai cờ bắt buộc
`draft_snapshot_available=false` và `issued_team_confirmed=false`.

Nếu Case/team/member không rõ ownership, danh tính/vai trò/thứ tự không hợp lệ,
endpoint trả HTTP 409 theo source gate hiện có. Không tự đối chiếu profile
bên ngoài Case và không tự tạo bản chụp lịch sử từ team hiện tại.

**Giới hạn:** backend chưa có snapshot lưu bền vững theo
DocumentVersion, chưa có team chính thức riêng theo InspectionDecision.
Không dùng endpoint đọc này để xác nhận QĐKT, dựng DOCX, hay suy luận legal
approval. Frontend có thể hiển thị đoàn hiện tại cho người có quyền và phải
giữ riêng thông tin chính thức/snapshot trong UI cho đến khi có API hợp lệ.


## Read-only ownership audit for multiple QĐKT

`inspection_qd_kt_ownership_audit.inspect_case_qdkt_ownership` đọc
`InspectionPlan`, `InspectionDecision`, `InspectionTeam`, và các
`Document/DocumentVariant/DocumentVersion` được gắn vào Case.

Kết quả chỉ gồm định danh, số phiên bản và blocker kiến trúc, không trả
tên thành viên. Đây là **kiểm kê read-only**, không phải chứng cứ rằng
một version DOCX thuộc một InspectionDecision hoặc roster nào.

Kết quả luôn giữ ba blocker chưa được model chứng minh:

- `DECISION_SPECIFIC_TEAM_LINK_NOT_MODELED`
- `DRAFT_TEAM_SNAPSHOT_PERSISTENCE_NOT_MODELED`
- `DOCUMENT_VERSION_DECISION_LINK_NOT_MODELED`

`InspectionTeam.case_id` unique nhưng `InspectionDecision` có thể có
nhiều record theo `InspectionPlan`. Một `DocumentVersion` chỉ tham
chiếu `DocumentVariant`, do đó không được coi số lượng tài liệu/phiên
bản như bằng chứng đã gắn QĐKT ban hành với snapshot đoàn tương ứng.

Không chuyển audit này thành endpoint ban hành, migration hoặc mở
renderer khi chưa xác nhận nghiệp vụ về bản ký, điều chỉnh, thay thế,
idempotency và sự kiện audit. Không dùng audit thay cho kiểm chứng trên
dữ liệu thật.


## Xác minh nguồn DocumentVersion cho snapshot dự thảo

`require_qdkt_draft_version_binding` kiểm tra read-only đúng
`DocumentVersion → DocumentVariant → Document`, `Document.case_id`,
`family_code=INSPECTION_QD_KT`, storage locator và stored SHA-256.

Đây là bước xác minh rằng khóa version trong snapshot dự kiến trỏ đúng
tài liệu của Case. Không chứng minh roster đã render trong binary,
không tạo snapshot persistence, không xác nhận bản ký hoặc liên kết
`InspectionDecision` với phiên bản này. Các cờ
`confirmed_binary_roster_match=false` và
`approved_decision_link=false` cố định để tránh frontend suy luận sai.

Chưa nên mở API create/issue dựa vào bước kiểm chứng read-only này.
Cần owner transaction lưu snapshot bất biến và liên kết quyết định,
kiểm tra quyền, optimistic locking, idempotency và audit trail riêng.


## Additive draft roster persistence schema (0024)

Hai bảng rỗng `qdkt_draft_roster_snapshot` và
`qdkt_draft_roster_member` cung cấp ownership theo phiên bản:

- `snapshot.case_id` liên kết Case;
- `snapshot.document_version_id` unique tới đúng DocumentVersion;
- `snapshot.source_team_id` và `source_team_revision` pin nguồn;
- `snapshot.roster_sha256` là digest dự kiến của payload, **không** phải
  checksum DOCX;
- các member có `source_team_member_id`, `position`, tên, vai trò,
  chức danh chụp tại thời điểm dự thảo.

Migration 0024 chỉ tạo schema, không chuyển dữ liệu, không có endpoint
ghi snapshot và chưa đảm bảo bất biến tại tầng DB cho UPDATE/DELETE.
Rollback từ chối nếu có record, không âm thầm xóa dữ liệu lịch sử.

Trước khi bật writer cần: (1) transaction chụp từ nguồn được kiểm tra;
(2) checksum nhị phân DOCX + snapshot nội dung đã render; (3) quyền,
idempotency, concurrency, audit; (4) chính sách lưu không sửa/xóa;
(5) hợp đồng riêng official team theo từng InspectionDecision.

Không suy luận người dùng đã phê duyệt từ việc snapshot tồn tại.
