# Codex Start Prompt — GxP Web Migration

Bạn đang tiếp nhận dự án **GxP Web Management System**, thay thế dần phần mềm Excel/VBA hiện tại dùng để quản lý xử lý hồ sơ, kiểm tra và cấp chứng nhận GMP/GLP/GSP/GMP bao bì/GMP nước ngoài.

## Nguồn hiện trạng bắt buộc reverse-engineer
- `Danh sách Kiểm tra GPs.xlsb`
- `GPs.xlam`

Hai artifact là specification sống của hệ thống. Không được suy đoán chức năng chỉ từ tên sheet/macro. Phải đọc workbook structure, named ranges, VBA modules, UserForms, events, macro calls, filesystem operations, Word automation và dependency giữa `.xlsb` và `.xlam`.

### Findings đã biết
- Workbook có 32 sheet.
- Bảng lõi: `db.cty`, `db.cso`, `db.ktra`, `db.cc`, `db.dkkd`, `db.Tdoi`, `db.Tdoi2`.
- Quan hệ lõi: `db.cty -> db.cso -> db.ktra -> db.cc`.
- VBA nằm trong cả `.xlsb` và `.xlam`; workbook gọi macro `GPs.xlam` bằng `Application.Run`.
- `db.dkkd ID=385` là exact duplicate do user xác nhận; migration được giữ một record. Chỉ auto-dedup khi toàn bộ payload giống nhau; cùng ID nhưng payload khác phải fail và yêu cầu review.

## Kiến trúc đã chốt
### Google Cloud
- Cloud Run: web + backend API
- Cloud SQL for PostgreSQL: database nghiệp vụ
- Secret Manager: secrets
- Artifact Registry: images
- Cloud Logging/Monitoring: technical logs phù hợp

### Synology
- NAS hiện tại: Synology DS115j.
- Chỉ làm file storage.
- File nghiệp vụ phải nằm trên Synology; không persistent mirror sang Cloud Storage/server khác.
- Không chạy database/backend/container/document engine trên DS115j.

### Network
- Phase đầu: Tailscale.
- Thiết kế phải cho phép thay bằng site-to-site VPN sau này mà không sửa business logic.
- Tất cả file access qua `StorageService`; không để domain code phụ thuộc UNC path, Tailscale IP hay protocol.

### Inspector editing UX
Thanh tra viên đi hiện trường cần:
- Windows Explorer
- Microsoft Word desktop
- mở trực tiếp, sửa, Ctrl+S
- không download/edit/upload thủ công

PoC ban đầu: laptop dùng Tailscale để truy cập Synology qua private network; mapped drive/SMB nếu field test chứng minh đủ ổn định.

## Legacy file contract
Root dạng:
`\\synology\...\01 - Kiểm tra GPs\<YEAR>\`

Inspection folder ví dụ:
`120 Armephaco - Hà Nội (...) - (ID-103) - (KT-1376-GMP)`

Stable identity:
- `ID-103` = site ID
- `KT-1376-GMP` = inspection/case ID
- year = parent folder

Không dùng descriptive name/full folder name làm business key.

Folder resolver:
- 1 match -> RESOLVED
- 0 -> NOT_FOUND
- >1 -> AMBIGUOUS, fail closed

Không bulk rename/restructure legacy folders/files ở phase migration đầu.

## Legacy document prefixes
Đã quan sát:
- `3.` Kế hoạch kiểm tra
- `3.2.` Biên bản đánh giá GMP
- `4.` Báo cáo đánh giá GMP
- `4.2.` Biên bản KTGS
- `5.1.` CAPA lần 1
- `5.2.` CAPA lần 2
- `6.` Phiếu trình PCT
- `6.2.` biến thể liên quan
- `7.` Phiếu trình CT
- `8.` QĐ cấp CC
- `9.` Chứng chỉ GMP
- `10.` Quản lý rủi ro

Không hardcode registry chỉ từ danh sách này. Phải đối chiếu VBA + dữ liệu thật.

`.docx`, `.pdf`, `.scan.pdf`, `.signed.pdf` thường là rendition/variant của cùng logical document.

## Migration principles
- Không map 1 sheet -> 1 SQL table một cách máy móc.
- Xác định business entity thật.
- `db.ktra` là wide-row nhiều phase; target nên dùng workflow/event model.
- Preserve legacy IDs qua mapping.
- Tạo reconciliation reports.

Tối thiểu xem xét:
companies, sites, people/person roles, professional licenses, cases, inspections, inspection teams, case events, CAPA cycles, certificates, business eligibility, documents, renditions/versions, change history, users/roles, dictionaries/rules, audit logs.

## Reverse-engineering mapping
Cho mỗi VBA procedure:
`VBA function -> business purpose -> reads -> writes -> file ops -> target service/API`

Nhóm đã biết:
- Certificate: `AddCC_Cs`, `Input_DC_to_CC2`, `QD_CapCC`, `KT_CapCC`, `SelectCC`
- Case/history: `PrepareRecordForm`, `RefreshHistoryItem`, `RefreshListHistory`, `UpdateDotKtra`
- Planning: `Ke_Hoach`, `List_KH`, `List_KHKT`, `TaoQDKT_KHKT`
- Listing: `Ds_Co_so_Cty_GPs`, `Ds_Co_so_Cty_GPs2`, `Ds_cong_bo_GPs`
- Files: `LoadYearFolder*`, `LoadFolder*`, `LoadFiles*`, `Load_Data_Folders`, `Load_DDK_Folders`

Phải tìm toàn bộ FileSystemObject, Win32 file API, Shell/ShellExecute, Word.Application, Bookmarks, template logic, error handling và global mutable state.

## Target services
Backend ưu tiên Python/FastAPI.
Frontend TypeScript/React; chọn framework và ghi ADR trước khi scale implementation.

Domain/services:
- MasterDataService
- CaseService
- InspectionService
- CertificationService
- ChangeManagementService
- DocumentService
- StorageService
- AuditService
- Auth/RBAC

## Safety/integrity
Bắt buộc:
- RBAC
- audit trail
- transaction boundaries
- concurrency control
- SHA-256 file integrity
- version/rendition tracking
- no sensitive payload in technical logs
- no secrets in git
- no public SMB/DSM/WebDAV
- no hardcoded NAS path/IP in business layer
- path traversal protection
- fail closed on ambiguous folder resolution
- no destructive legacy migration without dry-run + report

## Cách làm việc bắt buộc
1. Đọc `AGENTS.md`.
2. Đọc docs liên quan.
3. Audit code/data thật.
4. Cập nhật ADR/design nếu assumption đổi.
5. Viết tests cùng implementation.
6. Chạy test/lint/typecheck.
7. Không tuyên bố hoàn thành nếu chưa validation.
8. Không sửa ngoài scope.
9. Không downstream-rescue lỗi owner-layer.
10. Một business rule có một owner rõ ràng.

Mỗi task báo:
- files changed
- decisions
- tests run/results
- migration impact
- security impact
- risks
- deferred work

## Nhiệm vụ đầu tiên — Phase 0
**Không bắt đầu bằng UI.**

### 0A Repository bootstrap
Tạo:
`backend/`, `frontend/`, `migrations/`, `tools/`, `tests/`, `docs/`, `docs/ADR/`.

### 0B Legacy reverse engineering
- workbook schema
- named ranges
- VBA modules/procedures
- UserForms/events
- dependency graph
- filesystem interactions
- Word/Excel automation
- implicit business rules
- file/folder naming contracts
- workflow/state machines

### 0C Deliverables trước business implementation
Tạo:
- `docs/LEGACY_SYSTEM_MAP.md`
- `docs/VBA_FUNCTION_MAP.md`
- `docs/DATA_DICTIONARY_LEGACY.md`
- `docs/FILE_STORAGE_CONTRACT.md`
- `docs/WORKFLOW_MODEL.md`
- `docs/TARGET_DATA_MODEL.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR/`
- `docs/MIGRATION_PLAN.md`
- automated legacy-data validation report

Sau Phase 0, dừng và trình bày findings/risks trước khi viết application chính.
