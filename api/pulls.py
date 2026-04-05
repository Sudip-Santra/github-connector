from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx
from api.deps import get_current_user
from config import GITHUB_API_BASE_URL

router = APIRouter(tags=["Pull Requests"])


class CreatePullRequest(BaseModel):
    owner: str = Field(..., description="Repository owner (user or org)")
    repo: str = Field(..., description="Repository name")
    title: str = Field(..., min_length=1, description="Pull request title")
    head: str = Field(..., description="The branch that contains your changes")
    base: str = Field(..., description="The branch you want to merge into")
    body: Optional[str] = Field(None, description="Pull request description")


@router.post("/create-pull-request", status_code=201)
async def create_pull_request(
    payload: CreatePullRequest,
    user: dict = Depends(get_current_user),
):
    """Create a pull request in a repository."""
    github_token = user["github_token"]
    url = f"{GITHUB_API_BASE_URL}/repos/{payload.owner}/{payload.repo}/pulls"

    body = {
        "title": payload.title,
        "head": payload.head,
        "base": payload.base,
    }
    if payload.body:
        body["body"] = payload.body

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Repository '{payload.owner}/{payload.repo}' not found")

    if response.status_code == 403:
        raise HTTPException(status_code=403, detail="You don't have permission to create pull requests in this repository")

    if response.status_code == 422:
        errors = response.json().get("errors", [])
        message = response.json().get("message", "Validation failed")
        detail = f"{message}: {errors[0].get('message')}" if errors else message
        raise HTTPException(status_code=422, detail=detail)

    if response.status_code != 201:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"GitHub API error: {response.json().get('message', 'Unknown error')}",
        )

    pr = response.json()
    return {
        "message": "Pull request created successfully",
        "pull_request": {
            "id": pr["id"],
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "head": pr["head"]["ref"],
            "base": pr["base"]["ref"],
            "url": pr["html_url"],
            "created_at": pr["created_at"],
        },
    }
