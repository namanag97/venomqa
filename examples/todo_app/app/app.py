"""Flask REST API for Todo application example."""

import os
import uuid
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

from models import Todo, TodoCreate, TodoUpdate, db

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///todos.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "/tmp/todo_uploads")

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db.init_app(app)


@app.before_request
def create_tables():
    db.create_all()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


@app.route("/todos", methods=["GET"])
def list_todos():
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 10, type=int)
    completed = request.args.get("completed", type=str)
    search = request.args.get("search", type=str)

    query = Todo.query

    if completed is not None:
        if completed.lower() in ("true", "1", "yes"):
            query = query.filter_by(completed=True)
        elif completed.lower() in ("false", "0", "no"):
            query = query.filter_by(completed=False)

    if search:
        query = query.filter(
            Todo.title.ilike(f"%{search}%") | Todo.description.ilike(f"%{search}%")
        )

    total = query.count()
    todos = query.offset((page - 1) * limit).limit(limit).all()

    return jsonify(
        {
            "todos": [t.to_dict() for t in todos],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit,
            },
        }
    )


@app.route("/todos", methods=["POST"])
def create_todo():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    if "title" not in data:
        return jsonify({"error": "Title is required"}), 422

    if len(data["title"]) < 1 or len(data["title"]) > 200:
        return jsonify({"error": "Title must be between 1 and 200 characters"}), 422

    todo = Todo(
        title=data["title"],
        description=data.get("description", ""),
        completed=data.get("completed", False),
    )

    db.session.add(todo)
    db.session.commit()

    return jsonify(todo.to_dict()), 201


@app.route("/todos/<int:todo_id>", methods=["GET"])
def get_todo(todo_id):
    todo = Todo.query.get(todo_id)

    if not todo:
        return jsonify({"error": f"Todo with id {todo_id} not found"}), 404

    return jsonify(todo.to_dict())


@app.route("/todos/<int:todo_id>", methods=["PUT"])
def update_todo(todo_id):
    todo = Todo.query.get(todo_id)

    if not todo:
        return jsonify({"error": f"Todo with id {todo_id} not found"}), 404

    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    if "title" in data:
        if len(data["title"]) < 1 or len(data["title"]) > 200:
            return jsonify({"error": "Title must be between 1 and 200 characters"}), 422
        todo.title = data["title"]

    if "description" in data:
        todo.description = data["description"]

    if "completed" in data:
        todo.completed = data["completed"]

    db.session.commit()

    return jsonify(todo.to_dict())


@app.route("/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    todo = Todo.query.get(todo_id)

    if not todo:
        return jsonify({"error": f"Todo with id {todo_id} not found"}), 404

    db.session.delete(todo)
    db.session.commit()

    return "", 204


@app.route("/todos/<int:todo_id>/attachments", methods=["POST"])
def upload_attachment(todo_id):
    todo = Todo.query.get(todo_id)

    if not todo:
        return jsonify({"error": f"Todo with id {todo_id} not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    file_id = str(uuid.uuid4())
    filename = f"{file_id}_{file.filename}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    attachment = {
        "id": file_id,
        "filename": file.filename,
        "size": os.path.getsize(filepath),
        "content_type": file.content_type,
        "todo_id": todo_id,
    }

    if not todo.attachments:
        todo.attachments = []
    todo.attachments.append(attachment)
    db.session.commit()

    return jsonify(attachment), 201


@app.route("/todos/<int:todo_id>/attachments/<file_id>", methods=["GET"])
def download_attachment(todo_id, file_id):
    todo = Todo.query.get(todo_id)

    if not todo:
        return jsonify({"error": f"Todo with id {todo_id} not found"}), 404

    if not todo.attachments:
        return jsonify({"error": "No attachments found"}), 404

    attachment = next((a for a in todo.attachments if a["id"] == file_id), None)

    if not attachment:
        return jsonify({"error": f"Attachment {file_id} not found"}), 404

    filename = f"{file_id}_{attachment['filename']}"
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/todos/<int:todo_id>/attachments/<file_id>", methods=["DELETE"])
def delete_attachment(todo_id, file_id):
    todo = Todo.query.get(todo_id)

    if not todo:
        return jsonify({"error": f"Todo with id {todo_id} not found"}), 404

    if not todo.attachments:
        return jsonify({"error": "No attachments found"}), 404

    attachment = next((a for a in todo.attachments if a["id"] == file_id), None)

    if not attachment:
        return jsonify({"error": f"Attachment {file_id} not found"}), 404

    filename = f"{file_id}_{attachment['filename']}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    todo.attachments = [a for a in todo.attachments if a["id"] != file_id]
    db.session.commit()

    return "", 204


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found"}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
