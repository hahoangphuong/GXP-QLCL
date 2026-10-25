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
