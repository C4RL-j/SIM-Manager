"""Source-backed MyDITO authentication boundary; no networking or secrets.

The public-source ledger under tests/fixtures/dito records why these paths exist.
The default remains authentication-only. The separately enabled account reader
admits only public-source-verified read getters, never purchases or other writes.
"""

from importlib.resources import files
import re
from urllib.parse import urlsplit

LOGIN_URL = "https://my.dito.ph/"
LOGIN_PATH = "/ecare/webs/user/login"
LOGOUT_PATH = "/ecare/webs/user/logout"
SUCCESS_PATH = "/pto/home"
PROBE_SOURCE = (
    "(() => { try { const o = window.__simManagerDitoAuthObserver; "
    "return o && typeof o.poll === 'function' ? o.poll() : 'unsupported'; "
    "} catch (_) { return 'unsupported'; } })()"
)

AUTH_REQUESTS = frozenset(
    {
        ("POST", LOGIN_PATH),
        ("GET", LOGOUT_PATH),
        ("POST", "/ecare/webs/captcha/check"),
        ("POST", "/ecare/webs/user/login/check"),
        ("POST", "/ecare/webs/common/configParam"),
        ("POST", "/ecare/webs/content/qryContentByCode"),
        ("POST", "/ecare/webs/cust/sign/privacyPolicy"),
        ("GET", "/ecare/webs/common/defCurrencyType"),
        ("GET", "/ecare/common/currencyType/default"),
    }
)
_CAPTCHA = re.compile(r"/ecare/webs/captcha/[A-Za-z0-9_-]{1,128}\Z")
# sendType=1 is the official sign-in Get SMS Code action; type=2 resets a password.
_SMS_REQUEST = re.compile(r"/ecare/webs/message/sms/1/[0-9]{10,11}\Z")
_ASSET = re.compile(
    r"/(?:assets/|lib/)?[A-Za-z0-9_.\-/]+\.(?:js|css|png|jpg|jpeg|svg|gif|webp|ico|woff|woff2|ttf|otf)\Z"
)
_ACCOUNT_VIEW = re.compile(
    r"/(?:layouts__BaseLayout|p__Home)\.[0-9a-f]{8}\.async\.js\Z"
)


def trusted_origin(url: str) -> bool:
    """Accept exactly the evidenced HTTPS origin, without URL credentials."""
    if not isinstance(url, str) or not url or len(url) > 8192:
        return False
    if "\\" in url or any(ord(char) < 33 or ord(char) == 127 for char in url):
        return False
    try:
        parts = urlsplit(url)
        return (
            parts.scheme == "https"
            and parts.hostname == "my.dito.ph"
            and parts.username is None
            and parts.password is None
            and parts.port in (None, 443)
            and parts.netloc.lower() in {"my.dito.ph", "my.dito.ph:443"}
        )
    except (TypeError, ValueError):
        return False


def authenticated_route(url: str) -> bool:
    if not trusted_origin(url):
        return False
    parts = urlsplit(url)
    return parts.path == SUCCESS_PATH and not parts.query and not parts.fragment


def request_allowed(url: str, method: str) -> bool:
    """Allow official manual auth and static assets; deny all other requests."""
    if not trusted_origin(url) or not isinstance(method, str) or method not in {"GET", "POST"}:
        return False
    parts = urlsplit(url)
    path = parts.path
    if "%" in path or "//" in path or any(segment in {".", ".."} for segment in path.split("/")):
        return False
    # The official success effect installs its session before pushing /pto/home.
    # That route lazily loads these account views. Preventing their load keeps
    # the auth-only handoff intact without executing account/balance bootstrap
    # or its auxiliary subscriber-info guard. No history or response is changed.
    if _ACCOUNT_VIEW.fullmatch(path):
        return False
    if any(allowed_path == path for _, allowed_path in AUTH_REQUESTS):
        return (method, path) in AUTH_REQUESTS
    if method == "POST" and _SMS_REQUEST.fullmatch(path):
        return True
    if method != "GET":
        return False
    if _CAPTCHA.fullmatch(path):
        return True
    if path in {"/", SUCCESS_PATH}:
        return not parts.query and not parts.fragment
    if not _ASSET.fullmatch(path):
        return False
    # A suffix must not turn an API or arbitrary nested route into a static asset.
    return path.startswith(("/assets/", "/lib/")) or path.count("/") == 1


def observer_source() -> str:
    return files("sim_manager.carriers.dito").joinpath("auth_observer.js").read_text(encoding="utf-8")


def account_request_allowed(url: str, method: str) -> bool:
    """Extend the unchanged login policy with the three reviewed account reads.

    POST is the official site's getter method for both balance APIs. Product
    identifiers remain inside the page; no caller can choose another origin.
    Protected Home/BaseLayout chunks remain blocked to avoid unrelated effects.
    """
    if request_allowed(url, method):
        return True
    if not trusted_origin(url):
        return False
    parts = urlsplit(url)
    if parts.fragment:
        return False
    if method == "POST" and parts.path in {
        "/ecare/webs/balance/balInfo",
        "/ecare/webs/balance/balInfo/glSumInfo",
    }:
        return not parts.query
    if method == "GET" and parts.path == "/ecare/webs/subs/qrySubsDetail":
        return re.fullmatch(r"prodInstIds=[0-9]{1,32}", parts.query) is not None
    return False
