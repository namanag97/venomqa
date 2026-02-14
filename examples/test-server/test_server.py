"""Simple FastAPI test server for VenomQA testing.

Run with: uvicorn test_server:app --host 0.0.0.0 --port 8001 --reload
"""

from datetime import datetime
from typing import Optional
import uuid

from fastapi import FastAPI, HTTPException, Header, Depends, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

app = FastAPI(title="VenomQA Test API", version="1.0.0")

security = HTTPBearer(auto_error=False)

# In-memory storage
users_db: dict[str, dict] = {}
items_db: dict[str, dict] = {}
tokens_db: dict[str, str] = {}  # token -> user_id


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool = True
    created_at: datetime


class ItemCreate(BaseModel):
    title: str
    description: Optional[str] = None


class ItemResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    owner_id: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Message(BaseModel):
    message: str


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    if token not in tokens_db:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = tokens_db[token]
    if user_id not in users_db:
        raise HTTPException(status_code=401, detail="User not found")

    return users_db[user_id]


@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/v1/utils/health-check/")
def api_health_check():
    return {"status": "ok"}


@app.post("/api/v1/users/signup", response_model=UserResponse)
def signup(user: UserCreate):
    # Check if email exists
    for u in users_db.values():
        if u["email"] == user.email:
            raise HTTPException(status_code=409, detail="Email already registered")

    user_id = str(uuid.uuid4())
    users_db[user_id] = {
        "id": user_id,
        "email": user.email,
        "full_name": user.full_name,
        "password": user.password,  # In real app, this would be hashed
        "is_active": True,
        "created_at": datetime.now(),
    }

    return users_db[user_id]


@app.post("/api/v1/login/access-token", response_model=Token)
def login(
    username: str = Form(None),
    password: str = Form(None),
):
    # username field is used for email in OAuth2 password flow
    login_email = username

    if not login_email or not password:
        raise HTTPException(status_code=422, detail="Email and password required")

    # Find user
    user = None
    for u in users_db.values():
        if u["email"] == login_email:
            user = u
            break

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate token
    token = f"token-{uuid.uuid4()}"
    tokens_db[token] = user["id"]

    return Token(access_token=token)


@app.post("/api/v1/login/test-token")
def test_token(current_user: dict = Depends(get_current_user)):
    return {"email": current_user["email"], "id": current_user["id"]}


@app.get("/api/v1/users/me", response_model=UserResponse)
def get_current_user_endpoint(current_user: dict = Depends(get_current_user)):
    return current_user


@app.patch("/api/v1/users/me", response_model=UserResponse)
def update_current_user(
    full_name: Optional[str] = None,
    email: Optional[EmailStr] = None,
    password: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    if full_name is not None:
        current_user["full_name"] = full_name
    if email is not None:
        # Check if email is taken
        for u in users_db.values():
            if u["email"] == email and u["id"] != current_user["id"]:
                raise HTTPException(status_code=409, detail="Email already in use")
        current_user["email"] = email
    if password is not None:
        current_user["password"] = password

    return current_user


@app.delete("/api/v1/users/me")
def delete_current_user(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    # Delete user's items
    items_to_delete = [iid for iid, item in items_db.items() if item["owner_id"] == user_id]
    for iid in items_to_delete:
        del items_db[iid]

    # Delete user's tokens
    tokens_to_delete = [t for t, uid in tokens_db.items() if uid == user_id]
    for t in tokens_to_delete:
        del tokens_db[t]

    # Delete user
    del users_db[user_id]

    return {"message": "User deleted"}


@app.post("/api/v1/items/", response_model=ItemResponse)
def create_item(
    item: ItemCreate,
    current_user: dict = Depends(get_current_user),
):
    item_id = str(uuid.uuid4())
    items_db[item_id] = {
        "id": item_id,
        "title": item.title,
        "description": item.description,
        "owner_id": current_user["id"],
        "created_at": datetime.now(),
    }

    return items_db[item_id]


@app.get("/api/v1/items/")
def list_items(
    limit: int = 10,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    user_items = [item for item in items_db.values() if item["owner_id"] == current_user["id"]]

    # Apply pagination
    paginated = user_items[skip : skip + limit]

    return {"data": paginated, "count": len(user_items)}


@app.get("/api/v1/items/{item_id}", response_model=ItemResponse)
def get_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    item = items_db[item_id]

    if item["owner_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this item")

    return item


@app.put("/api/v1/items/{item_id}", response_model=ItemResponse)
def update_item(
    item_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    item = items_db[item_id]

    if item["owner_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to modify this item")

    if title is not None:
        item["title"] = title
    if description is not None:
        item["description"] = description

    return item


@app.delete("/api/v1/items/{item_id}")
def delete_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    item = items_db[item_id]

    if item["owner_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this item")

    del items_db[item_id]

    return {"message": "Item deleted"}


@app.get("/api/v1/admin/stats")
def get_stats(current_user: dict = Depends(get_current_user)):
    """Admin endpoint - returns 403 for non-superusers."""
    return {
        "users_count": len(users_db),
        "items_count": len(items_db),
        "active_tokens": len(tokens_db),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
