# API Reference — GitHub Connector

Complete documentation for every endpoint exposed by the GitHub Connector application.

**Base URL:** `http://localhost:8000`
**Interactive Docs (Swagger UI):** `http://localhost:8000/docs`

---

## Table of Contents

1. [Authentication](#authentication)
   - [How Authentication Works](#how-authentication-works)
   - [Protected Endpoints](#protected-endpoints)
2. [Health](#health)
   - [GET /health](#get-health)
3. [Auth Endpoints](#auth-endpoints)
   - [GET /login](#get-login)
   - [GET /callback](#get-callback)
   - [GET /me](#get-me)
4. [Repositories](#repositories)
   - [GET /repos](#get-repos)
5. [Issues](#issues)
   - [GET /list-issues](#get-list-issues)
   - [POST /create-issue](#post-create-issue)
6. [Commits](#commits)
   - [GET /commits](#get-commits)
7. [Pull Requests](#pull-requests)
   - [POST /create-pull-request](#post-create-pull-request)
8. [Error Response Format](#error-response-format)
9. [Common Error Codes](#common-error-codes)

---

## Authentication

### How Authentication Works

This application uses **GitHub OAuth 2.0** for authentication. The flow is:

1. User hits `GET /login` → gets redirected to GitHub's authorization page.
2. User authorizes the app on GitHub → GitHub redirects back to `GET /callback` with a temporary code.
3. The server exchanges the code for a GitHub access token, fetches the user's profile, creates a **JWT**, and sets it as an **HTTP-only cookie** named `auth_token`.
4. The cookie is valid for **7 days** and is automatically sent with every subsequent request by the browser.

### Protected Endpoints

All endpoints except `/health`, `/login`, and `/callback` are **protected**. They require the `auth_token` cookie to be present in the request.

If the cookie is missing, expired, or invalid, the server responds with:

```json
{
    "detail": "Not authenticated"
}
```

**How it works internally:**

Protected endpoints use FastAPI's `Depends(get_current_user)` dependency. This dependency:

1. Reads the `auth_token` cookie from the request.
2. Decodes and verifies the JWT using the `JWT_SECRET` and `HS256` algorithm.
3. Checks the `exp` claim to ensure the token hasn't expired.
4. Returns the decoded payload containing `github_token`, `username`, and `avatar_url`.
5. The endpoint then uses `github_token` from the payload to make authenticated calls to the GitHub API on behalf of the user.

**Source file:** `api/deps.py`

---

## Health

### GET /health

Check if the server is running.

**Authentication:** Not required

**Request:**
```
GET /health
```

**Response:**

| Status | Body |
|---|---|
| `200 OK` | `{"status": "ok"}` |

**Example Response:**
```json
{
    "status": "ok"
}
```

**Source file:** `api/health.py`

---

## Auth Endpoints

### GET /login

Initiates the GitHub OAuth 2.0 login flow by redirecting the user to GitHub's authorization page.

**Authentication:** Not required

**Request:**
```
GET /login
```

**What happens step by step:**

1. The server constructs a GitHub OAuth authorization URL with:
   - `client_id` — The app's GitHub OAuth Client ID (from `.env`)
   - `redirect_uri` — The callback URL: `http://localhost:8000/callback`
   - `scope=repo` — Requests access to the user's repositories (public and private)
2. Returns a **302 redirect** to GitHub's authorization page.
3. The user sees GitHub's consent screen showing the permissions being requested.
4. If the user clicks "Authorize", GitHub redirects back to `/callback` with a temporary authorization code.

**Response:**

| Status | Description |
|---|---|
| `302 Found` | Redirects to `https://github.com/login/oauth/authorize?client_id=...&redirect_uri=...&scope=repo` |

**OAuth Scope Explained:**

The `repo` scope grants the application:
- Read/write access to public and private repositories
- Ability to create issues, pull requests, and read commits
- Access to repository metadata

**Source file:** `api/auth.py`

---

### GET /callback

GitHub redirects to this endpoint after the user authorizes the application. This endpoint handles the entire token exchange and session creation.

**Authentication:** Not required (this endpoint *creates* the authentication)

**Request:**
```
GET /callback?code=<TEMPORARY_AUTH_CODE_FROM_GITHUB>
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `code` | string | Yes | Temporary authorization code provided by GitHub in the redirect URL |

**What happens step by step:**

1. **Code-to-Token Exchange:** The server sends a `POST` request to `https://github.com/login/oauth/access_token` with:
   - `client_id` — From `.env`
   - `client_secret` — From `.env`
   - `code` — The temporary code from the query parameter
   - `redirect_uri` — Must match the registered callback URL
   - GitHub responds with an `access_token` (the user's GitHub OAuth token)

2. **Fetch User Profile:** The server calls `GET https://api.github.com/user` using the newly obtained `access_token` to fetch the user's GitHub profile (username, avatar URL, etc.).

3. **Create JWT:** The server creates a JWT containing:
   - `github_token` — The GitHub access token (so future API calls can be made on behalf of the user)
   - `username` — The user's GitHub login name
   - `avatar_url` — The user's GitHub avatar URL
   - `exp` — Expiration timestamp set to **7 days from now** (UTC)

4. **Set Cookie:** The JWT is set as an HTTP-only cookie named `auth_token` with the following properties:
   - `max_age=604800` — 7 days in seconds
   - `httponly=True` — Cannot be accessed by JavaScript (XSS protection)
   - `samesite=lax` — Sent on same-site requests and top-level navigations (CSRF protection)

**Response:**

| Status | Description |
|---|---|
| `200 OK` | Login successful, cookie is set |
| `400 Bad Request` | GitHub OAuth code exchange failed |

**Success Response:**
```json
{
    "message": "Login successful",
    "username": "johndoe"
}
```

**Response Headers (on success):**
```
Set-Cookie: auth_token=eyJhbGciOiJIUzI1NiIs...; Max-Age=604800; HttpOnly; Path=/; SameSite=lax
```

**Error Response (invalid/expired code):**
```json
{
    "detail": "GitHub OAuth failed: The code passed is incorrect or expired."
}
```

**Important Notes:**
- The `code` parameter is **single-use**. Once exchanged for a token, it cannot be reused.
- The `code` expires after **10 minutes** if not used.
- The `client_secret` is never exposed to the client — it is only used server-side.

**Source file:** `api/auth.py`

---

### GET /me

Returns the currently authenticated user's information. This is useful for verifying that the login was successful and the cookie is working.

**Authentication:** Required (cookie: `auth_token`)

**Request:**
```
GET /me
```

**What happens step by step:**

1. The `get_current_user` dependency reads the `auth_token` cookie from the request.
2. It decodes the JWT and verifies the signature using `JWT_SECRET`.
3. It checks that the token hasn't expired.
4. If valid, the decoded payload is returned to the endpoint.
5. The endpoint extracts `username` and `avatar_url` from the payload and returns them.

**Response:**

| Status | Description |
|---|---|
| `200 OK` | User info returned |
| `401 Unauthorized` | Not authenticated / Token expired / Invalid token |

**Success Response:**
```json
{
    "username": "johndoe",
    "avatar_url": "https://avatars.githubusercontent.com/u/12345"
}
```

**Error Responses:**

Not authenticated (no cookie):
```json
{
    "detail": "Not authenticated"
}
```

Token expired (cookie is older than 7 days):
```json
{
    "detail": "Token expired"
}
```

Token tampered with or malformed:
```json
{
    "detail": "Invalid token"
}
```

**Source file:** `app.py` (endpoint), `api/deps.py` (dependency)

---

## Repositories

### GET /repos

Fetch all repositories accessible by the authenticated user. This includes personal repositories, organization repositories (if access was granted during OAuth), and repositories the user collaborates on.

**Authentication:** Required (cookie: `auth_token`)

**Request:**
```
GET /repos
```

**What happens step by step:**

1. The `get_current_user` dependency verifies the `auth_token` cookie and extracts the `github_token`.
2. The server calls `GET https://api.github.com/user/repos` with the user's GitHub token.
3. The endpoint **paginates through all pages** (100 repos per page) to ensure every repository is returned — not just the default first 30.
4. For each repository, only the relevant fields are extracted and returned.

**GitHub API Called:**
```
GET https://api.github.com/user/repos?per_page=100&page={page}
Authorization: Bearer <github_token>
Accept: application/vnd.github+json
```

**Response:**

| Status | Description |
|---|---|
| `200 OK` | List of repositories |
| `401 Unauthorized` | Not authenticated |

**Success Response:**
```json
{
    "count": 2,
    "repos": [
        {
            "id": 123456789,
            "name": "my-project",
            "full_name": "johndoe/my-project",
            "private": false,
            "description": "A sample project",
            "url": "https://github.com/johndoe/my-project",
            "language": "Python",
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-03-20T14:45:00Z"
        },
        {
            "id": 987654321,
            "name": "private-repo",
            "full_name": "johndoe/private-repo",
            "private": true,
            "description": null,
            "url": "https://github.com/johndoe/private-repo",
            "language": "JavaScript",
            "created_at": "2024-02-10T08:00:00Z",
            "updated_at": "2024-03-18T12:00:00Z"
        }
    ]
}
```

**Response Fields:**

| Field | Type | Description |
|---|---|---|
| `count` | integer | Total number of repositories returned |
| `repos` | array | List of repository objects |
| `repos[].id` | integer | GitHub's unique repository ID |
| `repos[].name` | string | Repository name (e.g., `my-project`) |
| `repos[].full_name` | string | Full name including owner (e.g., `johndoe/my-project`) |
| `repos[].private` | boolean | Whether the repository is private |
| `repos[].description` | string or null | Repository description |
| `repos[].url` | string | URL to the repository on GitHub |
| `repos[].language` | string or null | Primary programming language |
| `repos[].created_at` | string | ISO 8601 timestamp of when the repo was created |
| `repos[].updated_at` | string | ISO 8601 timestamp of last update |

**Notes:**
- Returns **all** repos (personal + org + collaborated) depending on what the user authorized during OAuth.
- Pagination is handled automatically — no matter how many repos the user has, all are returned.

**Source file:** `api/repos.py`

---

## Issues

### GET /list-issues

List issues from a specific repository. Only returns actual issues — pull requests are filtered out (GitHub's issues endpoint includes PRs by default).

**Authentication:** Required (cookie: `auth_token`)

**Request:**
```
GET /list-issues?owner={owner}&repo={repo}&state={state}
```

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `owner` | string | Yes | — | Repository owner (GitHub username or organization name) |
| `repo` | string | Yes | — | Repository name |
| `state` | string | No | `"open"` | Filter by issue state: `open`, `closed`, or `all` |

**What happens step by step:**

1. The `get_current_user` dependency verifies the `auth_token` cookie and extracts the `github_token`.
2. The server calls `GET https://api.github.com/repos/{owner}/{repo}/issues` with the user's GitHub token.
3. The endpoint **paginates through all pages** (100 issues per page).
4. **Pull requests are filtered out.** GitHub's issues API includes pull requests in the results — this endpoint checks for the `pull_request` key and excludes those entries.
5. For each issue, only the relevant fields are extracted and returned.

**GitHub API Called:**
```
GET https://api.github.com/repos/{owner}/{repo}/issues?state={state}&per_page=100&page={page}
Authorization: Bearer <github_token>
Accept: application/vnd.github+json
```

**Response:**

| Status | Description |
|---|---|
| `200 OK` | List of issues |
| `401 Unauthorized` | Not authenticated |
| `404 Not Found` | Repository not found |

**Success Response:**
```json
{
    "count": 2,
    "issues": [
        {
            "id": 111222333,
            "number": 42,
            "title": "Bug: Login page not loading",
            "state": "open",
            "created_at": "2024-03-01T09:00:00Z",
            "updated_at": "2024-03-15T11:30:00Z",
            "user": "contributor123",
            "labels": ["bug", "high-priority"],
            "url": "https://github.com/johndoe/my-project/issues/42"
        },
        {
            "id": 444555666,
            "number": 38,
            "title": "Feature: Add dark mode",
            "state": "open",
            "created_at": "2024-02-20T15:00:00Z",
            "updated_at": "2024-02-25T10:00:00Z",
            "user": "johndoe",
            "labels": ["enhancement"],
            "url": "https://github.com/johndoe/my-project/issues/38"
        }
    ]
}
```

**Response Fields:**

| Field | Type | Description |
|---|---|---|
| `count` | integer | Total number of issues returned |
| `issues` | array | List of issue objects |
| `issues[].id` | integer | GitHub's unique issue ID |
| `issues[].number` | integer | Issue number within the repository (e.g., #42) |
| `issues[].title` | string | Issue title |
| `issues[].state` | string | Current state: `open` or `closed` |
| `issues[].created_at` | string | ISO 8601 timestamp of when the issue was created |
| `issues[].updated_at` | string | ISO 8601 timestamp of last update |
| `issues[].user` | string | GitHub username of the issue author |
| `issues[].labels` | array of strings | List of label names attached to the issue |
| `issues[].url` | string | URL to the issue on GitHub |

**Error Response (repo not found):**
```json
{
    "detail": "Repository 'johndoe/nonexistent' not found"
}
```

**Source file:** `api/issues.py`

---

### POST /create-issue

Create a new issue in a specific repository.

**Authentication:** Required (cookie: `auth_token`)

**Request:**
```
POST /create-issue
Content-Type: application/json
```

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `owner` | string | Yes | Repository owner (GitHub username or organization name) |
| `repo` | string | Yes | Repository name |
| `title` | string | Yes | Issue title (minimum 1 character) |
| `body` | string | No | Issue body/description (supports Markdown) |
| `labels` | array of strings | No | List of label names to attach to the issue |

**Example Request Body:**
```json
{
    "owner": "johndoe",
    "repo": "my-project",
    "title": "Bug: API returns 500 on empty input",
    "body": "## Steps to Reproduce\n1. Send a POST request with empty body\n2. Server returns 500\n\n## Expected Behavior\nShould return 400 with a validation error.",
    "labels": ["bug", "api"]
}
```

**Minimal Request Body (only required fields):**
```json
{
    "owner": "johndoe",
    "repo": "my-project",
    "title": "Fix typo in README"
}
```

**What happens step by step:**

1. FastAPI validates the request body using the `CreateIssueRequest` Pydantic model.
   - `owner`, `repo`, and `title` are required.
   - `title` must be at least 1 character long.
   - `body` and `labels` are optional — they are only included in the GitHub API call if provided.
2. The `get_current_user` dependency verifies the `auth_token` cookie and extracts the `github_token`.
3. The server sends a `POST` request to `https://api.github.com/repos/{owner}/{repo}/issues` with the issue data.
4. If successful, the created issue's details are returned.

**GitHub API Called:**
```
POST https://api.github.com/repos/{owner}/{repo}/issues
Authorization: Bearer <github_token>
Accept: application/vnd.github+json
Content-Type: application/json

{
    "title": "Bug: API returns 500 on empty input",
    "body": "## Steps to Reproduce\n...",
    "labels": ["bug", "api"]
}
```

**Response:**

| Status | Description |
|---|---|
| `201 Created` | Issue created successfully |
| `401 Unauthorized` | Not authenticated |
| `403 Forbidden` | No permission to create issues in this repository |
| `404 Not Found` | Repository not found |
| `410 Gone` | Issues are disabled for this repository |
| `422 Unprocessable Entity` | Validation failed (e.g., empty title) |

**Success Response:**
```json
{
    "message": "Issue created successfully",
    "issue": {
        "id": 777888999,
        "number": 43,
        "title": "Bug: API returns 500 on empty input",
        "state": "open",
        "url": "https://github.com/johndoe/my-project/issues/43",
        "created_at": "2024-03-20T16:00:00Z"
    }
}
```

**Response Fields:**

| Field | Type | Description |
|---|---|---|
| `message` | string | Confirmation message |
| `issue.id` | integer | GitHub's unique issue ID |
| `issue.number` | integer | Issue number within the repository |
| `issue.title` | string | The title of the created issue |
| `issue.state` | string | State of the issue (always `open` for newly created) |
| `issue.url` | string | URL to the created issue on GitHub |
| `issue.created_at` | string | ISO 8601 timestamp of when the issue was created |

**Error Responses:**

Repository not found:
```json
{
    "detail": "Repository 'johndoe/nonexistent' not found"
}
```

No permission:
```json
{
    "detail": "You don't have permission to create issues in this repository"
}
```

Issues disabled:
```json
{
    "detail": "Issues are disabled for this repository"
}
```

**Source file:** `api/issues.py`

---

## Commits

### GET /commits

Fetch all commits from a specific repository.

**Authentication:** Required (cookie: `auth_token`)

**Request:**
```
GET /commits?owner={owner}&repo={repo}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `owner` | string | Yes | Repository owner (GitHub username or organization name) |
| `repo` | string | Yes | Repository name |

**What happens step by step:**

1. The `get_current_user` dependency verifies the `auth_token` cookie and extracts the `github_token`.
2. The server calls `GET https://api.github.com/repos/{owner}/{repo}/commits` with the user's GitHub token.
3. The endpoint **paginates through all pages** (100 commits per page) to return the complete commit history.
4. For each commit, only the relevant fields are extracted and returned.

**GitHub API Called:**
```
GET https://api.github.com/repos/{owner}/{repo}/commits?per_page=100&page={page}
Authorization: Bearer <github_token>
Accept: application/vnd.github+json
```

**Response:**

| Status | Description |
|---|---|
| `200 OK` | List of commits |
| `401 Unauthorized` | Not authenticated |
| `404 Not Found` | Repository not found |
| `409 Conflict` | Repository is empty (no commits exist) |

**Success Response:**
```json
{
    "count": 3,
    "commits": [
        {
            "sha": "abc123def456789abc123def456789abc123def4",
            "message": "fix: resolve login redirect issue",
            "author": "John Doe",
            "date": "2024-03-20T14:30:00Z",
            "url": "https://github.com/johndoe/my-project/commit/abc123d"
        },
        {
            "sha": "def789abc123456def789abc123456def789abc1",
            "message": "feat: add dark mode support\n\nAdded CSS variables for theme switching.",
            "author": "John Doe",
            "date": "2024-03-19T10:00:00Z",
            "url": "https://github.com/johndoe/my-project/commit/def789a"
        },
        {
            "sha": "789abc123def456789abc123def456789abc123d",
            "message": "Initial commit",
            "author": "John Doe",
            "date": "2024-01-15T08:00:00Z",
            "url": "https://github.com/johndoe/my-project/commit/789abc1"
        }
    ]
}
```

**Response Fields:**

| Field | Type | Description |
|---|---|---|
| `count` | integer | Total number of commits returned |
| `commits` | array | List of commit objects (newest first) |
| `commits[].sha` | string | Full SHA hash of the commit (40 characters) |
| `commits[].message` | string | Commit message (may include multi-line body) |
| `commits[].author` | string | Name of the commit author |
| `commits[].date` | string | ISO 8601 timestamp of when the commit was authored |
| `commits[].url` | string | URL to the commit on GitHub |

**Error Responses:**

Repository not found:
```json
{
    "detail": "Repository 'johndoe/nonexistent' not found"
}
```

Empty repository:
```json
{
    "detail": "Repository is empty (no commits)"
}
```

**Notes:**
- Commits are returned in **reverse chronological order** (newest first) — this is GitHub's default behavior.
- The `message` field includes the full commit message, including the body if present (separated by `\n\n`).
- Pagination is handled automatically — the entire commit history is returned regardless of size.

**Source file:** `api/commits.py`

---

## Pull Requests

### POST /create-pull-request

Create a new pull request in a specific repository. This requires that the source branch (`head`) already exists and has commits that are not in the target branch (`base`).

**Authentication:** Required (cookie: `auth_token`)

**Request:**
```
POST /create-pull-request
Content-Type: application/json
```

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `owner` | string | Yes | Repository owner (GitHub username or organization name) |
| `repo` | string | Yes | Repository name |
| `title` | string | Yes | Pull request title (minimum 1 character) |
| `head` | string | Yes | The name of the branch that contains your changes (source branch) |
| `base` | string | Yes | The name of the branch you want to merge into (target branch, e.g., `main`) |
| `body` | string | No | Pull request description (supports Markdown) |

**Example Request Body:**
```json
{
    "owner": "johndoe",
    "repo": "my-project",
    "title": "feat: Add dark mode support",
    "head": "feature/dark-mode",
    "base": "main",
    "body": "## Changes\n- Added CSS variables for theme switching\n- Added toggle button in settings\n\n## Testing\n- Tested on Chrome, Firefox, Safari"
}
```

**Minimal Request Body (only required fields):**
```json
{
    "owner": "johndoe",
    "repo": "my-project",
    "title": "Fix typo in docs",
    "head": "fix/typo",
    "base": "main"
}
```

**What happens step by step:**

1. FastAPI validates the request body using the `CreatePullRequest` Pydantic model.
   - `owner`, `repo`, `title`, `head`, and `base` are required.
   - `title` must be at least 1 character long.
   - `body` is optional — it is only included in the GitHub API call if provided.
2. The `get_current_user` dependency verifies the `auth_token` cookie and extracts the `github_token`.
3. The server sends a `POST` request to `https://api.github.com/repos/{owner}/{repo}/pulls` with the pull request data.
4. If successful, the created pull request's details are returned.

**GitHub API Called:**
```
POST https://api.github.com/repos/{owner}/{repo}/pulls
Authorization: Bearer <github_token>
Accept: application/vnd.github+json
Content-Type: application/json

{
    "title": "feat: Add dark mode support",
    "head": "feature/dark-mode",
    "base": "main",
    "body": "## Changes\n..."
}
```

**Response:**

| Status | Description |
|---|---|
| `201 Created` | Pull request created successfully |
| `401 Unauthorized` | Not authenticated |
| `403 Forbidden` | No permission to create pull requests in this repository |
| `404 Not Found` | Repository not found |
| `422 Unprocessable Entity` | Validation failed (see common causes below) |

**Success Response:**
```json
{
    "message": "Pull request created successfully",
    "pull_request": {
        "id": 111222333,
        "number": 15,
        "title": "feat: Add dark mode support",
        "state": "open",
        "head": "feature/dark-mode",
        "base": "main",
        "url": "https://github.com/johndoe/my-project/pull/15",
        "created_at": "2024-03-20T16:30:00Z"
    }
}
```

**Response Fields:**

| Field | Type | Description |
|---|---|---|
| `message` | string | Confirmation message |
| `pull_request.id` | integer | GitHub's unique pull request ID |
| `pull_request.number` | integer | PR number within the repository (e.g., #15) |
| `pull_request.title` | string | The title of the created pull request |
| `pull_request.state` | string | State of the PR (always `open` for newly created) |
| `pull_request.head` | string | Source branch name |
| `pull_request.base` | string | Target branch name |
| `pull_request.url` | string | URL to the pull request on GitHub |
| `pull_request.created_at` | string | ISO 8601 timestamp of when the PR was created |

**Error Responses:**

Repository not found:
```json
{
    "detail": "Repository 'johndoe/nonexistent' not found"
}
```

No permission:
```json
{
    "detail": "You don't have permission to create pull requests in this repository"
}
```

Validation failed (common 422 causes):
```json
{
    "detail": "Validation Failed: No commits between main and main"
}
```

Other common 422 errors:
- `"A pull request already exists for johndoe:feature-branch"` — A PR from this branch already exists
- `"Head sha can't be blank"` — The `head` branch does not exist
- `"Base does not exist"` — The `base` branch does not exist

**Prerequisites:**
- The `head` branch must already exist in the repository with at least one commit ahead of `base`.
- The `base` branch must exist.
- There must not already be an open PR from `head` to `base`.
- The authenticated user must have push access to the repository (or it must be a fork).

**Source file:** `api/pulls.py`

---

## Error Response Format

All error responses follow the same format:

```json
{
    "detail": "Human-readable error message"
}
```

For validation errors (invalid request body), FastAPI returns:

```json
{
    "detail": [
        {
            "loc": ["body", "title"],
            "msg": "Field required",
            "type": "missing"
        }
    ]
}
```

---

## Common Error Codes

| Status Code | Meaning | Common Cause |
|---|---|---|
| `200` | Success | Request completed successfully |
| `201` | Created | Resource (issue, PR) created successfully |
| `302` | Redirect | OAuth login redirect to GitHub |
| `400` | Bad Request | OAuth code exchange failed |
| `401` | Unauthorized | Missing, expired, or invalid `auth_token` cookie |
| `403` | Forbidden | User lacks permission for this action on the repository |
| `404` | Not Found | Repository or resource does not exist |
| `409` | Conflict | Repository is empty (no commits) |
| `410` | Gone | Issues are disabled for the repository |
| `422` | Unprocessable Entity | Validation failed (invalid input, duplicate PR, branch not found) |
| `500` | Internal Server Error | Unexpected server error |
