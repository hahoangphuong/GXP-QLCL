# QĐKT: hai quy trình legacy độc lập và điểm nối có xác nhận

## 1. Quy trình dự thảo

Từ **Kế hoạch kiểm tra (KHKT)**, người dùng tạo **dự thảo QĐKT ở dạng DOCX** bằng template. Dự thảo chưa có hiệu lực ban hành, chưa tạo số quyết định chính thức hay ngày ban hành. Danh sách thành viên dự kiến trong dự thảo là một **đề xuất có nguồn gốc và thứ tự**, không mặc nhiên là đoàn đã được phê duyệt.

## 2. Quy trình sau phê duyệt

Sau khi QĐKT được phê duyệt, người dùng ghi nhận **số QĐKT, ngày ban hành và thành phần đoàn kiểm tra**. Quy trình này vẫn độc lập với việc tạo bản dự thảo. Người dùng có thể:
- xác nhận tái sử dụng nguyên danh sách dự kiến từ dự thảo cùng Case để tránh nhập lại; hoặc
- nhập/chỉnh sửa đoàn chính thức nếu nội dung đã thay đổi trong quá trình phê duyệt.

Không được lấy số/ngày quyết định đã ban hành từ một bản DOCX dự thảo; không được tự động phê duyệt hay ghi quyết định chỉ vì bản dự thảo đã được tạo. Tái sử dụng phải có **xác nhận rõ ràng của người dùng**. Mọi khác biệt thành viên/thứ tự/vai trò yêu cầu đường nhập chính thức, không âm thầm biến đổi danh sách đề xuất.

## 3. Ranh giới Case và KHKT

Thông tin khởi tạo Case do người dùng nhập hoặc kế thừa hợp lệ từ Case gốc (ví dụ loại hồ sơ Tái). **Không lấy thông tin khởi tạo Case từ KHKT**. KHKT là nguồn phục vụ tạo dự thảo QĐKT; không phải nguồn tự động điền hay sửa Case. Đoàn trong dự thảo có thể được đề xuất cho bước nhập sau phê duyệt nhưng không tự động ghi vào Case khi chưa xác nhận.

## 4. Phạm vi mã hiện tại

`backend/app/document/inspection_qd_kt_draft_approval_handoff.py` chỉ cung cấp hai hợp đồng kiểm tra dữ liệu thuần:
- `propose_qdkt_draft_team`: danh sách thành viên dự kiến, gắn danh tính Case/dự thảo;
- `validate_approved_qdkt_input`: số, ngày, đội ngũ đã xác nhận và lựa chọn giữ nguyên đề xuất hay nhập thủ công.

Đây **không** phải API ghi dữ liệu hay trạng thái phê duyệt; chưa tích hợp UI, transaction/database, storage hoặc DOCX renderer. Phần ghi nhận thật sau này phải có quyền hạn, idempotency, kiểm soát thay đổi, provenance và audit event ở owner bước phê duyệt; cần ngăn nhập thông tin quyết định đã ban hành bằng một hành động tạo dự thảo.

Giữ nguyên các blocker template bookmark/renderer hiện có và không thay đổi dữ liệu lịch sử.
