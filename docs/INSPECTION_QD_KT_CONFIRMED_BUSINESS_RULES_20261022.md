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
