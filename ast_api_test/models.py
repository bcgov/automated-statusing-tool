from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field, BaseModel


class User(BaseModel):
    __tablename__ = "users"

    id: int
    username: str
    email: str
    image_file: str | None = None
    post_ids: list[str] = []

    @property
    def image_path(self) -> str:
        if self.image_file:
            return f"/media/profile_pics/{self.image_file}"
        return "/static/profile_pics/default.jpg"


class Post(BaseModel):
    __tablename__ = "posts"

    id: str
    title: str = Field(max_length=100)
    content: str
    user_id: str
    date_posted: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )