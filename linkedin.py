"""LinkedIn OAuth (3-legged) and the Posts API."""

import os
import re
import time
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
SCOPES = "openid profile w_member_social"
API_VERSION = os.getenv("LINKEDIN_API_VERSION", "202610")

# Characters with special meaning in LinkedIn's "little text" commentary format.
# Left unescaped they can make the API silently truncate the post.
_RESERVED = re.compile(r"([\\|{}@\[\]()<>*_~]|#(?!\w))")
_URL = re.compile(r"https?://\S+")


def escape_commentary(text: str) -> str:
    """Escape reserved characters, keeping URLs and #hashtags intact."""
    out, pos = [], 0
    for m in _URL.finditer(text):
        out.append(_RESERVED.sub(r"\\\1", text[pos:m.start()]))
        out.append(m.group())
        pos = m.end()
    out.append(_RESERVED.sub(r"\\\1", text[pos:]))
    return "".join(out)


def _redirect_uri() -> str:
    return os.environ["PUBLIC_URL"].rstrip("/") + "/callback"


def authorize_url(state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "response_type": "code",
        "client_id": os.environ["LINKEDIN_CLIENT_ID"],
        "redirect_uri": _redirect_uri(),
        "state": state,
        "scope": SCOPES,
    })


def exchange_code(code: str) -> dict:
    """Trade the OAuth code for a token; returns token, expiry and the member's person URN."""
    r = httpx.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(),
        "client_id": os.environ["LINKEDIN_CLIENT_ID"],
        "client_secret": os.environ["LINKEDIN_CLIENT_SECRET"],
    }, timeout=30)
    r.raise_for_status()
    token = r.json()
    me = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {token['access_token']}"}, timeout=30)
    me.raise_for_status()
    info = me.json()
    return {
        "access_token": token["access_token"],
        "expires_at": time.time() + token["expires_in"],
        "person_urn": f"urn:li:person:{info['sub']}",
        "name": info.get("name", ""),
    }


def create_post(access_token: str, person_urn: str, text: str) -> str:
    """Publish a public text post. Returns the post URN."""
    r = httpx.post(POSTS_URL, json={
        "author": person_urn,
        "commentary": escape_commentary(text),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }, headers={
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }, timeout=30)
    if r.status_code != 201:
        raise RuntimeError(f"LinkedIn returned {r.status_code}: {r.text}")
    return r.headers.get("x-restli-id", "")
