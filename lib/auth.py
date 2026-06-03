"""Garmin Connect authentication module.

Handles login with email/password, MFA, and persistent token storage.
Tokens are stored at ~/.garminconnect and persist for ~1 year.
"""

import os
import sys
from getpass import getpass
from pathlib import Path

import logging

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from garth.exc import GarthException, GarthHTTPError

# Suppress library tracebacks in normal operation
logging.getLogger("garminconnect").setLevel(logging.CRITICAL)
logging.getLogger("garth").setLevel(logging.CRITICAL)

DEFAULT_TOKEN_DIR = os.path.expanduser("~/.garminconnect")


def get_client(token_dir: str = DEFAULT_TOKEN_DIR) -> Garmin:
    """Get an authenticated Garmin client, reusing stored tokens if available."""
    token_path = Path(token_dir)

    # Try stored tokens first
    if token_path.exists() and list(token_path.glob("*.json")):
        try:
            client = Garmin()
            client.login(str(token_path))
            return client
        except GarminConnectTooManyRequestsError:
            print("❌ Rate limited by Garmin. Wait a few minutes and try again.")
            sys.exit(1)
        except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError):
            print("⚠️  Stored tokens expired. Re-authenticating...")

    # Interactive login
    return _interactive_login(token_dir)


def _interactive_login(token_dir: str = DEFAULT_TOKEN_DIR) -> Garmin:
    """Login with email/password, supporting MFA."""
    email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ")
    password = os.getenv("GARMIN_PASSWORD") or getpass("Garmin password: ")

    try:
        client = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
        result1, result2 = client.login()

        if result1 == "needs_mfa":
            mfa_code = input("Enter MFA code: ")
            try:
                client.resume_login(result2, mfa_code)
            except GarthHTTPError as e:
                if "429" in str(e):
                    print("❌ Rate limited. Wait a few minutes.")
                    sys.exit(1)
                raise

        # Persist tokens
        token_path = Path(token_dir)
        token_path.mkdir(parents=True, exist_ok=True)
        client.garth.dump(str(token_path))
        print(f"✅ Logged in. Tokens saved to {token_dir}")
        return client

    except GarminConnectAuthenticationError:
        print("❌ Invalid credentials.")
        sys.exit(1)
    except GarminConnectTooManyRequestsError:
        print("❌ Rate limited by Garmin. Wait 5-10 minutes and try again.")
        sys.exit(1)
    except (GarthHTTPError, GarminConnectConnectionError) as e:
        if "429" in str(e) or "Too Many Requests" in str(e):
            print("❌ Rate limited by Garmin. Wait 5-10 minutes and try again.")
        else:
            print(f"❌ Connection error: {e}")
        sys.exit(1)
