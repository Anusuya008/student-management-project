"""Student Management System - FastAPI backend (SQLite via SQLAlchemy)."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

# --------------------------------------------------------------------------- #
# Database setup
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = f"sqlite:///{BASE_DIR / 'students.db'}"

# check_same_thread=False is required for SQLite when FastAPI uses a thread pool.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    roll_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    course: Mapped[str] = mapped_column(String(100))


def get_db():
    """Provide one database session per request and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class StudentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    roll_number: str = Field(min_length=1, max_length=30)
    email: EmailStr
    course: str = Field(min_length=1, max_length=100)


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    roll_number: str
    email: str
    course: str


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Student Management System", version="1.0.0", lifespan=lifespan)

# Allows index.html to work even when opened directly from disk (file://).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def serve_frontend():
    """Serve the single-page UI so it can be opened at http://127.0.0.1:8000"""
    return FileResponse(BASE_DIR / "index.html")


@app.post("/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Student).where(Student.roll_number == payload.roll_number)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Roll number {payload.roll_number} is already registered.",
        )
    if db.scalar(select(Student).where(Student.email == payload.email)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The email {payload.email} is already registered.",
        )

    student = Student(**payload.model_dump())
    db.add(student)
    try:
        db.commit()
    except IntegrityError:  # Safety net for race conditions on unique columns.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A student with this roll number or email already exists.",
        )
    db.refresh(student)
    return student


@app.get("/students", response_model=List[StudentOut])
def list_students(db: Session = Depends(get_db)):
    return db.scalars(select(Student).order_by(Student.id.desc())).all()


@app.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(student_id: int, db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found.")
    db.delete(student)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
