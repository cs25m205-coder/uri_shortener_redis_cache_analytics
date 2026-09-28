import os
import random
import string

import redis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import URL
from .schemas import CreateURLRequest, CreateURLResponse, URLStatsResponse


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI(
    title="URL Shortener",
    description="A simple URL shortener with PostgreSQL persistence and Redis caching.",
    version="1.0.0",
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


def generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/urls", response_model=CreateURLResponse)
def create_short_url(
    payload: CreateURLRequest,
    db: Session = Depends(get_db),
):
    for _ in range(5):
        code = generate_code()

        if db.query(URL).filter(URL.short_code == code).first():
            continue

        item = URL(
            original_url=str(payload.url),
            short_code=code,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        return {
            "short_code": item.short_code,
            "short_url": f"{BASE_URL}/{item.short_code}",
        }

    raise HTTPException(
        status_code=500,
        detail="Could not generate a unique short code",
    )


@app.get("/{short_code}")
def redirect_to_original(
    short_code: str,
    db: Session = Depends(get_db),
):
    cache_key = f"url:{short_code}"

    # Cache hit: avoid another URL lookup in PostgreSQL.
    cached_url = redis_client.get(cache_key)

    if cached_url:
        item = db.query(URL).filter(URL.short_code == short_code).first()

        if not item:
            redis_client.delete(cache_key)
            raise HTTPException(status_code=404, detail="Short URL not found")

        item.click_count += 1
        db.commit()

        return RedirectResponse(cached_url, status_code=307)

    # Cache miss: PostgreSQL is the persistent source of truth.
    item = db.query(URL).filter(URL.short_code == short_code).first()

    if not item:
        raise HTTPException(status_code=404, detail="Short URL not found")

    redis_client.setex(cache_key, 3600, item.original_url)

    item.click_count += 1
    db.commit()

    return RedirectResponse(item.original_url, status_code=307)


@app.get(
    "/api/urls/{short_code}/stats",
    response_model=URLStatsResponse,
)
def get_stats(
    short_code: str,
    db: Session = Depends(get_db),
):
    item = db.query(URL).filter(URL.short_code == short_code).first()

    if not item:
        raise HTTPException(status_code=404, detail="Short URL not found")

    return item
