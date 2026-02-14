#!/usr/bin/env python3
"""Complex State Graph: Multiple branching paths.

This demonstrates the FULL power of state graph testing:
- Multiple paths from each state
- All combinations explored
- Invariants checked at EVERY step

Like you said: "within a journey there could be 5 paths, 7 paths"
This tests ALL of them.
"""

import sys
sys.path.insert(0, '.')

from venomqa import Client, StateGraph
from venomqa.core.graph import Severity

BASE_URL = "https://jsonplaceholder.typicode.com"


def main():
    print("\n" + "=" * 70)
    print("COMPLEX STATE GRAPH: Multiple Branching Paths")
    print("=" * 70)

    client = Client(base_url=BASE_URL)

    graph = StateGraph(
        name="complex_branches",
        description="Tests all possible path combinations"
    )

    # =========================================
    # NODES: Multiple states to explore
    # =========================================

    graph.add_node("start", description="Initial state", initial=True)
    graph.add_node("user_selected", description="A user is selected")
    graph.add_node("viewing_posts", description="Viewing user's posts")
    graph.add_node("viewing_todos", description="Viewing user's todos")
    graph.add_node("viewing_albums", description="Viewing user's albums")
    graph.add_node("post_selected", description="A specific post selected")
    graph.add_node("viewing_comments", description="Viewing post comments")
    graph.add_node("todo_selected", description="A specific todo selected")
    graph.add_node("album_selected", description="A specific album selected")
    graph.add_node("viewing_photos", description="Viewing album photos")

    # =========================================
    # EDGES: Multiple paths from each state
    # =========================================

    def select_user_1(client, ctx):
        ctx["user_id"] = 1
        user = client.get("/users/1").json()
        ctx["user"] = user
        print(f"  [SELECT] User 1: {user['name']}")
        return user

    def select_user_2(client, ctx):
        ctx["user_id"] = 2
        user = client.get("/users/2").json()
        ctx["user"] = user
        print(f"  [SELECT] User 2: {user['name']}")
        return user

    def view_user_posts(client, ctx):
        posts = client.get(f"/users/{ctx['user_id']}/posts").json()
        ctx["posts"] = posts
        print(f"  [VIEW] {len(posts)} posts")
        return posts

    def view_user_todos(client, ctx):
        todos = client.get(f"/users/{ctx['user_id']}/todos").json()
        ctx["todos"] = todos
        completed = len([t for t in todos if t["completed"]])
        print(f"  [VIEW] {len(todos)} todos ({completed} completed)")
        return todos

    def view_user_albums(client, ctx):
        albums = client.get(f"/users/{ctx['user_id']}/albums").json()
        ctx["albums"] = albums
        print(f"  [VIEW] {len(albums)} albums")
        return albums

    def select_first_post(client, ctx):
        if not ctx.get("posts"):
            return None
        post = ctx["posts"][0]
        ctx["post_id"] = post["id"]
        ctx["current_post"] = post
        print(f"  [SELECT] Post {post['id']}: {post['title'][:30]}...")
        return post

    def view_post_comments(client, ctx):
        comments = client.get(f"/posts/{ctx['post_id']}/comments").json()
        ctx["comments"] = comments
        print(f"  [VIEW] {len(comments)} comments on post")
        return comments

    def select_first_todo(client, ctx):
        if not ctx.get("todos"):
            return None
        todo = ctx["todos"][0]
        ctx["todo_id"] = todo["id"]
        ctx["current_todo"] = todo
        status = "completed" if todo["completed"] else "pending"
        print(f"  [SELECT] Todo {todo['id']}: {status}")
        return todo

    def select_first_album(client, ctx):
        if not ctx.get("albums"):
            return None
        album = ctx["albums"][0]
        ctx["album_id"] = album["id"]
        ctx["current_album"] = album
        print(f"  [SELECT] Album {album['id']}: {album['title'][:30]}...")
        return album

    def view_album_photos(client, ctx):
        photos = client.get(f"/albums/{ctx['album_id']}/photos").json()
        ctx["photos"] = photos
        print(f"  [VIEW] {len(photos)} photos in album")
        return photos

    # From start: can select different users
    graph.add_edge("start", "user_selected", action=select_user_1, name="select_user_1")
    graph.add_edge("start", "user_selected", action=select_user_2, name="select_user_2")

    # From user_selected: can view posts, todos, or albums
    graph.add_edge("user_selected", "viewing_posts", action=view_user_posts, name="view_posts")
    graph.add_edge("user_selected", "viewing_todos", action=view_user_todos, name="view_todos")
    graph.add_edge("user_selected", "viewing_albums", action=view_user_albums, name="view_albums")

    # From viewing_posts: can select a post or switch to todos/albums
    graph.add_edge("viewing_posts", "post_selected", action=select_first_post, name="select_post")
    graph.add_edge("viewing_posts", "viewing_todos", action=view_user_todos, name="switch_to_todos")

    # From post_selected: can view comments
    graph.add_edge("post_selected", "viewing_comments", action=view_post_comments, name="view_comments")

    # From viewing_todos: can select a todo
    graph.add_edge("viewing_todos", "todo_selected", action=select_first_todo, name="select_todo")
    graph.add_edge("viewing_todos", "viewing_posts", action=view_user_posts, name="switch_to_posts")

    # From viewing_albums: can select album or switch
    graph.add_edge("viewing_albums", "album_selected", action=select_first_album, name="select_album")

    # From album_selected: can view photos
    graph.add_edge("album_selected", "viewing_photos", action=view_album_photos, name="view_photos")

    # =========================================
    # INVARIANTS: Checked at every state
    # =========================================

    def user_data_consistent(client, db, ctx):
        """User data should be consistent across endpoints."""
        if "user" not in ctx:
            return True

        user_id = ctx["user_id"]
        direct_user = client.get(f"/users/{user_id}").json()

        # Check key fields match
        if ctx["user"]["name"] != direct_user["name"]:
            print(f"    [FAIL] User name mismatch")
            return False
        if ctx["user"]["email"] != direct_user["email"]:
            print(f"    [FAIL] User email mismatch")
            return False

        return True

    def posts_belong_to_user(client, db, ctx):
        """All loaded posts should belong to selected user."""
        if "posts" not in ctx or "user_id" not in ctx:
            return True

        invalid = [p for p in ctx["posts"] if p["userId"] != ctx["user_id"]]
        if invalid:
            print(f"    [FAIL] {len(invalid)} posts don't belong to user {ctx['user_id']}")
            return False

        return True

    def todos_belong_to_user(client, db, ctx):
        """All loaded todos should belong to selected user."""
        if "todos" not in ctx or "user_id" not in ctx:
            return True

        invalid = [t for t in ctx["todos"] if t["userId"] != ctx["user_id"]]
        if invalid:
            print(f"    [FAIL] {len(invalid)} todos don't belong to user")
            return False

        return True

    def albums_belong_to_user(client, db, ctx):
        """All loaded albums should belong to selected user."""
        if "albums" not in ctx or "user_id" not in ctx:
            return True

        invalid = [a for a in ctx["albums"] if a["userId"] != ctx["user_id"]]
        if invalid:
            print(f"    [FAIL] {len(invalid)} albums don't belong to user")
            return False

        return True

    def comments_belong_to_post(client, db, ctx):
        """All loaded comments should belong to selected post."""
        if "comments" not in ctx or "post_id" not in ctx:
            return True

        invalid = [c for c in ctx["comments"] if c["postId"] != ctx["post_id"]]
        if invalid:
            print(f"    [FAIL] {len(invalid)} comments don't belong to post")
            return False

        return True

    def photos_belong_to_album(client, db, ctx):
        """All loaded photos should belong to selected album."""
        if "photos" not in ctx or "album_id" not in ctx:
            return True

        invalid = [p for p in ctx["photos"] if p["albumId"] != ctx["album_id"]]
        if invalid:
            print(f"    [FAIL] {len(invalid)} photos don't belong to album")
            return False

        return True

    def todo_completion_valid(client, db, ctx):
        """Todo completion status should be boolean."""
        if "todos" not in ctx:
            return True

        for todo in ctx["todos"]:
            if not isinstance(todo.get("completed"), bool):
                print(f"    [FAIL] Todo {todo['id']} has non-boolean completed status")
                return False

        return True

    graph.add_invariant("user_consistent", user_data_consistent,
                       "User data consistent", Severity.CRITICAL)
    graph.add_invariant("posts_ownership", posts_belong_to_user,
                       "Posts belong to user", Severity.CRITICAL)
    graph.add_invariant("todos_ownership", todos_belong_to_user,
                       "Todos belong to user", Severity.CRITICAL)
    graph.add_invariant("albums_ownership", albums_belong_to_user,
                       "Albums belong to user", Severity.CRITICAL)
    graph.add_invariant("comments_ownership", comments_belong_to_post,
                       "Comments belong to post", Severity.HIGH)
    graph.add_invariant("photos_ownership", photos_belong_to_album,
                       "Photos belong to album", Severity.HIGH)
    graph.add_invariant("todo_completion", todo_completion_valid,
                       "Todo completion is valid", Severity.MEDIUM)

    # =========================================
    # Show graph
    # =========================================

    print("\nState Graph (Multiple Branches):")
    print("-" * 40)
    print(graph.to_mermaid())

    print(f"\nNodes: {len(graph.nodes)}")
    print(f"Edges: {sum(len(e) for e in graph.edges.values())}")
    print(f"Invariants: {len(graph.invariants)}")

    # =========================================
    # Explore ALL paths
    # =========================================

    print("\n\nExploring ALL paths through the graph...")
    print("-" * 40)

    result = graph.explore(
        client=client,
        db=None,
        max_depth=6,
        stop_on_violation=False,  # Continue to find ALL issues
    )

    # =========================================
    # Results
    # =========================================

    print("\n")
    print(result.summary())

    print("\n\nAll Paths Explored:")
    print("-" * 40)
    for i, path in enumerate(result.paths_explored):
        status = "PASS" if path.success else "FAIL"
        path_str = " -> ".join(path.path)
        # Truncate long paths
        if len(path_str) > 70:
            path_str = path_str[:67] + "..."
        print(f"  {i+1}. [{status}] {path_str}")

    print("\n" + "=" * 70)
    if result.success:
        print(f"ALL {len(result.paths_explored)} PATHS PASSED")
        print("Every combination of user flows is consistent!")
    else:
        print("ISSUES FOUND IN SOME PATHS")
    print("=" * 70)

    return result.success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
