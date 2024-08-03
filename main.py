from fastapi import FastAPI, Depends, HTTPException, status
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

@app.post("/token", response_model=dict)
def login_for_access_token(token_request: schemas.TokenRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == token_request.username).first()
    if not user or not auth.verify_password(token_request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/token/refresh", response_model=dict)
def refresh_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user_info["sub"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/users", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(username=user.username, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/todos", response_model=schemas.Todo)
async def create_todo(
    todo: schemas.TodoCreate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    db_todo = models.Todo(
        title=todo.title,
        description=todo.description,
        owner_id=user.id
    )
    db.add(db_todo)
    db.commit()
    db.refresh(db_todo)
    return db_todo

@app.delete("/todos/{todo_id}", response_model=schemas.Todo)
def delete_todo(todo_id: int, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_info = auth.decode_access_token(token)
    if user_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.username == user_info["sub"]).first()
    db_todo = db.query(models.Todo).filter(models.Todo.id == todo_id, models.Todo.owner_id == user.id).first()
    if db_todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    db.delete(db_todo)
    db.commit()
    return db_todo

@app.get("/todos", response_model=List[schemas.Todo])
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

    todos = db.query(models.Todo).filter(models.Todo.owner_id == user.id).all()
    return todos