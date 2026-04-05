from fastapi import APIRouter, Depends, HTTPException, Query
import httpx
from api.deps import get_current_user
from config import GITHUB_API_BASE_URL

router = APIRouter(tags=["Issues"])


@router.get("/list-issues")
async def list_issues(
    owner: str = Query(..., description="Repository owner (user or org)"),
    repo: str = Query(..., description="Repository name"),
    state: str = Query("open", description="Issue state: open, closed, or all"),
    user: dict = Depends(get_current_user),
):
    """List issues from a repository."""
    github_token = user["github_token"]
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues"

    issues = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                url,
                params={"state": state, "per_page": 100, "page": page},
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Repository '{owner}/{repo}' not found")

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"GitHub API error: {response.json().get('message', 'Unknown error')}",
                )

            data = response.json()
            if not data:
                break

            issues.extend([
                {
                    "id": issue["id"],
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue["state"],
                    "created_at": issue["created_at"],
                    "updated_at": issue["updated_at"],
                    "user": issue["user"]["login"],
                    "labels": [label["name"] for label in issue["labels"]],
                    "url": issue["html_url"],
                }
                for issue in data
                if "pull_request" not in issue
            ])

            page += 1

    return {"count": len(issues), "issues": issues}
