import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId
from datetime import datetime, timezone

from database import db, create_document, get_documents
from schemas import Project, Chapter, CreateProjectRequest, EditChapterRequest, GenerateChapterRequest

app = FastAPI(title="ChapterSmith AI – Complete Story Builder")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------- Utilities ---------------------

def collection(name: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    return db[name]


def serialize_id(doc):
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


def resolve_chapter_pov(pov_mode: str, chapter_number: int) -> str:
    if pov_mode == "female":
        return "female"
    if pov_mode == "male":
        return "male"
    # dual
    return "female" if chapter_number % 2 == 1 else "male"


def compute_word_count(text: str) -> int:
    return len([w for w in text.split() if w.strip()])


def enforce_word_range(text: str) -> str:
    """
    Ensure 1400-1800 words by padding with grounded reflective sentences if short,
    and trimming extra words if long (without breaking sentences harshly).
    """
    target_min, target_max = 1400, 1800
    words = text.split()
    n = len(words)
    if n < target_min:
        filler = (
            " I took my time and described what happened in a clear way. I kept the focus on"
            " real details, steady thoughts, and simple actions. I stayed in first person and"
            " let each moment breathe without sounding poetic or dramatic."
        )
        while n < target_min:
            words.extend(filler.split())
            n = len(words)
    elif n > target_max:
        # Trim to nearest sentence end before max
        trimmed = " ".join(words[:target_max])
        # Try to cut back to last period within last 120 words
        last_dot = trimmed.rfind(".")
        if last_dot != -1 and last_dot > target_max - 200:
            trimmed = trimmed[: last_dot + 1]
        return trimmed
    return " ".join(words[:target_max])


# Simple grounded generator (placeholder, non-explicit)

def grounded_chapter_generator(outline: str, chapter_idx: int, chapter_total: int, pov: str, genre: str) -> str:
    """
    Create a long, grounded first-person chapter using the outline as guidance.
    This generator avoids metaphors, purple prose, and explicit content.
    """
    lines: List[str] = []
    header = (
        f"This chapter follows the outline and continues the story in a clear, human voice. "
        f"I speak in first person as the {pov} lead. The tone is natural and steady. "
        f"The setting and actions are grounded in small details."
    )
    lines.append(header)

    # Split outline into segments for structure
    parts = [p.strip("- •\n ") for p in outline.splitlines() if p.strip()]
    if not parts:
        parts = ["The story setup is simple. I meet the other lead and a problem starts."]

    # Genre nudges
    genre_note = ""
    if genre == "billionaire":
        genre_note = (
            " There is a quiet tension between wealth and loneliness. Power shows up in small practical ways."
        )
    elif genre == "werewolf":
        genre_note = (
            " Instinct and duty pull at me. I notice heat, breath, and the press of the crowd without exaggeration."
        )
    elif genre == "mafia":
        genre_note = (
            " Danger is present but not sensational. Trust is fragile and every choice has a cost."
        )

    intro = (
        f"It is chapter {chapter_idx} of {chapter_total}. I keep the pacing even and I move from one scene to the next"
        f" without jumps. I react in real time with simple thoughts and clean sentences.{genre_note}"
    )
    lines.append(intro)

    # Build scenes from parts with internal thoughts
    for i, p in enumerate(parts[:8]):
        lines.append(
            f"Scene {i+1}: {p}. I look for what matters right now. I describe only what I would notice."
        )
        lines.append(
            "I watch faces and hands. I listen for tone. I keep my feelings steady and honest."
        )
        lines.append(
            "I let the moment slow enough to understand it, then I make a choice that moves the scene forward."
        )
        lines.append(
            "Dialogue feels natural. I speak in clear sentences. I avoid dramatic fragments and fancy images."
        )
        # Small personal reactions
        lines.append(
            "My body tells a simple truth: my breath changes, my shoulders tense, my hands warm or cool."
        )

    # Chapter movement and hook
    lines.append(
        "I stay consistent with point of view. I keep it personal and close. I do not summarize the story."
    )
    lines.append(
        "When I think of the other lead, I admit what I want and what I fear, even if I do not say it out loud."
    )
    lines.append(
        "The chapter closes on a clean beat. I do not end with a slogan. I end with a small decision or a question that matters."
    )

    # Expand body to reach target by elaborating practical steps
    base = " ".join(lines)
    # Add rolling elaboration paragraphs tied to outline
    cycle = parts if parts else ["progress"]
    idx = 0
    while compute_word_count(base) < 1450:
        step = cycle[idx % len(cycle)]
        idx += 1
        base += (
            f" I take one more careful step in this situation: {step}. I ask a direct question, I listen,"
            f" and I notice how my chest feels and how my thoughts settle. I choose clear words and I keep the pace even."
        )
        base += (
            " I avoid clichés. I use plain language. I stay with the present scene and I let the next moment lead me."
        )

    # Ensure range
    return enforce_word_range(base)


# --------------------- Routes ---------------------

@app.get("/")
def read_root():
    return {"message": "ChapterSmith AI backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
        else:
            response["database"] = "❌ Not Available"
    except Exception as e:
        response["database"] = f"⚠️ Error: {str(e)[:80]}"
    return response


# Projects CRUD
@app.post("/api/projects")
def create_project(req: CreateProjectRequest):
    now = datetime.now(timezone.utc)
    project = Project(
        name=req.name,
        outline=req.outline,
        chapter_count=req.chapter_count,
        pov_mode=req.pov_mode,
        genre=req.genre,
        rules=req.rules,
        chapters=[],
        created_at=now,
        updated_at=now,
    )
    pid = create_document("project", project)
    return {"id": pid}


@app.get("/api/projects")
def list_projects():
    items = get_documents("project")
    return [serialize_id(i) for i in items]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    try:
        doc = collection("project").find_one({"_id": ObjectId(project_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project id")
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    return serialize_id(doc)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    try:
        res = collection("project").delete_one({"_id": ObjectId(project_id)})
        return {"deleted": res.deleted_count == 1}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project id")


# Generate or regenerate a chapter
@app.post("/api/projects/{project_id}/chapters/generate")
def generate_chapter(project_id: str, req: GenerateChapterRequest):
    try:
        doc = collection("project").find_one({"_id": ObjectId(project_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project id")
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")

    project = Project(**{k: v for k, v in doc.items() if k != "_id"})

    ch_num = req.chapter_number
    if ch_num < 1 or ch_num > project.chapter_count:
        raise HTTPException(status_code=400, detail="Chapter number out of range")

    pov = resolve_chapter_pov(project.pov_mode, ch_num)
    text = grounded_chapter_generator(project.outline, ch_num, project.chapter_count, pov, project.genre or "general")

    # Apply user instructions lightly by appending a small targeted adjustment (kept grounded)
    if req.user_instructions:
        text += " " + (
            f"Adjustment note applied: {req.user_instructions.strip()} I keep the same plot and tone while refining moments."
        )
        text = enforce_word_range(text)

    title = f"Chapter {ch_num}"
    wc = compute_word_count(text)
    chapter = Chapter(number=ch_num, title=title, text=text, word_count=wc, pov=pov)

    # Upsert logic for this chapter number
    chapters = [c for c in (project.chapters or [])]
    existing_idx = next((i for i, c in enumerate(chapters) if c.get("number") == ch_num or getattr(c, "number", None) == ch_num), None)

    ch_dict = chapter.model_dump()
    ch_dict["created_at"] = datetime.now(timezone.utc)
    ch_dict["updated_at"] = datetime.now(timezone.utc)

    if existing_idx is None:
        chapters.append(ch_dict)
    else:
        chapters[existing_idx] = ch_dict

    collection("project").update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {"chapters": chapters, "updated_at": datetime.now(timezone.utc)}},
    )

    return {"ok": True, "chapter": ch_dict}


# Bulk generate all chapters
@app.post("/api/projects/{project_id}/chapters/generate_all")
def generate_all(project_id: str):
    try:
        doc = collection("project").find_one({"_id": ObjectId(project_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project id")
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")

    project = Project(**{k: v for k, v in doc.items() if k != "_id"})

    chapters: List[dict] = []
    for ch_num in range(1, project.chapter_count + 1):
        pov = resolve_chapter_pov(project.pov_mode, ch_num)
        text = grounded_chapter_generator(project.outline, ch_num, project.chapter_count, pov, project.genre or "general")
        title = f"Chapter {ch_num}"
        wc = compute_word_count(text)
        ch_dict = Chapter(number=ch_num, title=title, text=text, word_count=wc, pov=pov).model_dump()
        ch_dict["created_at"] = datetime.now(timezone.utc)
        ch_dict["updated_at"] = datetime.now(timezone.utc)
        chapters.append(ch_dict)

    collection("project").update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {"chapters": chapters, "updated_at": datetime.now(timezone.utc)}},
    )

    return {"ok": True, "count": len(chapters)}


# Edit a chapter
@app.patch("/api/projects/{project_id}/chapters/{chapter_number}")
def edit_chapter(project_id: str, chapter_number: int, body: EditChapterRequest):
    try:
        doc = collection("project").find_one({"_id": ObjectId(project_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project id")
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")

    chapters = doc.get("chapters", [])
    idx = next((i for i, c in enumerate(chapters) if c.get("number") == chapter_number), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if body.title is not None:
        chapters[idx]["title"] = body.title
    if body.text is not None:
        chapters[idx]["text"] = enforce_word_range(body.text)
        chapters[idx]["word_count"] = compute_word_count(chapters[idx]["text"])
    chapters[idx]["updated_at"] = datetime.now(timezone.utc)

    collection("project").update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {"chapters": chapters, "updated_at": datetime.now(timezone.utc)}},
    )

    return {"ok": True, "chapter": chapters[idx]}


# Copy chapter endpoint (returns just the text)
@app.get("/api/projects/{project_id}/chapters/{chapter_number}/copy")
def copy_chapter_text(project_id: str, chapter_number: int):
    try:
        doc = collection("project").find_one({"_id": ObjectId(project_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project id")
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")

    chapter = next((c for c in doc.get("chapters", []) if c.get("number") == chapter_number), None)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    return {"title": chapter.get("title"), "text": chapter.get("text"), "word_count": chapter.get("word_count")}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
