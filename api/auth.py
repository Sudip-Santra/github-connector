from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
import httpx
import jwt
from config import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_REDIRECT_URI, JWT_SECRET, ALGORITHM

router = APIRouter(tags=["Auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


@router.get("/login")
def login():
    """Redirect to GitHub OAuth authorization page."""
    url = (
        f"{GITHUB_AUTHORIZE_URL}"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&scope=repo"
    )
    return RedirectResponse(url)


@router.get("/callback")
async def callback(code: str):
    """Exchange GitHub code for access token, create JWT, and set cookie."""
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            json={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )

    token_data = token_response.json()
    github_access_token = token_data.get("access_token")
    if not github_access_token:
        raise HTTPException(status_code=400, detail=f"GitHub OAuth failed: {token_data.get('error_description', 'Unknown error')}")

    # Fetch GitHub user info
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {github_access_token}"},
        )

    user_data = user_response.json()

    # Create JWT with GitHub access token and user info
    payload = {
        "github_token": github_access_token,
        "username": user_data.get("login"),
        "avatar_url": user_data.get("avatar_url"),
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    auth_token = jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

    response = JSONResponse(content={
        "message": "Login successful",
        "username": user_data.get("login"),
    })
    response.set_cookie(
        key="auth_token",
        value=auth_token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
    )
    return response
