"""
Full-Featured FastAPI Application for VenomQA Demo.

This application demonstrates all features that VenomQA can test:
- CRUD endpoints
- WebSocket endpoint
- File upload/download
- Background jobs (Celery-like)
- Email sending
- Rate limiting
- Caching
- Search endpoint
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import redis.asyncio as redis
from celery import Celery
from celery.result import AsyncResult
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, select, update, delete
from sqlalchemy.orm import Session, sessionmaker

from models import Base, Item, Order, User, SearchIndex
from workers import send_email_task, process_order_task, generate_report_task

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://appuser:apppass@localhost:5432/appdb")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
SMTP_HOST = os.getenv("SMTP_HOST", "mailhog")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

celery_app = Celery("workers", broker=CELERY_BROKER_URL, backend=CELERY_BROKER_URL)


class ItemCreate(BaseModel):
    name: str
    description: str | None = None
    price: float
    quantity: int = 1


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    quantity: int | None = None


class ItemResponse(BaseModel):
    id: int
    name: str
    description: str | None
    price: float
    quantity: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    user_id: int
    item_ids: list[int]
    shipping_address: str


class OrderResponse(BaseModel):
    id: int
    user_id: int
    status: str
    total: float
    created_at: datetime

    class Config:
        from_attributes = True


class EmailRequest(BaseModel):
    to: EmailStr
    subject: str
    body: str
    html_body: str | None = None


class SearchQuery(BaseModel):
    query: str
    filters: dict[str, Any] | None = None
    limit: int = 10
    offset: int = 0


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = redis.from_url(REDIS_URL)
    await FastAPILimiter.init(redis_client)
    FastAPICache.init(RedisBackend(redis_client), prefix="app-cache")
    Base.metadata.create_all(bind=engine)
    yield
    await FastAPILimiter.close()
    await redis_client.close()


app = FastAPI(
    title="Full-Featured App",
    description="Demo application showcasing all VenomQA capabilities",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database not ready: {str(e)}")


@app.post("/api/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    db_item = Item(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    search_entry = SearchIndex(
        document_type="item",
        document_id=str(db_item.id),
        content=f"{db_item.name} {db_item.description or ''}",
        metadata=json.dumps({"name": db_item.name, "price": db_item.price}),
    )
    db.add(search_entry)
    db.commit()

    return db_item


@app.get("/api/items", response_model=list[ItemResponse])
@cache(expire=60)
async def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    items = db.execute(select(Item).offset(skip).limit(limit)).scalars().all()
    return items


@app.get("/api/items/{item_id}", response_model=ItemResponse)
@cache(expire=120)
async def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.execute(select(Item).where(Item.id == item_id)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.patch("/api/items/{item_id}", response_model=ItemResponse)
async def update_item(item_id: int, item: ItemUpdate, db: Session = Depends(get_db)):
    db_item = db.execute(select(Item).where(Item.id == item_id)).scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    update_data = item.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()

    db.execute(update(Item).where(Item.id == item_id).values(**update_data))
    db.commit()

    db.refresh(db_item)
    return db_item


@app.delete("/api/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, db: Session = Depends(get_db)):
    result = db.execute(delete(Item).where(Item.id == item_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    db.commit()


@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == user.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user = User(email=user.email, name=user.name, password_hash=f"hash_{user.password}")
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.get("/api/users/{user_id}", response_model=UserResponse)
@cache(expire=120)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/api/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order: OrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    items = db.execute(select(Item).where(Item.id.in_(order.item_ids))).scalars().all()
    if len(items) != len(order.item_ids):
        raise HTTPException(status_code=400, detail="Some items not found")

    total = sum(item.price * item.quantity for item in items)

    db_order = Order(
        user_id=order.user_id,
        status="pending",
        total=total,
        shipping_address=order.shipping_address,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    task = process_order_task.delay(db_order.id)
    db_order.task_id = task.id
    db.commit()

    return db_order


@app.get("/api/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/api/orders/{order_id}/status")
async def get_order_status(order_id: int, db: Session = Depends(get_db)):
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    task_status = None
    if order.task_id:
        result = AsyncResult(order.task_id, app=celery_app)
        task_status = {
            "task_id": order.task_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
        }

    return {
        "order_id": order.id,
        "order_status": order.status,
        "task_status": task_status,
    }


@app.post("/api/emails/send")
async def send_email(
    email: EmailRequest,
    background_tasks: BackgroundTasks,
):
    task = send_email_task.delay(
        to=email.to,
        subject=email.subject,
        body=email.body,
        html_body=email.html_body,
    )
    return {"message": "Email queued", "task_id": task.id}


@app.post("/api/emails/send-sync")
async def send_email_sync(email: EmailRequest):
    task = send_email_task.delay(
        to=email.to,
        subject=email.subject,
        body=email.body,
        html_body=email.html_body,
    )
    result = task.get(timeout=30)
    return {"message": "Email sent", "result": result}


@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    description: str = Form(None),
):
    content = await file.read()

    file_info = {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "description": description,
    }

    return {"message": "File uploaded successfully", "file": file_info}


@app.post("/api/files/upload-many")
async def upload_files(files: list[UploadFile] = File(...)):
    uploaded = []
    for file in files:
        content = await file.read()
        uploaded.append(
            {
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(content),
            }
        )
    return {"message": f"{len(uploaded)} files uploaded", "files": uploaded}


@app.get("/api/files/download/{filename}")
async def download_file(filename: str):
    content = f"This is the content of {filename}".encode()
    from fastapi.responses import Response

    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/search")
async def search(
    query: SearchQuery,
    db: Session = Depends(get_db),
):
    search_query = f"%{query.query}%"
    results = (
        db.execute(
            select(SearchIndex)
            .where(SearchIndex.content.ilike(search_query))
            .offset(query.offset)
            .limit(query.limit)
        )
        .scalars()
        .all()
    )

    return {
        "query": query.query,
        "total": len(results),
        "results": [
            {
                "id": r.document_id,
                "type": r.document_type,
                "content": r.content,
                "metadata": json.loads(r.metadata) if r.metadata else {},
            }
            for r in results
        ],
    }


@app.get("/api/rate-limited", dependencies=[Depends(RateLimiter(times=5, seconds=10))])
async def rate_limited_endpoint():
    return {"message": "This endpoint is rate limited to 5 requests per 10 seconds"}


@app.get("/api/cached")
@cache(expire=300)
async def cached_endpoint():
    return {
        "message": "This response is cached for 5 minutes",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.delete("/api/cache/clear")
async def clear_cache():
    await FastAPICache.clear()
    return {"message": "Cache cleared"}


@app.post("/api/jobs/generate-report")
async def generate_report(report_type: str = Query("sales", description="Type of report")):
    task = generate_report_task.delay(report_type)
    return {"message": "Report generation started", "task_id": task.id}


@app.get("/api/jobs/{task_id}")
async def get_job_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
        "traceback": result.traceback if result.failed() else None,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket.send_json(
                    {"type": "pong", "timestamp": datetime.utcnow().isoformat()}
                )
            elif message.get("type") == "broadcast":
                await manager.broadcast(
                    json.dumps(
                        {
                            "type": "broadcast",
                            "message": message.get("message"),
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                )
            else:
                await websocket.send_json(
                    {
                        "type": "echo",
                        "message": message,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/notifications")
async def notifications_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(5)
            await websocket.send_json(
                {
                    "type": "notification",
                    "message": f"Notification at {datetime.utcnow().isoformat()}",
                }
            )
    except WebSocketDisconnect:
        pass


@app.post("/api/webhooks/test")
async def test_webhook(request: Request):
    body = await request.json()
    headers = dict(request.headers)
    return {
        "received": True,
        "body": body,
        "headers": {k: v for k, v in headers.items() if k.lower().startswith("x-")},
    }


@app.get("/api/time")
async def get_server_time():
    return {
        "utc": datetime.utcnow().isoformat(),
        "timestamp": datetime.utcnow().timestamp(),
    }


@app.post("/api/batch/items")
async def batch_create_items(items: list[ItemCreate], db: Session = Depends(get_db)):
    created = []
    for item in items:
        db_item = Item(**item.model_dump())
        db.add(db_item)
        created.append(db_item)
    db.commit()
    for item in created:
        db.refresh(item)
    return {"created": len(created), "items": [ItemResponse.model_validate(i) for i in created]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
