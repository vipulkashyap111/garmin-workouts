"""Browser-based Garmin Connect login.

Opens a real browser to connect.garmin.com, lets the user log in normally,
then captures SSO ticket → exchanges for OAuth tokens (~1 year lifespan).
Falls back to session cookies if OAuth exchange fails.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs

import requests
from playwright.sync_api import sync_playwright

COOKIE_FILE = "garmin_cookies.json"
TOKEN_FILE = "garmin_session.json"
OAUTH_CONSUMER_URL = "https://thegarth.s3.amazonaws.com/oauth_consumer.json"
MOBILE_UA = "com.garmin.android.apps.connectmobile"


def _get_token_dir(token_dir: str = None) -> Path:
    if token_dir is None:
        token_dir = str(Path.home() / ".garminconnect")
    return Path(token_dir)


def get_cookie_path(token_dir: str = None) -> Path:
    return _get_token_dir(token_dir) / COOKIE_FILE


def get_token_path(token_dir: str = None) -> Path:
    return _get_token_dir(token_dir) / TOKEN_FILE


def browser_login(token_dir: str = None) -> bool:
    """Login via browser. Tries OAuth token exchange first, falls back to cookies."""
    token_path = _get_token_dir(token_dir)
    token_path.mkdir(parents=True, exist_ok=True)

    captured_token = {}
    captured_ticket = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="msedge",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        )
        page = context.new_page()

        # Capture CSRF token and SSO ticket
        def capture_auth(request):
            csrf = request.headers.get("connect-csrf-token", "")
            if csrf and not captured_token.get("csrf"):
                captured_token["csrf"] = csrf

        def capture_response(response):
            url = response.url
            if "ticket=" in url:
                m = re.search(r"ticket=(ST-[A-Za-z0-9\-]+)", url)
                if m and not captured_ticket.get("ticket"):
                    captured_ticket["ticket"] = m.group(1)

        page.on("request", capture_auth)
        page.on("response", capture_response)

        page.goto("https://connect.garmin.com/modern/")

        print()
        print("=" * 50)
        print("  Browser opened — log in to Garmin Connect.")
        print("  The window will close automatically once")
        print("  you're on the dashboard.")
        print("=" * 50)
        print()

        max_wait = 600
        start = time.time()
        logged_in = False

        while time.time() - start < max_wait:
            try:
                url = page.url
                # Also try to capture ticket from page content/URL during SSO redirect
                if "ticket=" in url:
                    m = re.search(r"ticket=(ST-[A-Za-z0-9\-]+)", url)
                    if m and not captured_ticket.get("ticket"):
                        captured_ticket["ticket"] = m.group(1)

                if "connect.garmin.com" in url and "sso.garmin.com" not in url and "signin" not in url:
                    page.wait_for_load_state("networkidle")
                    page.goto("https://connect.garmin.com/modern/workouts")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(3000)
                    logged_in = True
                    break
            except Exception:
                pass
            page.wait_for_timeout(1000)

        if not logged_in:
            print("❌ Timed out waiting for login (10 min).")
            browser.close()
            return False

        cookies = context.cookies()
        browser.close()

    # Save cookies (always — as fallback)
    cookie_file = token_path / COOKIE_FILE
    cookie_file.write_text(json.dumps(cookies, indent=2))

    token_file = token_path / TOKEN_FILE
    token_file.write_text(json.dumps(captured_token, indent=2))

    # Try OAuth token exchange if we captured a ticket
    oauth_success = False
    ticket = captured_ticket.get("ticket")
    if ticket:
        print("🔑 Captured SSO ticket, exchanging for OAuth tokens...")
        oauth_success = _try_oauth_exchange(ticket, str(token_path))
    else:
        print("⚠️  No SSO ticket captured — trying alternative method...")
        # Try to get ticket from CASTGC cookie
        castgc = None
        for c in cookies:
            if c.get("name") == "CASTGC":
                castgc = c.get("value")
                break
        if castgc and castgc.startswith("TGT-"):
            print("🔑 Found CASTGC, attempting service ticket exchange...")
            oauth_success = _try_service_ticket(castgc, str(token_path))

    garmin_cookies = [c for c in cookies if "garmin" in c.get("domain", "")]
    if oauth_success:
        print(f"✅ Logged in with OAuth tokens (~1 year lifespan).")
    else:
        csrf = captured_token.get("csrf", "")
        parts = [f"Saved {len(garmin_cookies)} cookies"]
        if csrf:
            parts.append("CSRF token")
        print(f"✅ Logged in with {' + '.join(parts)} (session-based, may expire in hours).")
    print(f"   Saved to {token_path}")
    return True


def _try_oauth_exchange(ticket: str, token_dir: str) -> bool:
    """Exchange SSO ticket for OAuth1 → OAuth2 tokens, save in garth format."""
    try:
        from requests_oauthlib import OAuth1Session

        consumer = requests.get(OAUTH_CONSUMER_URL, timeout=10).json()

        # OAuth1 exchange
        sess = OAuth1Session(consumer["consumer_key"], consumer["consumer_secret"])
        url = (
            f"https://connectapi.garmin.com/oauth-service/oauth/"
            f"preauthorized?ticket={ticket}"
            f"&login-url=https://sso.garmin.com/sso/embed"
            f"&accepts-mfa-tokens=true"
        )
        resp = sess.get(url, headers={"User-Agent": MOBILE_UA}, timeout=15)
        if resp.status_code == 429:
            print("  ⚠️  OAuth exchange rate-limited, using cookies instead.")
            return False
        resp.raise_for_status()
        parsed = parse_qs(resp.text)
        oauth1 = {k: v[0] for k, v in parsed.items()}
        oauth1["domain"] = "garmin.com"

        # OAuth2 exchange
        sess2 = OAuth1Session(
            consumer["consumer_key"], consumer["consumer_secret"],
            resource_owner_key=oauth1["oauth_token"],
            resource_owner_secret=oauth1["oauth_token_secret"],
        )
        resp2 = sess2.post(
            "https://connectapi.garmin.com/oauth-service/oauth/exchange/user/2.0",
            headers={"User-Agent": MOBILE_UA, "Content-Type": "application/x-www-form-urlencoded"},
            data={"mfa_token": oauth1.get("mfa_token", "")},
            timeout=15,
        )
        if resp2.status_code == 429:
            print("  ⚠️  OAuth2 exchange rate-limited, using cookies instead.")
            return False
        resp2.raise_for_status()
        oauth2 = resp2.json()
        oauth2["expires_at"] = int(time.time() + oauth2["expires_in"])
        oauth2["refresh_token_expires_at"] = int(time.time() + oauth2["refresh_token_expires_in"])

        # Save in garth format
        token_path = Path(token_dir)
        (token_path / "oauth1_token.json").write_text(json.dumps(oauth1, indent=2))
        (token_path / "oauth2_token.json").write_text(json.dumps(oauth2, indent=2))
        return True

    except Exception as e:
        print(f"  ⚠️  OAuth exchange failed: {e}")
        return False


def _try_service_ticket(castgc: str, token_dir: str) -> bool:
    """Try to get a service ticket using the CASTGC (TGT) cookie."""
    try:
        resp = requests.get(
            "https://sso.garmin.com/sso/login",
            params={
                "service": "https://sso.garmin.com/sso/embed",
                "clientId": "GarminConnect",
            },
            cookies={"CASTGC": castgc},
            headers={"User-Agent": MOBILE_UA},
            allow_redirects=False,
            timeout=15,
        )
        location = resp.headers.get("location", "")
        m = re.search(r"ticket=(ST-[A-Za-z0-9\-]+)", location)
        if m:
            return _try_oauth_exchange(m.group(1), token_dir)
        return False
    except Exception:
        return False


def get_garmin_client():
    """Try to get an authenticated garminconnect client using saved OAuth tokens."""
    token_path = _get_token_dir()
    oauth1_file = token_path / "oauth1_token.json"
    oauth2_file = token_path / "oauth2_token.json"

    if oauth1_file.exists() and oauth2_file.exists():
        try:
            from garminconnect import Garmin
            client = Garmin()
            client.login(str(token_path))
            return client
        except Exception:
            return None
    return None


def has_oauth_tokens(token_dir: str = None) -> bool:
    """Check if OAuth tokens exist."""
    token_path = _get_token_dir(token_dir)
    return (token_path / "oauth1_token.json").exists() and (token_path / "oauth2_token.json").exists()


def load_cookies(token_dir: str = None) -> dict:
    """Load saved cookies as a dict for requests session."""
    cookie_file = get_cookie_path(token_dir)
    if not cookie_file.exists():
        return {}
    cookies = json.loads(cookie_file.read_text())
    return {c["name"]: c["value"] for c in cookies}


def load_session_token(token_dir: str = None) -> dict:
    """Load saved bearer token and headers."""
    token_file = get_token_path(token_dir)
    if not token_file.exists():
        return {}
    return json.loads(token_file.read_text())


def has_saved_session(token_dir: str = None) -> bool:
    """Check if any auth method is available."""
    return has_oauth_tokens(token_dir) or get_cookie_path(token_dir).exists()
