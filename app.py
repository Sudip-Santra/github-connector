from fastapi import FastAPI, Depends
from api.health import router as health_router
from api.auth import router as auth_router
from api.repos import router as repos_router
from api.issues import router as issues_router
from api.deps import get_current_user

app = FastAPI(title="GitHub Connector")

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(repos_router)
app.include_router(issues_router)


@app.get("/me", tags=["Auth"])
def me(user: dict = Depends(get_current_user)):
    """Return the current authenticated user info."""
    return {"username": user["username"], "avatar_url": user["avatar_url"]}
