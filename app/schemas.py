from datetime import datetime

from pydantic import BaseModel, HttpUrl


class CreateURLRequest(BaseModel):
    url: HttpUrl


class CreateURLResponse(BaseModel):
    short_code: str
    short_url: str


class URLStatsResponse(BaseModel):
    short_code: str
    original_url: str
    click_count: int
    created_at: datetime
