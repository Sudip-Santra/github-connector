# Authentication Implementation Guide

## Overview

This project uses **GitHub OAuth 2.0** for user authentication. When a user logs in via GitHub, the server exchanges the OAuth authorization code for a GitHub access token, fetches the user's profile, wraps everything into a **JWT (JSON Web Token)**, and sets it as an **HTTP-only cookie** that expires in **7 days**. All subsequent protected API calls read this cookie to identify and authorize the user.

---

## Table of Contents

1. [Authentication Flow Diagram](#authentication-flow-diagram)
2. [Environment Configuration](#environment-configuration)
3. [Files Involved](#files-involved)
4. [Step-by-Step Detailed Walkthrough](#step-by-step-detailed-walkthrough)
   - [Step 1: User Initiates Login — GET /login](#step-1-user-initiates-login--get-login)
   - [Step 2: User Authorizes on GitHub](#step-2-user-authorizes-on-github)
   - [Step 3: GitHub Redirects Back — GET /callback](#step-3-github-redirects-back--get-callback)
   - [Step 4: Accessing Protected Routes — GET /me](#step-4-accessing-protected-routes--get-me)
5. [JWT Token Structure](#jwt-token-structure)
6. [Cookie Configuration](#cookie-configuration)
7. [Authentication Dependency — get_current_user](#authentication-dependency--get_current_user)
8. [Error Handling](#error-handling)
9. [Security Considerations](#security-considerations)

---

## Authentication Flow Diagram

```
┌──────────┐       ┌──────────────┐       ┌──────────────┐
│  Browser │       │  Our Server  │       │  GitHub API  │
└─────┬────┘       └──────┬───────┘       └──────┬───────┘
      │                   │                      │
      │  1. GET /login    │                      │
      │──────────────────>│                      │
      │                   │                      │
      │  2. 302 Redirect  │                      │
      │   to GitHub OAuth │                      │
      │<──────────────────│                      │
      │                   │                      │
      │  3. User authorizes on GitHub            │
      │─────────────────────────────────────────>│
      │                   │                      │
      │  4. GitHub redirects to /callback?code=  │
      │<─────────────────────────────────────────│
      │                   │                      │
      │  5. GET /callback?code=abc123            │
      │──────────────────>│                      │
      │                   │                      │
      │                   │  6. POST exchange    │
      │                   │  code for token      │
      │                   │─────────────────────>│
      │                   │                      │
      │                   │  7. { access_token } │
      │                   │<─────────────────────│
      │                   │                      │
      │                   │  8. GET /user        │
      │                   │  (with access_token) │
      │                   │─────────────────────>│
      │                   │                      │
      │                   │  9. { user profile } │
      │                   │<─────────────────────│
      │                   │                      │
      │  10. JSON response│                      │
      │  + Set-Cookie:    │                      │
      │    auth_token=JWT │                      │
      │<──────────────────│                      │
      │                   │                      │
      │  11. GET /me      │                      │
      │  Cookie: auth_token=JWT                  │
      │──────────────────>│                      │
      │                   │                      │
      │  12. Decode JWT,  │                      │
      │  return user info │                      │
      │<──────────────────│                      │
```

---

## Environment Configuration

All sensitive values are stored in the `.env` file and loaded via `config.py`. Nothing is hardcoded.

| Variable | Purpose |
|---|---|
| `GITHUB_CLIENT_ID` | The OAuth App's Client ID from GitHub Developer Settings |
| `GITHUB_CLIENT_SECRET` | The OAuth App's Client Secret from GitHub Developer Settings |
| `GITHUB_REDIRECT_URI` | The callback URL registered in GitHub (must match exactly) e.g. `http://localhost:8000/callback` |
| `JWT_SECRET` | A random secret key used to sign and verify JWT tokens |
| `ALGORITHM` | The hashing algorithm for JWT (we use `HS256`) |

**config.py** loads these once at import time:

```python
import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")
JWT_SECRET = os.getenv("JWT_SECRET")
ALGORITHM = os.getenv("ALGORITHM")
```

Any file that needs config values simply does `from config import ...`.

---

## Files Involved

| File | Role |
|---|---|
| `.env` | Stores all secrets and configuration |
| `config.py` | Loads `.env` values and exports them as Python constants |
| `api/auth.py` | Contains `/login` and `/callback` endpoints (the OAuth flow) |
| `api/deps.py` | Contains the `get_current_user` dependency (JWT cookie verification) |
| `app.py` | Registers auth routes and the `/me` protected endpoint |

---

## Step-by-Step Detailed Walkthrough

### Step 1: User Initiates Login — `GET /login`

**File:** `api/auth.py`

**What happens:**

1. The user (or Swagger UI) hits `GET /login`.
2. The server constructs a GitHub OAuth authorization URL with the following query parameters:
   - `client_id` — Our app's GitHub OAuth Client ID
   - `redirect_uri` — Where GitHub should send the user back (`http://localhost:8000/callback`)
   - `scope=repo` — The permissions we are requesting (access to the user's repositories)
3. The server returns a **302 Redirect** to this GitHub URL.

**The constructed URL looks like:**
```
https://github.com/login/oauth/authorize
  ?client_id=<YOUR_GITHUB_CLIENT_ID>
  &redirect_uri=http://localhost:8000/callback
  &scope=repo
```

**Code:**
```python
@router.get("/login")
def login():
    url = (
        f"{GITHUB_AUTHORIZE_URL}"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&scope=repo"
    )
    return RedirectResponse(url)
```

**Key detail:** The `scope=repo` grants our app access to the user's public and private repositories. This is necessary for later API actions like fetching repos, creating issues, etc.

---

### Step 2: User Authorizes on GitHub

**This happens entirely on GitHub's side — no code from our server is involved.**

1. The user's browser lands on GitHub's authorization page.
2. GitHub shows the user which permissions our app is requesting (`repo` scope).
3. The user clicks **"Authorize"**.
4. GitHub generates a temporary **authorization code** (a short-lived, one-time-use string).
5. GitHub redirects the user's browser to our `redirect_uri` with the code as a query parameter:
   ```
   http://localhost:8000/callback?code=abc123def456
   ```

---

### Step 3: GitHub Redirects Back — `GET /callback`

**File:** `api/auth.py`

This is the most critical endpoint. It does **three things** in sequence:

#### 3a. Exchange the Authorization Code for a GitHub Access Token

The temporary `code` from GitHub is **not** an access token — it can only be used once to request the actual token. Our server sends a `POST` request to GitHub's token endpoint:

**Request to GitHub:**
```
POST https://github.com/login/oauth/access_token
Content-Type: application/json
Accept: application/json

{
    "client_id": "<YOUR_GITHUB_CLIENT_ID>",
    "client_secret": "<YOUR_GITHUB_CLIENT_SECRET>",
    "code": "<TEMPORARY_AUTH_CODE_FROM_GITHUB>",
    "redirect_uri": "http://localhost:8000/callback"
}
```

**Response from GitHub:**
```json
{
    "access_token": "gho_xxxxxxxxxxxxxxxxxxxx",
    "token_type": "bearer",
    "scope": "repo"
}
```

**Code:**
```python
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
```

**Error handling:** If `access_token` is not present in the response, it means the OAuth flow failed (expired code, wrong credentials, etc.). We raise a 400 error with the description GitHub provides.

```python
if not github_access_token:
    raise HTTPException(
        status_code=400,
        detail=f"GitHub OAuth failed: {token_data.get('error_description', 'Unknown error')}"
    )
```

#### 3b. Fetch the User's GitHub Profile

Now that we have the access token, we use it to call the GitHub API and get the user's profile information:

**Request to GitHub:**
```
GET https://api.github.com/user
Authorization: Bearer gho_xxxxxxxxxxxxxxxxxxxx
```

**Response from GitHub:**
```json
{
    "login": "johndoe",
    "avatar_url": "https://avatars.githubusercontent.com/u/12345",
    "name": "John Doe",
    "email": "john@example.com",
    ...
}
```

**Code:**
```python
async with httpx.AsyncClient() as client:
    user_response = await client.get(
        GITHUB_USER_URL,
        headers={"Authorization": f"Bearer {github_access_token}"},
    )

user_data = user_response.json()
```

#### 3c. Create a JWT and Set It as a Cookie

We now have everything we need. We create a JWT that contains:

| Field | Value | Purpose |
|---|---|---|
| `github_token` | The GitHub access token | So protected routes can make GitHub API calls on behalf of the user |
| `username` | The user's GitHub login | For display/identification |
| `avatar_url` | The user's avatar URL | For display |
| `exp` | Current time + 7 days | JWT expiration — after this, the token is rejected |

**Code:**
```python
payload = {
    "github_token": github_access_token,
    "username": user_data.get("login"),
    "avatar_url": user_data.get("avatar_url"),
    "exp": datetime.now(timezone.utc) + timedelta(days=7),
}
auth_token = jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)
```

The JWT is signed using `JWT_SECRET` with the `HS256` algorithm. This means:
- **Only our server** can create valid tokens (because only we know the secret).
- **Anyone** can decode the payload (it's base64), but they **cannot tamper** with it without invalidating the signature.

Finally, we return a JSON response and attach the JWT as a cookie:

```python
response = JSONResponse(content={
    "message": "Login successful",
    "username": user_data.get("login"),
})
response.set_cookie(
    key="auth_token",
    value=auth_token,
    max_age=7 * 24 * 60 * 60,  # 7 days in seconds = 604800
    httponly=True,
    samesite="lax",
)
return response
```

---

### Step 4: Accessing Protected Routes — `GET /me`

**File:** `app.py`

After login, the browser automatically sends the `auth_token` cookie with every request to our server. Protected endpoints use FastAPI's `Depends()` to call `get_current_user`, which extracts and verifies the JWT.

```python
@app.get("/me", tags=["Auth"])
def me(user: dict = Depends(get_current_user)):
    return {"username": user["username"], "avatar_url": user["avatar_url"]}
```

The `user` dict here is the decoded JWT payload, so it contains `github_token`, `username`, `avatar_url`, and `exp`.

---

## JWT Token Structure

A JWT has three parts separated by dots: `header.payload.signature`

**Header (auto-generated by PyJWT):**
```json
{
    "alg": "HS256",
    "typ": "JWT"
}
```

**Payload (what we set):**
```json
{
    "github_token": "gho_xxxxxxxxxxxxxxxxxxxx",
    "username": "johndoe",
    "avatar_url": "https://avatars.githubusercontent.com/u/12345",
    "exp": 1712505600
}
```

**Signature:**
```
HMACSHA256(
    base64UrlEncode(header) + "." + base64UrlEncode(payload),
    JWT_SECRET
)
```

The `exp` field is a Unix timestamp. PyJWT automatically rejects tokens where `exp` is in the past.

---

## Cookie Configuration

| Property | Value | Why |
|---|---|---|
| `key` | `auth_token` | The name of the cookie |
| `value` | The JWT string | Contains all auth data |
| `max_age` | `604800` (7 days in seconds) | Cookie expires after 7 days, matching the JWT expiry |
| `httponly` | `True` | JavaScript cannot access this cookie — prevents XSS attacks from stealing the token |
| `samesite` | `lax` | Cookie is sent on same-site requests and top-level navigations — provides CSRF protection while still allowing the OAuth redirect flow to work |

---

## Authentication Dependency — get_current_user

**File:** `api/deps.py`

This is a FastAPI dependency function. Any endpoint that needs authentication adds `user: dict = Depends(get_current_user)` to its parameters.

**What it does step by step:**

1. **Extract the cookie:** Reads `auth_token` from the request cookies.
2. **Check existence:** If no cookie is found, return `401 Not authenticated`.
3. **Decode the JWT:** Uses `jwt.decode()` with our `JWT_SECRET` and `ALGORITHM` to verify the signature and decode the payload.
4. **Check expiration:** PyJWT automatically checks the `exp` claim. If the token is expired, it raises `ExpiredSignatureError` and we return `401 Token expired`.
5. **Handle invalid tokens:** Any other JWT error (tampered signature, malformed token) raises `InvalidTokenError` and we return `401 Invalid token`.
6. **Return the payload:** If everything is valid, the decoded payload dict is returned and injected into the endpoint function.

```python
def get_current_user(request: Request) -> dict:
    token = request.cookies.get("auth_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

**Important:** The returned `payload` dict contains `github_token`. This means any protected endpoint can extract it and use it to make authenticated GitHub API calls:

```python
github_token = user["github_token"]
# Use this to call GitHub API on behalf of the user
```

---

## Error Handling

| Scenario | HTTP Status | Error Detail | Where |
|---|---|---|---|
| GitHub OAuth code exchange fails | `400` | `GitHub OAuth failed: <description>` | `api/auth.py` — `/callback` |
| No `auth_token` cookie in request | `401` | `Not authenticated` | `api/deps.py` — `get_current_user` |
| JWT token has expired (past 7 days) | `401` | `Token expired` | `api/deps.py` — `get_current_user` |
| JWT token is tampered/malformed | `401` | `Invalid token` | `api/deps.py` — `get_current_user` |

---

## Security Considerations

1. **No hardcoded secrets:** All credentials (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `JWT_SECRET`) are loaded from `.env` via `config.py`. The `.env` file is listed in `.gitignore`.

2. **HTTP-only cookie:** The `auth_token` cookie has `httponly=True`, which means client-side JavaScript cannot read it. This mitigates **XSS (Cross-Site Scripting)** attacks.

3. **SameSite=Lax:** The cookie is only sent on same-site requests and top-level navigations. This provides baseline **CSRF (Cross-Site Request Forgery)** protection.

4. **JWT expiration:** Tokens expire after 7 days. After that, the user must re-authenticate via `/login`.

5. **One-time authorization code:** The `code` parameter from GitHub can only be used once. If someone intercepts it and tries to use it after our server already exchanged it, GitHub will reject it.

6. **GitHub token inside JWT:** The GitHub access token is stored inside the JWT payload. While the JWT payload is base64-encoded (not encrypted), the `httponly` cookie flag prevents client-side access, and the JWT signature prevents tampering.
