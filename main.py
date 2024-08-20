import os
import shutil
from fastapi.responses import FileResponse
from collections import defaultdict
from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File

import models, schemas, auth
from database import engine, get_db
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# UPLOAD_DIRECTORY = "profile"

# if not os.path.exists(UPLOAD_DIRECTORY):
#     os.makedirs(UPLOAD_DIRECTORY)


@app.on_event("startup")
async def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(reset_todos, CronTrigger(hour=0, minute=0))
    scheduler.add_job(delete_expired_todos, CronTrigger(hour=0, minute=0))
    scheduler.add_job(get_calendar_status, CronTrigger(hour=0, minute=0))
    scheduler.start()


async def reset_todos():
    db = next(get_db())
    todos = db.query(models.Todo).all()
    for todo in todos:
        todo.completed = False
    db.commit()
    db.close()


async def delete_expired_todos():
    db = next(get_db())
    today = date.today()
    expired_todos = db.query(models.Todo).filter(models.Todo.end_date < today).all()
    for todo in expired_todos:
        db.delete(todo)
    db.commit()
    db.close()


@app.post("/token", response_model=dict)
def access(token_request: schemas.TokenRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == token_request.username).first()
    if not user or not auth.verify_password(token_request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.username})
    refresh_token = auth.create_refresh_token(data={"sub": user.username})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@app.post("/token/refresh", response_model=dict)
def refresh(refresh_token_request: schemas.RefreshTokenRequest):
    user_info = auth.decode_refresh_token(refresh_token_request.refresh_token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user_info["sub"]})
    return {"access_token": access_token}


@app.post("/user", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(username=user.username, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.post("/todo", response_model=schemas.Todo)
async def create_todo(
        todo: schemas.TodoCreate,
        db: Session = Depends(get_db),
        token: str = Depends(oauth2_scheme)
):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    db_todo = models.Todo(
        title=todo.title,
        start_date=todo.start_date,
        end_date=todo.end_date,
        creator_id=user.id
    )
    db.add(db_todo)
    db.commit()
    db.refresh(db_todo)
    return db_todo


@app.get("/todo", response_model=List[schemas.Todo])
def read_todos(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    todos = db.query(models.Todo).filter(models.Todo.creator_id == user.id).all()
    return todos


@app.put("/todo/{todo_id}/complete", response_model=schemas.Todo)
def update_todo(
        todo_id: int,
        todo_update: schemas.TodoUpdate,
        db: Session = Depends(get_db),
        token: str = Depends(oauth2_scheme)
):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

    todo = db.query(models.Todo).filter(models.Todo.id == todo_id).first()

    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    todo.completed = todo_update.completed
    db.commit()
    db.refresh(todo)

    return todo


@app.post("/group", response_model=schemas.Group)
def create_group(group: schemas.GroupCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db_group = models.Group(name=group.name, creator_id=user.id)
    db_group.members.append(user)
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group


@app.delete("/group/{group_id}", response_model=schemas.Group)
def delete_group(group_id: int, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    db_group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if db_group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    if db_group.creator_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this group")
    db.delete(db_group)
    db.commit()
    return db_group


@app.post("/group/{group_id}/join", response_model=schemas.Group)
def join_group(group_id: int, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    db_group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if db_group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    db_group.members.append(user)
    db.commit()
    db.refresh(db_group)
    return db_group


@app.post("/group/{group_id}/leave", response_model=schemas.Group)
def leave_group(group_id: int, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    db_group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if db_group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    db_group.members.remove(user)
    db.commit()
    db.refresh(db_group)
    return db_group


@app.get("/group/joined", response_model=List[schemas.Group])
def get_joined(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user.groups


@app.get("/group/not-joined", response_model=List[schemas.Group])
def get_not_joined(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    joined_groups = [group.id for group in user.groups]
    not_joined_groups = db.query(models.Group).filter(models.Group.id.notin_(joined_groups)).all()
    return not_joined_groups


@app.get("/group/{group_id}/members", response_model=List[schemas.User])
def get_group_members(group_id: int, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    db_group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if db_group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return db_group.members


@app.get("/calendar-status", response_model=List[schemas.CalendarStatus])
def get_calendar_status(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    todos = db.query(models.Todo).filter(models.Todo.creator_id == user.id).all()

    today = date.today()
    date_status = defaultdict(lambda: "성공")

    for todo in todos:
        for current_date in range((todo.end_date - todo.start_date).days + 1):
            day = todo.start_date + timedelta(days=current_date)

            if day > today:
                date_status[day] = "예정"
            elif day == today:
                if not all(todo.completed for todo in todos if todo.start_date <= today <= todo.end_date):
                    date_status[day] = "도전"
                else:
                    date_status[day] = "성공"
            else:
                if not todo.completed:
                    date_status[day] = "실패"
                else:
                    date_status[day] = "성공"

    if all(todo.completed for todo in todos if todo.start_date <= today <= todo.end_date):
        if today in date_status:
            date_status[today] = "성공"

    calendar_status = [{"date": day, "status": status} for day, status in sorted(date_status.items())]
    return calendar_status


# @app.post("/profile", response_model=dict)
# async def upload_profile(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme),
#                          file: UploadFile = File(...)):
#     user_info = auth.decode_access_token(token)
#     if user_info is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid authentication credentials",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#
#     user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
#     if user is None:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     if not file.filename.endswith((".jpg", ".jpeg", ".png")):
#         raise HTTPException(
#             status_code=400, detail="Invalid file type"
#         )
#
#     file_path = os.path.join(UPLOAD_DIRECTORY, f"{file.filename}")
#
#     with open(file_path, "wb") as f:
#         shutil.copyfileobj(file.file, f)
#
#     user.profile = file_path
#     db.commit()
#
#     return {"filename": file.filename, "file_path": file_path}
#
#
# @app.get("/profile", response_model=schemas.User)
# async def get_profile(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
#     user_info = auth.decode_access_token(token)
#     if user_info is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid authentication credentials",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#
#     user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     if not user.profile:
#         raise HTTPException(status_code=404, detail="Profile not found")
#
#     return FileResponse(user.profile)
#
#
# @app.put("/profile", response_model=dict)
# async def update_profile(file: UploadFile = File(...), db: Session = Depends(get_db),
#                          token: str = Depends(oauth2_scheme)):
#     user_info = auth.decode_access_token(token)
#     if user_info is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid authentication credentials",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#
#     user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     if user.profile and os.path.exists(user.profile):
#         os.remove(user.profile)
#
#     file_path = os.path.join(UPLOAD_DIRECTORY, f"{file.filename}")
#     with open(file_path, "wb") as f:
#         shutil.copyfileobj(file.file, f)
#
#     user.profile = file_path
#     db.commit()
#
#     return {"filename": file.filename, "file_path": file_path}
#
#
# @app.delete("/profile", response_model=dict)
# async def delete_profile(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
#     user_info = auth.decode_access_token(token)
#     if user_info is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid authentication credentials",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#
#     user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     if user.profile and os.path.exists(user.profile):
#         os.remove(user.profile)
#
#     user.profile = None
#     db.commit()
#
#     return {"filename": user.profile, "file_path": user.profile}
