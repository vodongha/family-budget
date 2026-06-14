"""Legal pages — a public, no-auth privacy policy served as HTML.

Google Play requires a publicly reachable privacy-policy URL (for the store
listing and the Data Safety form) that is also accessible from inside the app.
This route is that single source of truth, rendered bilingually (vi/en) via a
`?lang=` query parameter.
"""

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["legal"])

# Keep these in one place so the page and any future doc stay consistent.
APP_NAME = "Family Budget"
DEVELOPER = "Võ Đông Hà"
CONTACT_EMAIL = "vodongha@hotmail.com"
WEBSITE = "https://vodongha.id.vn"
EFFECTIVE_DATE = "2026-06-14"

# Each language is a (title, intro, [(section_heading, section_html), ...]) bundle.
# Section bodies are small HTML fragments (paragraphs / lists) so the content
# reads like a real policy, not a flat wall of text.
_CONTENT: dict[str, dict[str, object]] = {
    "vi": {
        "lang_label": "English",
        "lang_switch": "?lang=en",
        "title": "Chính sách quyền riêng tư",
        "updated": f"Cập nhật lần cuối: {EFFECTIVE_DATE}",
        "intro": (
            f"Chính sách này mô tả cách ứng dụng <strong>{APP_NAME}</strong> "
            f"(do {DEVELOPER} phát triển) thu thập, sử dụng và bảo vệ thông tin "
            "của bạn. Bằng việc sử dụng ứng dụng, bạn đồng ý với chính sách này."
        ),
        "sections": [
            (
                "1. Thông tin chúng tôi thu thập",
                "<ul>"
                "<li><strong>Thông tin tài khoản:</strong> email, tên hiển thị và "
                "số điện thoại (tùy chọn) bạn cung cấp khi đăng ký hoặc cập nhật hồ sơ.</li>"
                "<li><strong>Thông tin đăng nhập:</strong> mật khẩu được lưu dưới dạng "
                "băm (hash), không bao giờ ở dạng văn bản thuần. Nếu đăng nhập bằng "
                "Google, chúng tôi lưu mã định danh tài khoản Google (sub) để liên kết.</li>"
                "<li><strong>Dữ liệu bạn nhập:</strong> ví, giao dịch thu/chi, danh mục, "
                "ngân sách và ghi chú do bạn tạo trong ứng dụng.</li>"
                "<li><strong>Thông tin gia đình:</strong> khi bạn tham gia một nhóm gia "
                "đình, các thành viên trong nhóm thấy dữ liệu dùng chung của gia đình đó.</li>"
                "</ul>"
                "<p>Chúng tôi <strong>không</strong> thu thập vị trí, danh bạ, hay dữ liệu "
                "quảng cáo, và không sử dụng trình theo dõi của bên thứ ba.</p>",
            ),
            (
                "2. Cách chúng tôi sử dụng thông tin",
                "<ul>"
                "<li>Cung cấp chức năng cốt lõi: ghi nhận thu chi, tính số dư, thống kê "
                "và chia sẻ ngân sách trong gia đình.</li>"
                "<li>Xác thực và bảo mật tài khoản của bạn.</li>"
                "<li>Vận hành, duy trì và cải thiện ứng dụng.</li>"
                "</ul>"
                "<p>Chúng tôi <strong>không bán</strong> dữ liệu cá nhân của bạn và không "
                "dùng nó cho quảng cáo.</p>",
            ),
            (
                "3. Chia sẻ dữ liệu",
                "<p>Dữ liệu của bạn chỉ được chia sẻ trong các trường hợp sau:</p>"
                "<ul>"
                "<li><strong>Trong gia đình của bạn:</strong> dữ liệu dùng chung (ví gia "
                "đình, giao dịch, danh mục, ngân sách) hiển thị cho các thành viên cùng "
                "gia đình. Ví <em>cá nhân</em> chỉ riêng bạn thấy, kể cả chủ gia đình.</li>"
                "<li><strong>Nhà cung cấp hạ tầng:</strong> dữ liệu được lưu trên dịch vụ "
                "cơ sở dữ liệu đám mây (Oracle Cloud) để vận hành ứng dụng.</li>"
                "<li><strong>Yêu cầu pháp lý:</strong> khi pháp luật bắt buộc.</li>"
                "</ul>",
            ),
            (
                "4. Lưu trữ và xóa dữ liệu",
                "<p>Bạn có thể <strong>xóa tài khoản ngay trong ứng dụng</strong> "
                "(Hồ sơ → Xóa tài khoản). Khi xóa:</p>"
                "<ul>"
                "<li>Tài khoản bị vô hiệu hóa ngay lập tức (không thể đăng nhập).</li>"
                "<li>Dữ liệu được xóa vĩnh viễn sau thời gian lưu giữ <strong>30 ngày</strong>. "
                "Nếu bạn là thành viên trong một gia đình còn hoạt động, thông tin cá nhân "
                "của bạn sẽ được ẩn danh để giữ tính toàn vẹn của dữ liệu chung.</li>"
                "</ul>"
                f"<p>Bạn cũng có thể yêu cầu xóa dữ liệu qua email "
                f"<a href=\"mailto:{CONTACT_EMAIL}\">{CONTACT_EMAIL}</a>.</p>",
            ),
            (
                "5. Bảo mật",
                "<p>Kết nối tới máy chủ được mã hóa; mật khẩu được băm bằng bcrypt; "
                "truy cập dữ liệu luôn giới hạn theo phạm vi gia đình của bạn. Tuy nhiên, "
                "không có hệ thống nào an toàn tuyệt đối — hãy giữ kín mật khẩu của bạn.</p>",
            ),
            (
                "6. Trẻ em",
                "<p>Ứng dụng không hướng tới trẻ em dưới 13 tuổi và chúng tôi không cố ý "
                "thu thập dữ liệu của trẻ em.</p>",
            ),
            (
                "7. Quyền của bạn",
                "<p>Bạn có quyền truy cập, chỉnh sửa và xóa dữ liệu của mình trực tiếp "
                "trong ứng dụng, hoặc liên hệ với chúng tôi để được hỗ trợ.</p>",
            ),
            (
                "8. Thay đổi chính sách",
                "<p>Chúng tôi có thể cập nhật chính sách này; thay đổi sẽ được đăng tại "
                "trang này kèm ngày cập nhật mới.</p>",
            ),
            (
                "9. Liên hệ",
                f"<p>Mọi câu hỏi xin gửi tới <a href=\"mailto:{CONTACT_EMAIL}\">"
                f"{CONTACT_EMAIL}</a> &middot; <a href=\"{WEBSITE}\">{WEBSITE}</a>.</p>",
            ),
        ],
    },
    "en": {
        "lang_label": "Tiếng Việt",
        "lang_switch": "?lang=vi",
        "title": "Privacy Policy",
        "updated": f"Last updated: {EFFECTIVE_DATE}",
        "intro": (
            f"This policy explains how the <strong>{APP_NAME}</strong> app "
            f"(developed by {DEVELOPER}) collects, uses, and protects your "
            "information. By using the app, you agree to this policy."
        ),
        "sections": [
            (
                "1. Information we collect",
                "<ul>"
                "<li><strong>Account information:</strong> your email, display name, and "
                "optional phone number, provided when you register or edit your profile.</li>"
                "<li><strong>Sign-in information:</strong> your password is stored hashed, "
                "never in plain text. If you sign in with Google, we store your Google "
                "account identifier (sub) to link the account.</li>"
                "<li><strong>Data you enter:</strong> wallets, income/expense transactions, "
                "categories, budgets, and notes you create in the app.</li>"
                "<li><strong>Family information:</strong> when you join a family group, its "
                "members can see that family's shared data.</li>"
                "</ul>"
                "<p>We do <strong>not</strong> collect location, contacts, or advertising "
                "data, and we use no third-party trackers.</p>",
            ),
            (
                "2. How we use information",
                "<ul>"
                "<li>To provide core features: recording income/expense, computing balances, "
                "statistics, and shared family budgeting.</li>"
                "<li>To authenticate and secure your account.</li>"
                "<li>To operate, maintain, and improve the app.</li>"
                "</ul>"
                "<p>We do <strong>not sell</strong> your personal data and do not use it "
                "for advertising.</p>",
            ),
            (
                "3. Data sharing",
                "<p>Your data is shared only in these cases:</p>"
                "<ul>"
                "<li><strong>Within your family:</strong> shared data (family wallets, "
                "transactions, categories, budgets) is visible to members of the same "
                "family. <em>Personal</em> wallets are private to you — even from the "
                "family owner.</li>"
                "<li><strong>Infrastructure providers:</strong> data is stored on a cloud "
                "database service (Oracle Cloud) to run the app.</li>"
                "<li><strong>Legal requirements:</strong> when required by law.</li>"
                "</ul>",
            ),
            (
                "4. Data retention and deletion",
                "<p>You can <strong>delete your account from within the app</strong> "
                "(Profile → Delete account). On deletion:</p>"
                "<ul>"
                "<li>The account is disabled immediately (you can no longer sign in).</li>"
                "<li>Data is permanently purged after a <strong>30-day</strong> retention "
                "window. If you are a member of a still-active family, your personal "
                "information is anonymised to preserve the integrity of shared data.</li>"
                "</ul>"
                f"<p>You may also request deletion by emailing "
                f"<a href=\"mailto:{CONTACT_EMAIL}\">{CONTACT_EMAIL}</a>.</p>",
            ),
            (
                "5. Security",
                "<p>Connections to the server are encrypted; passwords are hashed with "
                "bcrypt; data access is always scoped to your family. No system is perfectly "
                "secure, however — please keep your password private.</p>",
            ),
            (
                "6. Children",
                "<p>The app is not directed to children under 13, and we do not knowingly "
                "collect data from children.</p>",
            ),
            (
                "7. Your rights",
                "<p>You can access, edit, and delete your data directly in the app, or "
                "contact us for help.</p>",
            ),
            (
                "8. Changes to this policy",
                "<p>We may update this policy; changes will be posted on this page with a "
                "new last-updated date.</p>",
            ),
            (
                "9. Contact",
                f"<p>Questions? Email <a href=\"mailto:{CONTACT_EMAIL}\">{CONTACT_EMAIL}</a> "
                f"&middot; <a href=\"{WEBSITE}\">{WEBSITE}</a>.</p>",
            ),
        ],
    },
}

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  line-height: 1.65;
  color: #1a1a2e;
  background: #f6f6fb;
}
@media (prefers-color-scheme: dark) {
  body { color: #e7e7ef; background: #14141b; }
  .card { background: #1e1e29 !important; box-shadow: none !important; }
  a { color: #9db4ff !important; }
  h2 { border-color: #2c2c3a !important; }
  .meta { color: #9a9aa8 !important; }
}
.wrap { max-width: 760px; margin: 0 auto; padding: 32px 20px 64px; }
.card {
  background: #fff;
  border-radius: 18px;
  padding: 32px 28px;
  box-shadow: 0 2px 16px rgba(40, 40, 90, 0.08);
}
.top { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
h1 { font-size: 1.7rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 28px 0 8px; padding-bottom: 6px;
     border-bottom: 1px solid #ececf3; }
.meta { color: #6a6a78; font-size: 0.9rem; margin: 0 0 18px; }
a { color: #4b56d2; text-decoration: none; }
a:hover { text-decoration: underline; }
ul { padding-left: 1.25rem; }
li { margin: 4px 0; }
.lang {
  font-size: 0.85rem; white-space: nowrap;
  border: 1px solid currentColor; border-radius: 999px;
  padding: 5px 12px; opacity: 0.8;
}
"""


def _render(lang: str) -> str:
    data = _CONTENT.get(lang, _CONTENT["vi"])
    sections_html = "\n".join(
        f"<h2>{heading}</h2>{body}"
        for heading, body in data["sections"]  # type: ignore[attr-defined]
    )
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<title>{data["title"]} — {APP_NAME}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="top">
      <h1>{data["title"]}</h1>
      <a class="lang" href="{data["lang_switch"]}">{data["lang_label"]}</a>
    </div>
    <p class="meta">{APP_NAME} &middot; {data["updated"]}</p>
    <p>{data["intro"]}</p>
    {sections_html}
  </div>
</div>
</body>
</html>"""


@router.get(
    "/privacy",
    response_class=HTMLResponse,
    summary="Privacy policy (public, no auth)",
)
def privacy_policy(
    lang: str = Query(default="vi", pattern="^(vi|en)$"),
) -> HTMLResponse:
    """The app's privacy policy as an HTML page. Public (no auth) so it can be
    used as the Google Play store-listing URL. Use `?lang=vi` or `?lang=en`."""
    return HTMLResponse(content=_render(lang))
