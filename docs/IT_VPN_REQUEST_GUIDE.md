# Hướng dẫn trao đổi với IT về VPN site-to-site

## Mục tiêu
Web GxP chạy trên Google Cloud; backend cần private access tới Synology để đọc/ghi tài liệu. NAS không được public ra Internet.

## Hỏi IT
- Router/firewall hãng/model gì?
- Ai quản trị?
- WAN có public IP không, static/dynamic, có CGNAT không?
- Subnet LAN chứa Synology?
- IP LAN tĩnh/reserved của Synology?
- Hỗ trợ IPsec/IKEv2/route-based VPN/BGP/static route không?
- Quy trình duyệt thay đổi network/firewall?
- Test/change window?

## Nội dung yêu cầu
“Cần kết nối mạng riêng giữa Google Cloud VPC và mạng nội bộ để backend GxP truy cập Synology. Không public SMB/DSM/WebDAV. Chỉ cấp route/firewall tối thiểu từ network/application GCP được chỉ định tới IP/port cần thiết của NAS.”

## Câu hỏi kỹ thuật
- Firewall tạo site-to-site IPsec với Google Cloud được không?
- Hỗ trợ IKEv2/route-based VPN?
- Có public IP cho VPN gateway?
- Có thể giới hạn source/destination/port?
- Có logging/monitoring tunnel?

Hiện tại Tailscale dùng cho development/PoC; application không được phụ thuộc Tailscale-specific address ở domain layer.
