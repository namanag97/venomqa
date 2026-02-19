# Tutorials

Step-by-step guides for common testing scenarios with VenomQA.

## Getting Started

<div class="feature-grid" markdown>

<div class="feature-card" markdown>

### [Your First Journey](first-journey.md)

Create a complete journey from scratch, covering authentication, CRUD operations, and error handling.

**Time:** 15 minutes

</div>

<div class="feature-card" markdown>

### [Testing Payment Flows](payment-flows.md)

Use checkpoints and branching to test multiple payment methods from a single setup.

**Time:** 20 minutes

</div>

<div class="feature-card" markdown>

### [CI/CD Integration](ci-cd.md)

Set up VenomQA in GitHub Actions, GitLab CI, and other CI/CD systems.

**Time:** 10 minutes

</div>

</div>

## Prerequisites

Before starting these tutorials, ensure you have:

- [x] VenomQA installed (`pip install venomqa`)
- [x] A running API to test (or use the example server below)
- [x] Basic Python knowledge

## Example Test Server

For tutorials, you can use this simple FastAPI server:

```python
# server.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
from datetime import datetime, timedelta

app = FastAPI()
security = HTTPBearer()

# In-memory storage (for demo)
users = {"test@example.com": {"password": "secret123", "name": "Test User"}}
items = {}
carts = {}

SECRET_KEY = "your-secret-key"

class LoginRequest(BaseModel):
    email: str
    password: str

class ItemCreate(BaseModel):
    name: str
    price: float

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/api/auth/login")
def login(request: LoginRequest):
    user = users.get(request.email)
    if not user or user["password"] != request.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = jwt.encode(
        {"email": request.email, "exp": datetime.utcnow() + timedelta(hours=1)},
        SECRET_KEY,
        algorithm="HS256"
    )
    return {"token": token, "user": {"email": request.email, "name": user["name"]}}

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload["email"]
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/api/users/me")
def get_profile(email: str = Depends(get_current_user)):
    user = users.get(email)
    return {"email": email, "name": user["name"]}

@app.post("/api/items")
def create_item(item: ItemCreate, email: str = Depends(get_current_user)):
    item_id = len(items) + 1
    items[item_id] = {"id": item_id, **item.dict(), "owner": email}
    return items[item_id]

@app.get("/api/items/{item_id}")
def get_item(item_id: int):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    return items[item_id]

@app.delete("/api/items/{item_id}")
def delete_item(item_id: int, email: str = Depends(get_current_user)):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    del items[item_id]
    return {"status": "deleted"}

# Run with: uvicorn server:app --reload
```

Start the server:

```bash
pip install fastapi uvicorn pyjwt
uvicorn server:app --reload
```

## Tutorial Structure

Each tutorial follows this structure:

1. **Goal**: What you'll build
2. **Prerequisites**: What you need
3. **Steps**: Detailed instructions
4. **Code**: Complete working examples
5. **Next Steps**: Where to go from here

## Quick Links

| Tutorial | Level | Time | Topics |
|----------|-------|------|--------|
| [Your First Journey](first-journey.md) | Beginner | 15 min | Basics, Steps, Context |
| [Testing Payment Flows](payment-flows.md) | Intermediate | 20 min | Checkpoints, Branching |
| [CI/CD Integration](ci-cd.md) | Intermediate | 10 min | GitHub Actions, JUnit |

## Need Help?

- Check the [FAQ](../faq.md) for common questions
- See [Examples](../examples/index.md) for more code samples
- Join our [Discord](https://discord.gg/venomqa) for community support
