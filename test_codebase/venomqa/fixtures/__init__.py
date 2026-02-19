"""Test fixtures for QA tests.

Fixtures provide test data and dependencies using dependency injection.
Use the @fixture decorator with optional `depends` for dependencies.

Example:
    from venomqa.plugins import fixture

    @fixture
    def db():
        from venomqa.adapters import get_adapter
        return get_adapter("postgres")(host="localhost", database="test")

    @fixture(depends=["db"])
    def user(db):
        return db.insert("users", {"email": "test@example.com", "name": "Test User"})
"""
