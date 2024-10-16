from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, APIRouter,Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from starlette.status import HTTP_303_SEE_OTHER
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from .database import engine, get_db
from .models import User,Task
from .schemas import UserCreate, UserLogin, TokenData,Token  # Ensure Token and TokenData schemas are defined
from sqlalchemy.exc import IntegrityError
import logging
from fastapi import Cookie
from .models import Base

# Initialize FastAPI app
app = FastAPI()
router = APIRouter()

# Setup Jinja2 for HTML templates
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# JWT configuration
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"  # Use a securely generated key in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Create password context for hashing passwords
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Create tables in the database


Base.metadata.create_all(bind=engine)

# Helper to hash passwords
def hash_password(password: str):
    return pwd_context.hash(password)

# Helper to verify passwords
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

# Helper to create access tokens
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Helper to verify tokens
# def verify_token(token: str, credentials_exception):
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         email: str = payload.get("sub")
#         if email is None:
#             raise credentials_exception
#         return TokenData(email=email)  # Return token data or user details
#     except JWTError:
#         raise credentials_exception

# Welcome page
@app.get("/", response_class=HTMLResponse)
def welcome(request: Request):
    return templates.TemplateResponse("welcome.html", {"request": request})

# Register page (GET)
@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

# Register page (POST)
@app.post("/register", response_class=HTMLResponse)
def register_user(request: Request, username: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    logging.info(f"Registering user: {username}")
    try:
        hashed_password = hash_password(password)
        user = User(username=username, email=email, password=hashed_password)
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        logging.info(f"User {username} registered successfully.")
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    except IntegrityError:
        db.rollback()
        logging.error("Username or email already exists.")
        raise HTTPException(status_code=400, detail="Username or email already exists")

# Login page (GET)
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Login page (POST)
@app.post("/login", response_class=HTMLResponse)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Check if user exists
    user = db.query(User).filter(User.username == form.username).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid username or password")
    
    # Check if password is correct
    if not pwd_context.verify(form.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    
    # Create an access token
    access_token = create_access_token(data={"sub": user.username})
    
    # Redirect to the /do_active page
    response = RedirectResponse(url="/todo", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
    key="access_token", 
    value=access_token, 
    httponly=True,  # Ensures the cookie is not accessible via JavaScript
    path="/"        # Sets the path to root so the cookie is accessible throughout the app
)

    
    return response


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")
from fastapi import Cookie
# def get_current_user(access_token: str = Cookie(None)):  # Fetch token from cookie
#     if access_token is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Not authenticated",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
    
#     credentials_exception = HTTPException(
#         status_code=status.HTTP_401_UNAUTHORIZED,
#         detail="Could not validate credentials",
#         headers={"WWW-Authenticate": "Bearer"},
#     )
    
#     # Verify the token
#     return verify_token(access_token, credentials_exception)

def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception

def get_current_user(access_token: str = Cookie(None), db: Session = Depends(get_db)):
    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Verify the token and fetch the username
    username = verify_token(access_token, credentials_exception)
    
    # Fetch the user from the database based on the username
    user = db.query(User).filter(User.username == username).first()
    
    if user is None:
        raise credentials_exception
    return user



@app.get("/todo", response_class=HTMLResponse)
def show_tasks(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tasks = db.query(Task).filter(Task.user_id == current_user.id).all()  # Filter by current user's ID
    return templates.TemplateResponse("todo.html", {"request": request, "tasks": tasks, "current_user": current_user})

# Add a new task associated with the current user
@app.post("/add_task", response_class=RedirectResponse)
def add_task(task_name: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user:
        new_task = Task(name=task_name, user_id=current_user.id)  # Associate task with current user's ID
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        return RedirectResponse(url="/todo", status_code=303)
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")


# Toggle task status (active/inactive) for the current user's tasks
@app.post("/toggle_task/{task_id}", response_class=RedirectResponse)
def toggle_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if task:
        task.is_active = not task.is_active
        db.commit()
    return RedirectResponse(url="/todo", status_code=303)

# Include the router



@app.post("/logout", response_class=RedirectResponse)
def logout(response: Response):
    # Clear the access token by setting an expired cookie with the same settings as the original
    response = RedirectResponse(url="/", status_code=HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token", httponly=True, path="/")  # Ensure the path and attributes match
    return response



