"""Lightweight models over the (unstable) Zhihu API payloads.

All models allow extra fields so that upstream additions never break the CLI.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class Author(_Base):
    name: str = ""
    url_token: str = ""
    headline: str = ""
    avatar_url: str = Field(default="", alias="avatar_url")


class Answer(_Base):
    id: int | None = None
    content: str = ""
    excerpt: str = ""
    voteup_count: int = 0
    comment_count: int = 0
    created_time: int = 0
    updated_time: int = 0
    url: str = ""
    author: Author = Field(default_factory=Author)
    question: dict = Field(default_factory=dict)

    @property
    def question_title(self) -> str:
        return str(self.question.get("title", "")) if isinstance(self.question, dict) else ""


class Question(_Base):
    id: int | None = None
    title: str = ""
    detail: str = ""
    answer_count: int = 0
    follower_count: int = 0
    comment_count: int = 0
    url: str = ""


class Article(_Base):
    id: int | None = None
    title: str = ""
    content: str = ""
    excerpt: str = ""
    voteup_count: int = 0
    comment_count: int = 0
    created: int = 0
    updated: int = 0
    url: str = ""
    author: Author = Field(default_factory=Author)


class Member(_Base):
    id: str = ""
    name: str = ""
    url_token: str = ""
    headline: str = ""
    description: str = ""
    answer_count: int = 0
    articles_count: int = 0
    followers_count: int = 0
    following_count: int = 0
    avatar_url: str = ""
