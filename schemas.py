from pydantic import BaseModel
from typing import List, Optional
from datetime import date


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    password: str
    profile: Optional[str] = None


class User(UserBase):
    id: int
    profile: Optional[str] = None

    class Config:
        orm_mode = True


class TokenRequest(BaseModel):
    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TodoBase(BaseModel):
    title: str
    start_date: date
    end_date: date


class TodoCreate(TodoBase):
    pass

class TodoUpdate(BaseModel):
    completed: bool = False

class Todo(TodoBase):
    id: int
    creator_id: int
    completed: bool = False

    class Config:
        orm_mode = True


class GroupBase(BaseModel):
    name: str


class GroupCreate(GroupBase):
    pass


class Group(GroupBase):
    id: int
    creator_id: int
    members: List[User] = []

    class Config:
        orm_mode = True


class CalendarStatus(BaseModel):
    date: date
    status: str

    class Config:
        orm_mode = True
