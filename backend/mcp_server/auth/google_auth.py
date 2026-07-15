"""Google OAuth2 authentication helper for the Google Drive connector.

Uses the existing ``credentials/client_secret.json`` to perform the OAuth2
flow.  On first invocation a browser-based consent screen is shown and the
resulting token is written to ``credentials/token.json``.  Subsequent calls
reuse (and auto-refresh) the saved token.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("mcp_server.google_auth")

# Paths relative to this file → mcp_server/credentials/
_CREDENTIALS_DIR = Path(__file__).resolve().parent.parent / "credentials"
_CLIENT_SECRET_PATH = _CREDENTIALS_DIR / "client_secret.json"
_TOKEN_PATH = _CREDENTIALS_DIR / "token.json"

# Scopes required for listing, searching, and downloading files from Drive.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_google_credentials():
    """Return authorised Google ``Credentials``, refreshing or creating as needed.

    Returns
    -------
    google.oauth2.credentials.Credentials
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds: Credentials | None = None

    # 1. Try to load an existing token
    if _TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), SCOPES)
            logger.info("Loaded existing Google token from %s", _TOKEN_PATH)
        except Exception:
            logger.warning("Existing token file is invalid; re-authenticating.")
            creds = None

    # 2. Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("Refreshed Google credentials.")
        except Exception:
            logger.warning("Token refresh failed; re-authenticating.")
            creds = None

    # 3. Full OAuth2 flow if we still don't have valid creds
    if not creds or not creds.valid:
        if not _CLIENT_SECRET_PATH.exists():
            raise FileNotFoundError(
                f"Google client secret not found at {_CLIENT_SECRET_PATH}. "
                "Please place your client_secret.json in the credentials/ folder."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(_CLIENT_SECRET_PATH), SCOPES
        )
        creds = flow.run_local_server(port=0)
        logger.info("Completed Google OAuth2 flow.")

    # 4. Persist the token for reuse
    _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    logger.info("Saved Google token to %s", _TOKEN_PATH)

    return creds
