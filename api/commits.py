from fastapi import APIRouter, Depends, HTTPException, Query
import httpx
from api.deps import get_current_user
from config import GITHUB_API_BASE_URL

router = APIRouter(tags=["Commits"])


@router.get("/commits")
async def fetch_commits(
    owner: str = Query(..., description="Repository owner (user or org)"),
    repo: str = Query(..., description="Repository name"),
    user: dict = Depends(get_current_user),
):
    """Fetch commits from a repository."""
    github_token = user["github_token"]
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/commits"

    commits = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                url,
                params={"per_page": 100, "page": page},
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Repository '{owner}/{repo}' not found")

            if response.status_code == 409:
                raise HTTPException(status_code=409, detail="Repository is empty (no commits)")

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"GitHub API error: {response.json().get('message', 'Unknown error')}",
                )

            data = response.json()
            if not data:
                break

            commits.extend([
                {
                    "sha": commit["sha"],
                    "message": commit["commit"]["message"],
                    "author": commit["commit"]["author"]["name"],
                    "date": commit["commit"]["author"]["date"],
                    "url": commit["html_url"],
                }
                for commit in data
            ])

            page += 1

    return {"count": len(commits), "commits": commits}
