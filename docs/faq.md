# FAQ

Common questions about VenomQA.

## General

**Q: What is VenomQA?**

A: VenomQA is a state-based API testing framework that helps you test your entire application through state exploration. Unlike traditional API testing tools that test endpoints in isolation, VenomQA tests complete user workflows and verifies that your system remains consistent after every action.

---

## Getting Started

**Q: When should I use StateGraph vs Journey?**

A: Use each approach for different scenarios:

| Scenario | Recommended Approach |
|----------|---------------------|
| Testing a specific user flow (login, checkout, etc.) | **Journey** |
| Exploring all possible state transitions | **StateGraph** |
| Smoke tests and quick sanity checks | **Journey** |
| Finding edge cases and unexpected paths | **StateGraph** |
| CI/CD integration | Both work well |

**Journey** is simpler and more intuitive - start here if you're new. It's like writing a script that a user would follow.

**StateGraph** is more powerful - it automatically explores all paths through your system and finds bugs that linear tests miss.

```python
# Journey: Test one specific flow
journey = Journey(
    name="checkout",
    steps=[Step(name="login", action=login), Step(name="checkout", action=checkout)]
)

# StateGraph: Explore ALL state transitions
graph = StateGraph(name="shopping")
graph.add_node("empty", initial=True)
graph.add_node("has_items")
graph.add_edge("empty", "has_items", action=add_item)
graph.add_edge("has_items", "empty", action=remove_item)
result = graph.explore(client)  # Tests all paths automatically
```

---

**Q: Do I need PostgreSQL to use VenomQA?**

A: No! PostgreSQL is optional and only needed for advanced features:

| Feature | Requires Database? |
|---------|-------------------|
| Basic Journey testing | No |
| HTTP assertions | No |
| Checkpoint/Branch (context only) | No |
| Checkpoint/Branch (database rollback) | Yes (PostgreSQL, MySQL, or SQLite) |
| StateGraph exploration | No (but recommended for full rollback) |

For most use cases, you can start without any database:

```yaml
# venomqa.yaml - minimal config (no database)
base_url: "http://localhost:8000"
timeout: 30
```

If you need database state rollback, add:

```yaml
# venomqa.yaml - with PostgreSQL
base_url: "http://localhost:8000"
db_url: "postgresql://user:pass@localhost:5432/testdb"
db_backend: "postgresql"
```

---

**Q: How do I test without a real API?**

A: You have several options:

1. **Use the test server we provide:**
   ```bash
   cd examples/quickstart
   pip install fastapi uvicorn
   python test_server.py
   ```

2. **Use mocking (for unit testing the framework itself):**
   ```python
   from venomqa.mocking import MockClient

   mock = MockClient()
   mock.when_get("/health").respond({"status": "ok"})

   journey(mock)  # Uses mock responses
   ```

3. **Use fixtures for predictable test data:**
   ```python
   from venomqa.data import DataFactory

   factory = DataFactory()
   user = factory.user(email="test@example.com")
   ```

---

**Q: What's the difference between `context["key"]` and `context.get("key")`?**

A: They behave differently when the key doesn't exist:

```python
# context["key"] - Raises KeyError if key doesn't exist
item_id = context["item_id"]  # Crashes if item_id not set!

# context.get("key") - Returns None (or default) if key doesn't exist
item_id = context.get("item_id")  # Returns None if not set
item_id = context.get("item_id", default=1)  # Returns 1 if not set

# context.get_required("key") - Raises KeyError with a better error message
item_id = context.get_required("item_id")  # KeyError: "Required context key not found: item_id"
```

**Best practice:** Use `context.get()` in most cases, and `context.get_required()` when the value MUST exist.

---

## Common Errors

**Q: I get "Connection refused" error. What's wrong?**

A: Your API server isn't running or isn't accessible. Check:

1. **Is the server running?**
   ```bash
   # Check if anything is listening on the port
   lsof -i :8000
   curl http://localhost:8000/health
   ```

2. **Is `base_url` correct in `venomqa.yaml`?**
   ```yaml
   # Make sure this matches your actual server
   base_url: "http://localhost:8000"  # Not https, correct port
   ```

3. **If using Docker, is the network configured?**
   ```yaml
   # docker-compose.yml
   services:
     api:
       ports:
         - "8000:8000"  # Make sure port is exposed
   ```

---

**Q: I get "Journey not found" error. How do I fix it?**

A: VenomQA can't find your journey file. Check:

1. **Is the file in the right directory?**
   ```
   my-project/
   ├── journeys/           # Journeys go here
   │   └── my_journey.py
   └── venomqa.yaml
   ```

2. **Does the file have a `journey` variable?**
   ```python
   # journeys/my_journey.py
   from venomqa import Journey, Step

   journey = Journey(  # Must be named 'journey' at module level
       name="my_journey",
       steps=[...]
   )
   ```

3. **Are you using the correct name?**
   ```bash
   # Run with the journey 'name', not the filename
   venomqa run my_journey      # Correct (uses name="my_journey")
   venomqa run my_journey.py   # Wrong (filename)
   ```

List available journeys:
```bash
venomqa list
```

---

**Q: I get "KeyError: 'item_id'" in my action. What happened?**

A: A previous step didn't set the value you're expecting. Common causes:

1. **Previous step failed silently:**
   ```python
   def create_item(client, context):
       response = client.post("/items", json={...})
       # This only sets item_id if successful!
       if response.status_code == 201:
           context["item_id"] = response.json()["id"]
       return response
   ```

2. **You're in a branch and context was reset:**
   Branches restore context to the checkpoint state. Make sure the value was set BEFORE the checkpoint.

3. **Typo in the key name:**
   ```python
   context["item_Id"] = 123  # Set with capital I
   context["item_id"]        # Get with lowercase i - KeyError!
   ```

**Fix:** Use defensive programming:
```python
def get_item(client, context):
    item_id = context.get("item_id")
    if not item_id:
        raise ValueError("item_id not set - did create_item succeed?")
    return client.get(f"/items/{item_id}")
```

---

**Q: How do I debug a failing step?**

A: Use verbose mode and add logging:

1. **Run with verbose output:**
   ```bash
   venomqa run my_journey --verbose
   ```

2. **Add logging to your actions:**
   ```python
   def create_item(client, context):
       print(f"Creating item with context: {dict(context._data)}")
       response = client.post("/items", json={...})
       print(f"Response: {response.status_code} - {response.text}")
       return response
   ```

3. **Check the response content:**
   ```python
   def create_item(client, context):
       response = client.post("/items", json={"name": "test"})
       if response.status_code != 201:
           print(f"Unexpected status: {response.status_code}")
           print(f"Response body: {response.json()}")
       return response
   ```

---

**Q: My step times out. How do I increase the timeout?**

A: Set timeout at the step or journey level:

```python
# Per-step timeout
Step(
    name="long_operation",
    action=long_operation,
    timeout=120.0,  # 2 minutes
)

# Default timeout for all steps in journey
journey = Journey(
    name="my_journey",
    timeout=60.0,  # 1 minute default
    steps=[...]
)
```

Or in `venomqa.yaml`:
```yaml
timeout: 60  # Global default in seconds
```

---

## Advanced Usage

**Q: How do I run the same journey with different data?**

A: Use the `args` parameter on steps:

```python
def login(client, context, email, password):
    return client.post("/login", json={"email": email, "password": password})

# Reuse the same action with different credentials
journey = Journey(
    name="multi_user_test",
    steps=[
        Step(name="login_admin", action=login, args={"email": "admin@example.com", "password": "admin123"}),
        Step(name="logout", action=logout),
        Step(name="login_user", action=login, args={"email": "user@example.com", "password": "user123"}),
    ]
)
```

---

**Q: How do I test authentication flows?**

A: Store the token in context and use `client.set_auth_token()`:

```python
def login(client, context):
    response = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "secret",
    })
    if response.status_code == 200:
        token = response.json()["access_token"]
        context["token"] = token
        client.set_auth_token(token)  # Sets Authorization: Bearer header
    return response

def protected_action(client, context):
    # Client automatically includes the auth header
    return client.get("/api/protected")
```

---

**Q: Can I use VenomQA with GraphQL APIs?**

A: Yes! Use the GraphQL client:

```python
from venomqa.clients.graphql import GraphQLClient

client = GraphQLClient("http://localhost:8000/graphql")

def get_users(client, context):
    query = """
    query {
        users {
            id
            name
            email
        }
    }
    """
    return client.query(query)

def create_user(client, context):
    mutation = """
    mutation CreateUser($name: String!, $email: String!) {
        createUser(name: $name, email: $email) {
            id
            name
        }
    }
    """
    return client.query(mutation, variables={"name": "Test", "email": "test@example.com"})
```

---

**Q: How do I integrate VenomQA with CI/CD?**

A: VenomQA works with any CI system. Here's an example for GitHub Actions:

```yaml
# .github/workflows/test.yml
name: API Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      api:
        image: your-api:latest
        ports:
          - 8000:8000

    steps:
      - uses: actions/checkout@v4

      - name: Install VenomQA
        run: pip install venomqa

      - name: Run tests
        run: venomqa run --all

      - name: Generate report
        if: always()
        run: venomqa report --format junit --output results.xml

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: results.xml
```

---

**Q: How do I test error handling in my API?**

A: Use `expect_failure=True` on steps that should fail:

```python
journey = Journey(
    name="error_handling",
    steps=[
        # Test 401 Unauthorized
        Step(
            name="access_without_auth",
            action=lambda c, ctx: c.get("/api/protected"),
            expect_failure=True,
        ),

        # Test 404 Not Found
        Step(
            name="get_nonexistent",
            action=lambda c, ctx: c.get("/api/items/99999"),
            expect_failure=True,
        ),

        # Test 422 Validation Error
        Step(
            name="invalid_input",
            action=lambda c, ctx: c.post("/api/items", json={"price": "not_a_number"}),
            expect_failure=True,
        ),
    ]
)
```

---

## Troubleshooting

**Q: VenomQA is slow. How do I speed it up?**

A: Try these optimizations:

1. **Use `--no-infra` if services are already running:**
   ```bash
   venomqa run --no-infra
   ```

2. **Reduce unnecessary waits:**
   ```python
   # Don't wait unnecessarily
   Step(name="fast_check", action=fast_check, timeout=5.0)
   ```

3. **Run tests in parallel (coming soon):**
   ```bash
   venomqa run --parallel 4
   ```

4. **Use targeted test runs:**
   ```bash
   venomqa run specific_journey  # Instead of --all
   ```

---

**Q: Where can I get help?**

A: You have several options:

1. **Check the documentation:** https://venomqa.dev/docs
2. **Search existing issues:** https://github.com/namanag97/venomqa/issues
3. **Open a new issue:** https://github.com/namanag97/venomqa/issues/new
4. **Join the community:** (Coming soon)

When reporting issues, include:
- VenomQA version (`venomqa --version`)
- Python version (`python --version`)
- Your `venomqa.yaml` config (remove secrets)
- The full error message and traceback
