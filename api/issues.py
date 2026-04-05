from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import httpx
from api.deps import get_current_user
from config import GITHUB_API_BASE_URL


class CreateIssueRequest(BaseModel):
    owner: str = Field(..., description="Repository owner (user or org)")
    repo: str = Field(..., description="Repository name")
    title: str = Field(..., min_length=1, description="Issue title")
    body: Optional[str] = Field(None, description="Issue body/description")
    labels: Optional[list[str]] = Field(None, description="List of label names")

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


@router.post("/create-issue", status_code=201)
async def create_issue(
    payload: CreateIssueRequest,
    user: dict = Depends(get_current_user),
):
    """Create an issue in a repository."""
    github_token = user["github_token"]
    url = f"{GITHUB_API_BASE_URL}/repos/{payload.owner}/{payload.repo}/issues"

    body = {"title": payload.title}
    if payload.body:
        body["body"] = payload.body
    if payload.labels:
        body["labels"] = payload.labels

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
        raise HTTPException(status_code=403, detail="You don't have permission to create issues in this repository")

    if response.status_code == 410:
        raise HTTPException(status_code=410, detail="Issues are disabled for this repository")

    if response.status_code not in (201,):
        raise HTTPException(
            status_code=response.status_code,
            detail=f"GitHub API error: {response.json().get('message', 'Unknown error')}",
        )

    issue = response.json()
    return {
        "message": "Issue created successfully",
        "issue": {
            "id": issue["id"],
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "url": issue["html_url"],
            "created_at": issue["created_at"],
        },
    }
