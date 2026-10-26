"""LinkedIn OAuth (3-legged) and the Posts API."""

import io
import os
import re
import time
from urllib.parse import urlencode

import httpx
from PIL import Image

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
IMAGES_URL = "https://api.linkedin.com/rest/images?action=initializeUpload"
SCOPES = "openid profile w_member_social"
API_VERSION = os.getenv("LINKEDIN_API_VERSION", "202610")

# Characters with special meaning in LinkedIn's "little text" commentary format.
# Left unescaped they can make the API silently truncate the post.
_RESERVED = re.compile(r"([\\|{}@\[\]()<>*_~]|#(?!\w))")
_URL = re.compile(r"https?://\S+")
# Image types LinkedIn accepts as-is; anything else (e.g. WebP, AVIF) is converted to JPEG
_LINKEDIN_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif"}


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


def _headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _download_image(url: str) -> bytes:
    r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0 WeeklyTechDigest/1.0"}, follow_redirects=True, timeout=30)
    r.raise_for_status()
    if r.headers.get("content-type", "").split(";")[0].strip() in _LINKEDIN_IMAGE_TYPES:
        return r.content
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


def upload_image(access_token: str, person_urn: str, image_url: str) -> str:
    """Upload the image at image_url to LinkedIn. Returns its image URN."""
    data = _download_image(image_url)
    r = httpx.post(IMAGES_URL, json={"initializeUploadRequest": {"owner": person_urn}},
                   headers=_headers(access_token), timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"LinkedIn image upload returned {r.status_code}: {r.text}")
    upload = r.json()["value"]
    put = httpx.put(upload["uploadUrl"], content=data,
                    headers={"Authorization": f"Bearer {access_token}"}, timeout=60)
    if put.status_code >= 300:
        raise RuntimeError(f"LinkedIn image upload returned {put.status_code}: {put.text}")
    return upload["image"]


def create_post(access_token: str, person_urn: str, text: str,
                image_urn: str | None = None, alt_text: str = "") -> str:
    """Publish a public post, with an image when image_urn is given. Returns the post URN."""
    body = {
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
    }
    if image_urn:
        body["content"] = {"media": {"id": image_urn, "altText": alt_text[:4086]}}
    r = httpx.post(POSTS_URL, json=body, headers=_headers(access_token), timeout=30)
    if r.status_code != 201:
        raise RuntimeError(f"LinkedIn returned {r.status_code}: {r.text}")
    return r.headers.get("x-restli-id", "")
