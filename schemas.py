"""
Database Schemas for ChapterSmith AI

Each Pydantic model corresponds to a MongoDB collection. The collection name is the lowercase
form of the class name (e.g., Project -> "project").
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class Chapter(BaseModel):
    number: int = Field(..., ge=1, description="Chapter number starting at 1")
    title: str = Field(..., min_length=1, description="Chapter title")
    text: str = Field(..., min_length=1, description="Full chapter text")
    word_count: int = Field(..., ge=0, description="Computed word count for the chapter")
    pov: Literal["female", "male"] = Field("female", description="Resolved POV for this chapter")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Project(BaseModel):
    name: str = Field(..., description="Project name provided by user")
    outline: str = Field(..., description="User provided outline text or bullet list")
    chapter_count: int = Field(..., ge=3, le=6, description="Number of chapters 3-6")
    pov_mode: Literal["female", "male", "dual"] = Field("female", description="POV strategy for the story")
    genre: Optional[Literal["billionaire", "werewolf", "mafia", "general"]] = Field("general", description="Optional genre to bias tone")
    rules: Optional[str] = Field(None, description="Extra writing rules provided by user")
    chapters: List[Chapter] = Field(default_factory=list, description="Generated chapters")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# Additional simple models for requests
class CreateProjectRequest(BaseModel):
    name: str
    outline: str
    chapter_count: int
    pov_mode: Literal["female", "male", "dual"] = "female"
    genre: Optional[Literal["billionaire", "werewolf", "mafia", "general"]] = "general"
    rules: Optional[str] = None


class EditChapterRequest(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None


class GenerateChapterRequest(BaseModel):
    chapter_number: int
    user_instructions: Optional[str] = None

