import { PublicLegalPage } from "../components/PublicLegalPage";

const sections = [
  {
    heading: "1. Acceptance of Terms / Chấp nhận điều khoản",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "Bằng việc truy cập hoặc sử dụng GXP QLCL, người dùng đồng ý tuân thủ Điều khoản sử dụng này cùng các chính sách, quy định nội bộ và yêu cầu pháp luật có liên quan.",
          "Nếu người dùng không đồng ý với các điều khoản này, người dùng không nên tiếp tục sử dụng hệ thống.",
        ],
        en: [
          "By accessing or using GXP QLCL, users agree to comply with these Terms of Service, together with applicable policies, organizational rules, and legal requirements.",
          "If a user does not agree to these terms, the user should not continue using the system.",
        ],
      },
    ],
  },
  {
    heading: "2. Purpose of the Service / Mục đích của dịch vụ",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "GXP QLCL là hệ thống hỗ trợ các hoạt động liên quan đến quản lý chất lượng, tuân thủ, hồ sơ, tài liệu, dữ liệu và các quy trình nghiệp vụ liên quan.",
          "Các chức năng cụ thể có thể thay đổi theo phiên bản hệ thống và quyền hạn được cấp cho từng người dùng.",
        ],
        en: [
          "GXP QLCL is a system supporting quality management, compliance, records, documents, data, and related operational workflows.",
          "Specific functionality may vary depending on the system version and the permissions assigned to each user.",
        ],
      },
    ],
  },
  {
    heading: "3. User Accounts / Tài khoản người dùng",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Người dùng có trách nhiệm:"],
        en: ["Users are responsible for:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "sử dụng đúng tài khoản được cấp hoặc tài khoản cá nhân đã được ủy quyền;",
          "bảo vệ thông tin xác thực của mình;",
          "không chia sẻ quyền truy cập trái phép;",
          "thông báo kịp thời nếu phát hiện tài khoản bị xâm nhập hoặc sử dụng bất thường.",
        ],
        en: [
          "using only accounts that are properly assigned or authorized;",
          "protecting their authentication credentials;",
          "not sharing access with unauthorized persons;",
          "promptly reporting suspected account compromise or unusual activity.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: ["Đăng nhập bằng Google không cho phép GXP QLCL truy cập mật khẩu Google của người dùng."],
        en: ["Google Sign-In does not provide GXP QLCL with access to the user's Google password."],
      },
    ],
  },
  {
    heading: "4. Authorized Use / Sử dụng được phép",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "Người dùng chỉ được sử dụng GXP QLCL cho các mục đích hợp pháp, được phép và phù hợp với vai trò được cấp.",
          "Người dùng không được:",
        ],
        en: [
          "Users may use GXP QLCL only for lawful, authorized purposes consistent with their assigned roles.",
          "Users must not:",
        ],
      },
      {
        kind: "bullets" as const,
        vi: [
          "cố gắng truy cập dữ liệu ngoài phạm vi quyền hạn;",
          "vượt qua cơ chế bảo mật;",
          "phát tán mã độc;",
          "can thiệp trái phép vào hệ thống;",
          "khai thác lỗ hổng;",
          "giả mạo người dùng khác;",
          "sử dụng hệ thống để thực hiện hành vi trái pháp luật;",
          "cố ý làm sai lệch, phá hủy hoặc xóa dữ liệu không được phép.",
        ],
        en: [
          "attempt to access data beyond their authorization;",
          "bypass security controls;",
          "distribute malicious code;",
          "interfere with the system without authorization;",
          "exploit vulnerabilities;",
          "impersonate another user;",
          "use the system for unlawful activities;",
          "intentionally alter, destroy, or delete data without authorization.",
        ],
      },
    ],
  },
  {
    heading: "5. User-Provided Data / Dữ liệu do người dùng cung cấp",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "Người dùng chịu trách nhiệm đối với dữ liệu, tài liệu và thông tin do mình nhập, tải lên hoặc xử lý trong GXP QLCL.",
          "Người dùng chỉ nên tải lên dữ liệu mà mình có quyền hợp pháp để xử lý.",
        ],
        en: [
          "Users are responsible for the data, documents, and information they submit, upload, or process through GXP QLCL.",
          "Users should only upload or process information for which they have lawful authorization.",
        ],
      },
    ],
  },
  {
    heading: "6. System Availability / Tính sẵn sàng của hệ thống",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "GXP QLCL được vận hành với mục tiêu duy trì tính ổn định và khả dụng hợp lý.",
          "Tuy nhiên, hệ thống có thể tạm ngừng hoặc bị gián đoạn do:",
        ],
        en: [
          "GXP QLCL is operated with the goal of maintaining reasonable stability and availability.",
          "However, the service may be temporarily unavailable or interrupted due to:",
        ],
      },
      {
        kind: "bullets" as const,
        vi: [
          "bảo trì;",
          "nâng cấp;",
          "sự cố kỹ thuật;",
          "sự cố hạ tầng;",
          "yêu cầu bảo mật;",
          "nguyên nhân ngoài khả năng kiểm soát hợp lý.",
        ],
        en: [
          "maintenance;",
          "upgrades;",
          "technical incidents;",
          "infrastructure issues;",
          "security requirements;",
          "circumstances outside reasonable control.",
        ],
      },
    ],
  },
  {
    heading: "7. Security and Audit / Bảo mật và kiểm toán",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Hoạt động sử dụng GXP QLCL có thể được ghi nhật ký nhằm:"],
        en: ["Use of GXP QLCL may be logged for purposes including:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "đảm bảo an ninh;",
          "phát hiện truy cập trái phép;",
          "khắc phục sự cố;",
          "bảo vệ tính toàn vẹn dữ liệu;",
          "phục vụ kiểm toán;",
          "đáp ứng nghĩa vụ pháp lý hoặc quy định.",
        ],
        en: [
          "maintaining security;",
          "detecting unauthorized access;",
          "troubleshooting;",
          "protecting data integrity;",
          "supporting audits;",
          "complying with applicable legal or regulatory obligations.",
        ],
      },
    ],
  },
  {
    heading: "8. Google Authentication / Xác thực bằng Google",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "GXP QLCL có thể cho phép người dùng đăng nhập bằng Google.",
          "Khi sử dụng chức năng này:",
        ],
        en: [
          "GXP QLCL may allow users to sign in with Google.",
          "When using this functionality:",
        ],
      },
      {
        kind: "bullets" as const,
        vi: [
          "người dùng cho phép Google cung cấp cho GXP QLCL các thông tin được hiển thị trên màn hình cấp quyền;",
          "GXP QLCL chỉ sử dụng dữ liệu Google theo Chính sách bảo mật đã công bố;",
          "người dùng có thể thu hồi quyền truy cập thông qua phần quản lý tài khoản Google.",
        ],
        en: [
          "the user authorizes Google to provide GXP QLCL with the information displayed in the applicable authorization flow;",
          "GXP QLCL uses Google user data only as described in its published Privacy Policy;",
          "users may revoke access through their Google Account settings.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: ["Việc sử dụng các dịch vụ Google cũng chịu sự điều chỉnh bởi các điều khoản và chính sách của Google."],
        en: ["Use of Google services is also subject to Google's applicable terms and policies."],
      },
    ],
  },
  {
    heading: "9. Intellectual Property / Quyền sở hữu trí tuệ",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "Trừ khi có quy định khác, phần mềm, giao diện, thiết kế, mã nguồn, tài liệu hệ thống và các thành phần do GXP QLCL phát triển được bảo hộ theo quy định pháp luật hiện hành.",
          "Việc sử dụng hệ thống không chuyển giao quyền sở hữu trí tuệ cho người dùng.",
        ],
        en: [
          "Unless otherwise stated, the software, interface, design, source code, system documentation, and other components developed for GXP QLCL are protected under applicable intellectual-property laws.",
          "Use of the service does not transfer ownership of intellectual property to users.",
        ],
      },
    ],
  },
  {
    heading: "10. Suspension or Termination / Tạm ngừng hoặc chấm dứt quyền truy cập",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Quyền truy cập của người dùng có thể bị hạn chế, tạm ngừng hoặc chấm dứt khi:"],
        en: ["A user's access may be restricted, suspended, or terminated where:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "người dùng vi phạm điều khoản này;",
          "có nguy cơ bảo mật;",
          "tài khoản không còn được tổ chức cho phép;",
          "có yêu cầu từ quản trị viên có thẩm quyền;",
          "pháp luật hoặc quy định yêu cầu.",
        ],
        en: [
          "the user violates these Terms;",
          "a security risk exists;",
          "the user's organization no longer authorizes access;",
          "an authorized administrator requests termination;",
          "applicable law or regulation requires it.",
        ],
      },
    ],
  },
  {
    heading: "11. Disclaimer / Miễn trừ trách nhiệm",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "GXP QLCL là công cụ hỗ trợ nghiệp vụ và quản lý thông tin.",
          "Trừ khi được quy định rõ ràng bằng văn bản, thông tin do hệ thống xử lý hoặc hiển thị không thay thế cho:",
        ],
        en: [
          "GXP QLCL is an operational and information-management support tool.",
          "Unless expressly stated otherwise in writing, information processed or displayed by the system does not replace:",
        ],
      },
      {
        kind: "bullets" as const,
        vi: [
          "đánh giá chuyên môn;",
          "quyết định pháp lý;",
          "quyết định quản lý;",
          "kết luận của cơ quan có thẩm quyền.",
        ],
        en: [
          "professional judgment;",
          "legal decisions;",
          "management decisions;",
          "determinations by competent authorities.",
        ],
      },
      {
        kind: "paragraphs" as const,
        vi: ["Người dùng có trách nhiệm xem xét và xác minh thông tin trước khi sử dụng cho các quyết định quan trọng."],
        en: ["Users remain responsible for reviewing and validating information before relying on it for material decisions."],
      },
    ],
  },
  {
    heading: "12. Limitation of Liability / Giới hạn trách nhiệm",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Trong phạm vi pháp luật cho phép, GXP QLCL và các bên vận hành không chịu trách nhiệm đối với thiệt hại gián tiếp hoặc hậu quả phát sinh từ:"],
        en: ["To the extent permitted by applicable law, GXP QLCL and its operators are not liable for indirect or consequential losses arising from:"],
      },
      {
        kind: "bullets" as const,
        vi: [
          "việc sử dụng sai hệ thống;",
          "dữ liệu do người dùng nhập sai;",
          "truy cập trái phép do lỗi của người dùng;",
          "gián đoạn dịch vụ ngoài khả năng kiểm soát hợp lý;",
          "việc sử dụng thông tin của hệ thống ngoài phạm vi mục đích được thiết kế.",
        ],
        en: [
          "misuse of the system;",
          "inaccurate data entered by users;",
          "unauthorized access resulting from user negligence;",
          "service interruptions outside reasonable control;",
          "use of system information beyond its intended purpose.",
        ],
      },
    ],
  },
  {
    heading: "13. Changes to the Service or Terms / Thay đổi dịch vụ hoặc điều khoản",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: [
          "GXP QLCL có thể cập nhật chức năng hoặc Điều khoản sử dụng này khi cần thiết.",
          "Ngày cập nhật gần nhất sẽ được công bố trên trang này.",
        ],
        en: [
          "GXP QLCL may update its functionality or these Terms of Service when necessary.",
          "The most recent revision date will be published on this page.",
        ],
      },
    ],
  },
  {
    heading: "14. Governing Requirements / Quy định áp dụng",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Việc sử dụng GXP QLCL phải tuân thủ pháp luật hiện hành, các quy định liên quan và chính sách quản trị nội bộ áp dụng cho tổ chức sử dụng hệ thống."],
        en: ["Use of GXP QLCL must comply with applicable laws, relevant regulations, and the internal governance policies applicable to the organization using the system."],
      },
    ],
  },
  {
    heading: "15. Contact / Liên hệ",
    blocks: [
      {
        kind: "paragraphs" as const,
        vi: ["Các câu hỏi liên quan đến Điều khoản sử dụng có thể được gửi tới địa chỉ email hỗ trợ được công bố trên trang chủ hoặc trong hệ thống GXP QLCL."],
        en: ["Questions regarding these Terms of Service may be directed to the support email published on the GXP QLCL homepage or within the application."],
      },
    ],
  },
] as const;

export function TermsPage() {
  return (
    <PublicLegalPage
      title="GXP QLCL Terms of Service"
      subtitle="Điều khoản sử dụng GXP QLCL"
      effectiveDate="30 August 2026 / 30/08/2026"
      updatedDate="30 August 2026 / 30/08/2026"
      sections={sections}
    />
  );
}
