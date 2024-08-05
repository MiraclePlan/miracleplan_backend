from pydantic import BaseModel
from datetime import date
from typing import List

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int

    class Config:
        orm_mode = True

class TodoBase(BaseModel):
    title: str
    start_date: date
    end_date: date
    completed: bool = False

class TodoCreate(TodoBase):
    pass

class TodoUpdate(TodoBase):
    completed: bool

class Todo(TodoBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class GroupBase(BaseModel):
    name: str

class GroupCreate(GroupBase):
    pass

class Group(GroupBase):
    id: int
    members: List[User] = []

    class Config:
        orm_mode = True

class TokenRequest(BaseModel):
    username: str
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str
