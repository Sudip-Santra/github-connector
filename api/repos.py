from fastapi import APIRouter, Depends, HTTPException
import httpx
from api.deps import get_current_user
from config import GITHUB_API_BASE_URL

router = APIRouter(tags=["Repositories"])

GITHUB_USER_REPOS_URL = f"{GITHUB_API_BASE_URL}/user/repos"


@router.get("/repos")
async def fetch_repos(user: dict = Depends(get_current_user)):
    """Fetch all repositories accessible by the authenticated user."""
    github_token = user["github_token"]

    repos = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                GITHUB_USER_REPOS_URL,
                params={"per_page": 100, "page": page},
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"GitHub API error: {response.json().get('message', 'Unknown error')}",
                )

            data = response.json()
            if not data:
                break

            repos.extend([
                {
                    "id": repo["id"],
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "private": repo["private"],
                    "description": repo["description"],
                    "url": repo["html_url"],
                    "language": repo["language"],
                    "created_at": repo["created_at"],
                    "updated_at": repo["updated_at"],
                }
                for repo in data
            ])

            page += 1

    return {"count": len(repos), "repos": repos}
