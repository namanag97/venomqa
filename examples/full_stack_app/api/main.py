from flask import Flask, jsonify, request, g
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
import os

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///test.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

db = SQLAlchemy(app)
CORS(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False, default=0.0)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "quantity": self.quantity,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
        }


def auth_required(f):
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            g.current_user = User.query.get(data["user_id"])
            if not g.current_user:
                return jsonify({"error": "User not found"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)

    decorated.__name__ = f.__name__
    return decorated


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.datetime.utcnow().isoformat()})


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()

    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"error": "Email and password required"}), 400

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email already registered"}), 400

    user = User(email=data["email"], name=data.get("name"))
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "User created", "user": user.to_dict()}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()

    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"error": "Email and password required"}), 400

    user = User.query.filter_by(email=data["email"]).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Invalid credentials"}), 401

    token = jwt.encode(
        {"user_id": user.id, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)},
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )

    refresh_token = jwt.encode(
        {
            "user_id": user.id,
            "type": "refresh",
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )

    return jsonify({"access_token": token, "refresh_token": refresh_token, "user": user.to_dict()})


@app.route("/api/auth/me", methods=["GET"])
@auth_required
def get_current_user():
    return jsonify(g.current_user.to_dict())


@app.route("/api/auth/logout", methods=["POST"])
@auth_required
def logout():
    return jsonify({"message": "Logged out successfully"})


@app.route("/api/items", methods=["GET"])
def list_items():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = Item.query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify(
        {
            "items": [item.to_dict() for item in pagination.items],
            "total": pagination.total,
            "page": page,
            "per_page": per_page,
            "pages": pagination.pages,
        }
    )


@app.route("/api/items", methods=["POST"])
@auth_required
def create_item():
    data = request.get_json()

    if not data or not data.get("name"):
        return jsonify({"error": "Name is required"}), 400

    item = Item(
        name=data["name"],
        description=data.get("description"),
        price=data.get("price", 0.0),
        quantity=data.get("quantity", 0),
        user_id=g.current_user.id,
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({"message": "Item created", "item": item.to_dict()}), 201


@app.route("/api/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    item = Item.query.get_or_404(item_id)
    return jsonify(item.to_dict())


@app.route("/api/items/<int:item_id>", methods=["PUT"])
@auth_required
def update_item(item_id):
    item = Item.query.get_or_404(item_id)

    if item.user_id != g.current_user.id:
        return jsonify({"error": "Not authorized"}), 403

    data = request.get_json()

    item.name = data.get("name", item.name)
    item.description = data.get("description", item.description)
    item.price = data.get("price", item.price)
    item.quantity = data.get("quantity", item.quantity)

    db.session.commit()

    return jsonify({"message": "Item updated", "item": item.to_dict()})


@app.route("/api/items/<int:item_id>", methods=["PATCH"])
@auth_required
def partial_update_item(item_id):
    item = Item.query.get_or_404(item_id)

    if item.user_id != g.current_user.id:
        return jsonify({"error": "Not authorized"}), 403

    data = request.get_json()

    if "name" in data:
        item.name = data["name"]
    if "description" in data:
        item.description = data["description"]
    if "price" in data:
        item.price = data["price"]
    if "quantity" in data:
        item.quantity = data["quantity"]

    db.session.commit()

    return jsonify({"message": "Item updated", "item": item.to_dict()})


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
@auth_required
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)

    if item.user_id != g.current_user.id:
        return jsonify({"error": "Not authorized"}), 403

    db.session.delete(item)
    db.session.commit()

    return jsonify({"message": "Item deleted"})


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({"error": "Internal server error"}), 500


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
