import { PublicLegalPage } from "../components/PublicLegalPage";

const sections = [
  {
    heading: "1. Introduction / Giới thiệu",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "GXP QLCL là một nền tảng hỗ trợ quản lý chất lượng, tuân thủ, tài liệu và các quy trình nghiệp vụ liên quan.",
          "Chính sách bảo mật này mô tả cách GXP QLCL thu thập, sử dụng, lưu trữ, bảo vệ và trong trường hợp cần thiết chia sẻ thông tin của người dùng khi sử dụng hệ thống, bao gồm thông tin được cung cấp thông qua chức năng đăng nhập bằng Google.",
          "Việc sử dụng GXP QLCL đồng nghĩa với việc người dùng xác nhận đã đọc và hiểu Chính sách bảo mật này.",
        ],
        en: [
          "GXP QLCL is a platform designed to support quality management, regulatory compliance, document management, and related operational workflows.",
          "This Privacy Policy explains how GXP QLCL collects, uses, stores, protects, and, where necessary, shares user information when users access or use the system, including information provided through Google Sign-In.",
          "By using GXP QLCL, users acknowledge that they have read and understood this Privacy Policy.",
        ],
      },
    ],
  },
  {
    heading: "2. Information We Collect / Thông tin chúng tôi thu thập",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["GXP QLCL có thể thu thập các nhóm thông tin sau:", "a. Thông tin tài khoản và xác thực"],
        en: [
          "GXP QLCL may collect the following categories of information:",
          "a. Account and authentication information",
        ],
      },
      {
        kind: "bullets" as const,
        vi: [
          "địa chỉ email;",
          "họ và tên;",
          "mã định danh tài khoản Google hoặc mã định danh người dùng tương đương;",
          "ảnh hồ sơ, nếu được Google cung cấp;",
          "thông tin cần thiết để xác minh phiên đăng nhập.",
        ],
        en: [
          "email address;",
          "full name;",
          "Google account identifier or equivalent user identifier;",
          "profile image, if provided by Google;",
          "information necessary to validate the authentication session.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: [
          "GXP QLCL không yêu cầu mật khẩu Google của người dùng và không có quyền truy cập vào mật khẩu Google.",
          "b. Thông tin sử dụng hệ thống",
        ],
        en: [
          "GXP QLCL does not request, receive, or have access to users' Google passwords.",
          "b. System usage information",
        ],
      },
      {
        kind: "bullets" as const,
        vi: [
          "thời điểm đăng nhập;",
          "lịch sử truy cập;",
          "hoạt động nghiệp vụ trong hệ thống;",
          "địa chỉ IP hoặc thông tin kết nối cần thiết cho việc bảo mật, giám sát và khắc phục sự cố;",
          "nhật ký hệ thống và nhật ký kiểm toán.",
        ],
        en: [
          "sign-in time;",
          "access history;",
          "actions performed within the system;",
          "IP address or other connection information required for security and monitoring;",
          "system and audit logs.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: [
          "c. Dữ liệu nghiệp vụ",
          "Tùy theo quyền hạn của từng người dùng, GXP QLCL có thể xử lý tài liệu, hồ sơ, dữ liệu chất lượng, dữ liệu tuân thủ và các thông tin nghiệp vụ do người dùng hoặc tổ chức của người dùng nhập vào hệ thống.",
        ],
        en: [
          "c. Business and operational data",
          "Depending on the user's permissions, GXP QLCL may process documents, records, quality-related data, compliance-related data, and other operational information submitted by users or their organizations.",
        ],
      },
    ],
  },
  {
    heading: "3. How We Use Google User Data / Cách chúng tôi sử dụng dữ liệu người dùng Google",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["GXP QLCL sử dụng dữ liệu nhận được từ Google chỉ cho các mục đích cần thiết để cung cấp và bảo vệ chức năng đăng nhập, bao gồm:"],
        en: ["GXP QLCL uses data received from Google only as necessary to provide and secure authentication functionality, including:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "xác thực danh tính người dùng;",
          "tạo hoặc liên kết tài khoản GXP QLCL với tài khoản Google của người dùng;",
          "xác định địa chỉ email và thông tin hồ sơ cơ bản;",
          "duy trì phiên đăng nhập;",
          "kiểm soát quyền truy cập;",
          "phòng chống truy cập trái phép;",
          "hỗ trợ kiểm toán và xử lý sự cố bảo mật.",
        ],
        en: [
          "authenticating the user's identity;",
          "creating or linking a GXP QLCL account with the user's Google account;",
          "identifying the user's email address and basic profile information;",
          "maintaining authenticated sessions;",
          "enforcing access controls;",
          "preventing unauthorized access;",
          "supporting security auditing and incident investigation.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: [
          "Trừ khi GXP QLCL công bố rõ ràng và người dùng cấp quyền bổ sung trong tương lai, GXP QLCL không sử dụng Google OAuth để đọc nội dung Gmail, Google Drive, Google Calendar hoặc các nội dung riêng tư khác trong tài khoản Google của người dùng.",
          "GXP QLCL không sử dụng Google user data cho mục đích quảng cáo hoặc bán dữ liệu người dùng.",
        ],
        en: [
          "Unless GXP QLCL explicitly discloses additional access and the user separately grants such permission in the future, GXP QLCL does not use Google OAuth to access the contents of Gmail, Google Drive, Google Calendar, or other private content in the user's Google account.",
          "GXP QLCL does not use Google user data for advertising purposes and does not sell Google user data.",
        ],
      },
    ],
  },
  {
    heading: "4. Legal and Operational Purposes / Mục đích sử dụng dữ liệu",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Thông tin người dùng có thể được sử dụng để:"],
        en: ["User information may be used to:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "cung cấp và duy trì dịch vụ;",
          "xác thực và phân quyền người dùng;",
          "vận hành các chức năng quản lý chất lượng và tuân thủ;",
          "bảo vệ tính bảo mật, toàn vẹn và khả dụng của hệ thống;",
          "phát hiện lỗi, gian lận hoặc truy cập trái phép;",
          "thực hiện kiểm toán;",
          "hỗ trợ kỹ thuật;",
          "đáp ứng nghĩa vụ pháp lý hoặc yêu cầu hợp pháp của cơ quan có thẩm quyền.",
        ],
        en: [
          "provide and maintain the service;",
          "authenticate users and manage authorization;",
          "operate quality-management and compliance workflows;",
          "protect the confidentiality, integrity, and availability of the system;",
          "detect errors, abuse, fraud, or unauthorized access;",
          "support auditing;",
          "provide technical support;",
          "comply with applicable legal obligations or lawful requests from competent authorities.",
        ],
      },
    ],
  },
  {
    heading: "5. Data Sharing / Chia sẻ dữ liệu",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "GXP QLCL không bán dữ liệu cá nhân của người dùng.",
          "Thông tin có thể được chia sẻ trong phạm vi cần thiết với:",
        ],
        en: [
          "GXP QLCL does not sell users' personal information.",
          "Information may be shared, where necessary, with:",
        ],
      },
      {
        kind: "bullets" as const,
        vi: [
          "quản trị viên hệ thống hoặc tổ chức có thẩm quyền quản lý tài khoản người dùng;",
          "nhà cung cấp hạ tầng, lưu trữ hoặc dịch vụ kỹ thuật cần thiết để vận hành hệ thống;",
          "cơ quan có thẩm quyền nếu pháp luật yêu cầu;",
          "các bên khác khi người dùng hoặc tổ chức có thẩm quyền đã cho phép.",
        ],
        en: [
          "authorized system administrators or organizations responsible for user account management;",
          "infrastructure, hosting, storage, or technical service providers required to operate the system;",
          "competent authorities where disclosure is required by law;",
          "other parties where the user or an authorized organization has provided appropriate authorization.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: ["Các nhà cung cấp dịch vụ chỉ được phép xử lý thông tin trong phạm vi cần thiết để cung cấp dịch vụ liên quan."],
        en: ["Service providers are permitted to process information only to the extent necessary to provide the relevant service."],
      },
    ],
  },
  {
    heading: "6. Data Storage and Security / Lưu trữ và bảo mật dữ liệu",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["GXP QLCL áp dụng các biện pháp kỹ thuật và tổ chức phù hợp nhằm bảo vệ dữ liệu, có thể bao gồm:"],
        en: ["GXP QLCL applies reasonable technical and organizational measures to protect information, which may include:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "xác thực người dùng;",
          "kiểm soát quyền truy cập;",
          "kết nối HTTPS;",
          "phân quyền theo vai trò;",
          "ghi nhật ký;",
          "sao lưu;",
          "giám sát hệ thống;",
          "giới hạn quyền truy cập cơ sở dữ liệu;",
          "các biện pháp bảo mật hạ tầng phù hợp.",
        ],
        en: [
          "user authentication;",
          "access controls;",
          "HTTPS-encrypted connections;",
          "role-based authorization;",
          "logging;",
          "backups;",
          "system monitoring;",
          "restricted database access;",
          "appropriate infrastructure security controls.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: ["Không có hệ thống điện tử nào có thể đảm bảo an toàn tuyệt đối. Tuy nhiên, GXP QLCL thực hiện các biện pháp hợp lý để giảm thiểu nguy cơ truy cập, thay đổi, tiết lộ hoặc phá hủy dữ liệu trái phép."],
        en: ["No electronic system can guarantee absolute security. However, GXP QLCL takes reasonable measures to reduce the risk of unauthorized access, alteration, disclosure, or destruction of data."],
      },
    ],
  },
  {
    heading: "7. Data Retention / Thời gian lưu trữ",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Dữ liệu được lưu giữ trong thời gian cần thiết để:"],
        en: ["Data is retained for as long as necessary to:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "cung cấp dịch vụ;",
          "duy trì hồ sơ kiểm toán;",
          "bảo đảm an ninh hệ thống;",
          "thực hiện nghĩa vụ nghiệp vụ;",
          "tuân thủ các yêu cầu pháp luật hoặc quy định áp dụng.",
        ],
        en: [
          "provide the service;",
          "maintain audit records;",
          "protect system security;",
          "satisfy operational requirements;",
          "comply with applicable legal or regulatory obligations.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: ["Khi dữ liệu không còn cần thiết, dữ liệu có thể được xóa, ẩn danh hoặc lưu trữ theo chính sách quản trị dữ liệu phù hợp."],
        en: ["When information is no longer required, it may be deleted, anonymized, or archived in accordance with applicable data-governance policies."],
      },
    ],
  },
  {
    heading: "8. User Rights and Data Deletion / Quyền của người dùng và yêu cầu xóa dữ liệu",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Tùy theo pháp luật áp dụng và quyền quản trị của tổ chức, người dùng có thể yêu cầu:"],
        en: ["Subject to applicable law and organizational administration policies, users may request to:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "xem thông tin cá nhân đang được lưu giữ;",
          "sửa thông tin không chính xác;",
          "yêu cầu xóa tài khoản hoặc dữ liệu cá nhân;",
          "yêu cầu hạn chế hoặc chấm dứt việc xử lý dữ liệu trong trường hợp phù hợp.",
        ],
        en: [
          "access personal information held about them;",
          "correct inaccurate information;",
          "request deletion of their account or personal information;",
          "request restriction or termination of certain processing activities where applicable.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: [
          "Đối với tài khoản được quản lý bởi một tổ chức, một số yêu cầu có thể phải được thực hiện thông qua quản trị viên của tổ chức đó.",
          "Người dùng cũng có thể thu hồi quyền truy cập Google OAuth của GXP QLCL trong phần quản lý ứng dụng được kết nối của tài khoản Google.",
        ],
        en: [
          "For accounts managed by an organization, some requests may need to be handled through the organization's authorized administrator.",
          "Users may also revoke GXP QLCL's Google OAuth access through the connected-app settings of their Google Account.",
        ],
      },
    ],
  },
  {
    heading: "9. Cookies and Sessions / Cookie và phiên đăng nhập",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["GXP QLCL có thể sử dụng cookie hoặc cơ chế lưu trữ phiên cần thiết cho:"],
        en: ["GXP QLCL may use cookies or similar session mechanisms where necessary to:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "duy trì trạng thái đăng nhập;",
          "bảo mật phiên;",
          "chống giả mạo yêu cầu;",
          "lưu các thiết lập kỹ thuật cần thiết.",
        ],
        en: [
          "maintain sign-in state;",
          "secure user sessions;",
          "prevent request forgery;",
          "store necessary technical settings.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: ["Các cookie thiết yếu này không được sử dụng để xây dựng hồ sơ quảng cáo."],
        en: ["These essential cookies are not used to build advertising profiles."],
      },
    ],
  },
  {
    heading: "10. Third-Party Services / Dịch vụ của bên thứ ba",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "GXP QLCL có thể sử dụng các dịch vụ hạ tầng hoặc xác thực của bên thứ ba, bao gồm Google Cloud và Google Identity Services.",
          "Việc sử dụng tài khoản Google cũng chịu sự điều chỉnh bởi các điều khoản và chính sách riêng của Google.",
        ],
        en: [
          "GXP QLCL may use third-party infrastructure or authentication services, including Google Cloud and Google Identity Services.",
          "Use of a Google Account is also subject to Google's own terms and privacy policies.",
        ],
      },
    ],
  },
  {
    heading: "11. Children's Privacy / Quyền riêng tư của trẻ em",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["GXP QLCL được thiết kế cho mục đích nghiệp vụ và không hướng tới trẻ em."],
        en: ["GXP QLCL is designed for professional and organizational use and is not directed toward children."],
      },
    ],
  },
  {
    heading: "12. Changes to This Policy / Thay đổi chính sách",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "Chính sách này có thể được cập nhật khi chức năng của hệ thống, yêu cầu pháp luật hoặc cách thức xử lý dữ liệu thay đổi.",
          "Ngày cập nhật gần nhất sẽ được hiển thị ở đầu trang.",
        ],
        en: [
          "This Privacy Policy may be updated when system functionality, legal requirements, or data-processing practices change.",
          "The latest revision date will be displayed at the top of this page.",
        ],
      },
    ],
  },
  {
    heading: "13. Contact / Liên hệ",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Nếu có câu hỏi về Chính sách bảo mật hoặc việc xử lý dữ liệu tại GXP QLCL, vui lòng liên hệ thông qua địa chỉ email hỗ trợ được công bố trên ứng dụng hoặc trang chủ chính thức của GXP QLCL."],
        en: ["For questions about this Privacy Policy or GXP QLCL's data-handling practices, please contact the support email published in the application or on the official GXP QLCL website."],
      },
    ],
  },
] as const;

export function PrivacyPage() {
  return (
    <PublicLegalPage
      title="GXP QLCL Privacy Policy"
      subtitle="Chính sách bảo mật GXP QLCL"
      effectiveDate="30 August 2026 / 30/08/2026"
      updatedDate="30 August 2026 / 30/08/2026"
      sections={sections}
    />
  );
}
