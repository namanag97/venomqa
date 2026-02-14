#!/usr/bin/env python3
"""Test VenomQA State Graph against JSONPlaceholder API.

JSONPlaceholder is a free fake REST API with:
- /users (10 users)
- /posts (100 posts, belong to users)
- /comments (500 comments, belong to posts)
- /todos (200 todos, belong to users)
- /albums (100 albums, belong to users)
- /photos (5000 photos, belong to albums)

This tests CROSS-FEATURE CONSISTENCY:
- Do all posts have valid user IDs?
- Do all comments belong to existing posts?
- Does the comment count match for each post?
- Are user relationships consistent across features?

This is EXACTLY what a human QA would check.
"""

import sys
sys.path.insert(0, '.')

from venomqa import Client, StateGraph
from venomqa.core.graph import Severity

BASE_URL = "https://jsonplaceholder.typicode.com"


def main():
    print("\n" + "=" * 70)
    print("STATE GRAPH TEST: JSONPlaceholder API")
    print("Testing cross-feature consistency on a real public API")
    print("=" * 70)

    client = Client(base_url=BASE_URL)

    # =========================================
    # STEP 1: Fetch all data for context
    # =========================================
    print("\nFetching data from API...")

    users = client.get("/users").json()
    posts = client.get("/posts").json()
    comments = client.get("/comments").json()
    todos = client.get("/todos").json()
    albums = client.get("/albums").json()

    print(f"  Users: {len(users)}")
    print(f"  Posts: {len(posts)}")
    print(f"  Comments: {len(comments)}")
    print(f"  Todos: {len(todos)}")
    print(f"  Albums: {len(albums)}")

    # Build lookup maps
    user_ids = {u["id"] for u in users}
    post_ids = {p["id"] for p in posts}
    album_ids = {a["id"] for a in albums}

    # =========================================
    # STEP 2: Define State Graph
    # =========================================

    graph = StateGraph(
        name="jsonplaceholder_api",
        description="Cross-feature consistency tests for JSONPlaceholder"
    )

    # States represent what we're testing
    graph.add_node("start", description="Initial state", initial=True)
    graph.add_node("users_loaded", description="Users data loaded")
    graph.add_node("posts_loaded", description="Posts data loaded")
    graph.add_node("comments_loaded", description="Comments data loaded")
    graph.add_node("full_state", description="All data loaded and verified")

    # Actions to transition between states
    def load_users(client, ctx):
        ctx["users"] = client.get("/users").json()
        ctx["user_ids"] = {u["id"] for u in ctx["users"]}
        print(f"  [LOAD] {len(ctx['users'])} users")
        return ctx["users"]

    def load_posts(client, ctx):
        ctx["posts"] = client.get("/posts").json()
        ctx["post_ids"] = {p["id"] for p in ctx["posts"]}
        print(f"  [LOAD] {len(ctx['posts'])} posts")
        return ctx["posts"]

    def load_comments(client, ctx):
        ctx["comments"] = client.get("/comments").json()
        print(f"  [LOAD] {len(ctx['comments'])} comments")
        return ctx["comments"]

    def load_todos(client, ctx):
        ctx["todos"] = client.get("/todos").json()
        print(f"  [LOAD] {len(ctx['todos'])} todos")
        return ctx["todos"]

    def verify_user_post(client, ctx):
        """Pick a user and verify their posts."""
        user_id = 1
        user_posts = client.get(f"/users/{user_id}/posts").json()
        ctx["user_posts"] = user_posts
        print(f"  [VERIFY] User {user_id} has {len(user_posts)} posts")
        return user_posts

    graph.add_edge("start", "users_loaded", action=load_users, name="load_users")
    graph.add_edge("users_loaded", "posts_loaded", action=load_posts, name="load_posts")
    graph.add_edge("posts_loaded", "comments_loaded", action=load_comments, name="load_comments")
    graph.add_edge("comments_loaded", "full_state", action=verify_user_post, name="verify")

    # =========================================
    # STEP 3: Define Invariants
    # =========================================

    def all_posts_have_valid_users(client, db, ctx):
        """Every post must belong to an existing user."""
        if "posts" not in ctx or "user_ids" not in ctx:
            return True  # Not yet loaded

        invalid = []
        for post in ctx["posts"]:
            if post["userId"] not in ctx["user_ids"]:
                invalid.append(post)

        if invalid:
            print(f"    [FAIL] {len(invalid)} posts have invalid userId")
            for p in invalid[:3]:
                print(f"      Post {p['id']}: userId={p['userId']} (not found)")

        return len(invalid) == 0

    def all_comments_have_valid_posts(client, db, ctx):
        """Every comment must belong to an existing post."""
        if "comments" not in ctx or "post_ids" not in ctx:
            return True

        invalid = []
        for comment in ctx["comments"]:
            if comment["postId"] not in ctx["post_ids"]:
                invalid.append(comment)

        if invalid:
            print(f"    [FAIL] {len(invalid)} comments have invalid postId")

        return len(invalid) == 0

    def comment_counts_match(client, db, ctx):
        """Comment count via /posts/:id/comments should match filtered comments."""
        if "posts" not in ctx or "comments" not in ctx:
            return True

        # Check first 3 posts (to keep test fast)
        for post in ctx["posts"][:3]:
            post_id = post["id"]

            # Count from filtered comments
            filtered_count = len([c for c in ctx["comments"] if c["postId"] == post_id])

            # Count from nested endpoint
            nested = client.get(f"/posts/{post_id}/comments").json()
            nested_count = len(nested)

            if filtered_count != nested_count:
                print(f"    [FAIL] Post {post_id}: filtered={filtered_count}, nested={nested_count}")
                return False

        return True

    def user_posts_endpoint_consistent(client, db, ctx):
        """User's posts via /users/:id/posts should match filtered posts."""
        if "posts" not in ctx or "users" not in ctx:
            return True

        # Check first 3 users
        for user in ctx["users"][:3]:
            user_id = user["id"]

            # Count from filtered posts
            filtered = [p for p in ctx["posts"] if p["userId"] == user_id]

            # Count from nested endpoint
            nested = client.get(f"/users/{user_id}/posts").json()

            if len(filtered) != len(nested):
                print(f"    [FAIL] User {user_id}: filtered={len(filtered)}, nested={len(nested)}")
                return False

            # Check IDs match
            filtered_ids = {p["id"] for p in filtered}
            nested_ids = {p["id"] for p in nested}

            if filtered_ids != nested_ids:
                print(f"    [FAIL] User {user_id}: post IDs don't match")
                return False

        return True

    def todos_have_valid_users(client, db, ctx):
        """All todos must belong to existing users."""
        if "todos" not in ctx or "user_ids" not in ctx:
            return True

        invalid = [t for t in ctx["todos"] if t["userId"] not in ctx["user_ids"]]

        if invalid:
            print(f"    [FAIL] {len(invalid)} todos have invalid userId")

        return len(invalid) == 0

    def email_format_valid(client, db, ctx):
        """All user emails should be valid format."""
        if "users" not in ctx:
            return True

        import re
        email_pattern = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

        invalid = []
        for user in ctx["users"]:
            if not email_pattern.match(user.get("email", "")):
                invalid.append(user)

        if invalid:
            print(f"    [FAIL] {len(invalid)} users have invalid email format")
            for u in invalid[:3]:
                print(f"      User {u['id']}: {u.get('email')}")

        return len(invalid) == 0

    graph.add_invariant(
        "posts_valid_users",
        all_posts_have_valid_users,
        "All posts must have valid userId",
        Severity.CRITICAL
    )

    graph.add_invariant(
        "comments_valid_posts",
        all_comments_have_valid_posts,
        "All comments must have valid postId",
        Severity.CRITICAL
    )

    graph.add_invariant(
        "comment_counts",
        comment_counts_match,
        "Comment counts must be consistent",
        Severity.HIGH
    )

    graph.add_invariant(
        "user_posts_consistent",
        user_posts_endpoint_consistent,
        "User posts endpoint must match filtered posts",
        Severity.HIGH
    )

    graph.add_invariant(
        "todos_valid_users",
        todos_have_valid_users,
        "All todos must have valid userId",
        Severity.MEDIUM
    )

    graph.add_invariant(
        "valid_emails",
        email_format_valid,
        "All emails must be valid format",
        Severity.LOW
    )

    # =========================================
    # STEP 4: Show the graph
    # =========================================

    print("\n\nState Graph:")
    print("-" * 40)
    print(graph.to_mermaid())

    # =========================================
    # STEP 5: Explore
    # =========================================

    print("\n\nExploring state graph...")
    print("-" * 40)

    result = graph.explore(
        client=client,
        db=None,  # No database, just API
        max_depth=5,
    )

    # =========================================
    # STEP 6: Results
    # =========================================

    print("\n")
    print(result.summary())

    # Path visualization
    print("\n\nPaths Explored:")
    print("-" * 40)
    for path in result.paths_explored:
        status = "PASS" if path.success else "FAIL"
        print(f"  [{status}] {' -> '.join(path.path)}")

    # Summary
    print("\n" + "=" * 70)
    if result.success:
        print("ALL INVARIANTS PASSED")
        print("JSONPlaceholder API maintains cross-feature consistency!")
    else:
        print("INVARIANT VIOLATIONS FOUND")
        print(f"Broken nodes: {result.broken_nodes()}")
        print(f"Broken edges: {result.broken_edges()}")
    print("=" * 70)

    return result.success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
