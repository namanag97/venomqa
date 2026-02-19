"""Data models for Todo application."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Todo(db.Model):
    __tablename__ = "todos"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    completed = db.Column(db.Boolean, default=False)
    attachments = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp()
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "completed": self.completed,
            "attachments": self.attachments or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Todo {self.id}: {self.title}>"


class TodoCreate:
    def __init__(self, title: str, description: str = "", completed: bool = False):
        self.title = title
        self.description = description
        self.completed = completed


class TodoUpdate:
    def __init__(self, title: str = None, description: str = None, completed: bool = None):
        self.title = title
        self.description = description
        self.completed = completed
