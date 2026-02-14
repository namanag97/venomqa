"""Pre-built content data generators.

This module provides specialized data generators for content-related testing
scenarios, including articles, comments, media, and CMS data.

Example:
    >>> from venomqa.data.content import content
    >>>
    >>> # Generate a blog post with comments
    >>> post = content.blog_post_with_comments(5)
    >>>
    >>> # Generate a content feed
    >>> feed = content.content_feed(20)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from venomqa.data.generators import FakeDataGenerator, fake as default_fake


@dataclass
class ContentGenerator:
    """Specialized generator for content-related test data.

    Provides methods for generating complex content data structures
    like articles, blog posts, comments, media items, and CMS data.
    """

    fake: FakeDataGenerator = field(default_factory=lambda: default_fake)

    def article(self, author_id: str | None = None, **overrides: Any) -> dict:
        """Generate an article."""
        return self.fake.article(author_id=author_id, **overrides)

    def blog_post(self, author_id: str | None = None, **overrides: Any) -> dict:
        """Generate a blog post."""
        title = self.fake.article_title()
        post = {
            "id": self.fake.uuid(),
            "title": title,
            "slug": self.fake.article_slug(title),
            "excerpt": self.fake.article_excerpt(200),
            "content": self.fake._faker.article_body_markdown(5),
            "content_html": self.fake._faker.article_body_html(5),
            "author_id": author_id or self.fake.uuid(),
            "author": {
                "id": author_id or self.fake.uuid(),
                "name": self.fake.name(),
                "avatar_url": self.fake._faker.avatar_url(),
                "bio": self.fake._faker.bio(100),
            },
            "category": self.fake._faker.category(),
            "tags": self.fake.tags(random.randint(3, 7)),
            "featured_image": {
                "url": self.fake._faker.featured_image_url(),
                "alt": self.fake.sentence(words=5),
                "caption": self.fake.sentence() if random.random() > 0.5 else None,
            },
            "status": self.fake._faker.content_status(),
            "is_featured": random.random() > 0.8,
            "allow_comments": random.random() > 0.1,
            "reading_time": self.fake._faker.reading_time(),
            "views": random.randint(0, 50000),
            "likes": random.randint(0, 5000),
            "shares": random.randint(0, 1000),
            "comments_count": random.randint(0, 200),
            "meta": {
                "title": title,
                "description": self.fake.article_excerpt(160),
                "keywords": self.fake.tags(5),
            },
            "published_at": (
                self.fake.past_datetime(days=365).isoformat()
                if random.random() > 0.2 else None
            ),
            "created_at": self.fake.datetime().isoformat(),
            "updated_at": self.fake.datetime().isoformat(),
        }
        post.update(overrides)
        return post

    def comment(
        self,
        content_id: str | None = None,
        user_id: str | None = None,
        parent_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a comment."""
        comment = {
            "id": self.fake.uuid(),
            "content_id": content_id or self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "parent_id": parent_id,
            "user": {
                "id": user_id or self.fake.uuid(),
                "name": self.fake.name(),
                "avatar_url": self.fake._faker.avatar_url(),
            },
            "body": self.fake.comment(300),
            "status": self.fake._faker.comment_status(),
            "likes": random.randint(0, 100),
            "replies_count": 0 if parent_id else random.randint(0, 10),
            "is_pinned": random.random() > 0.95,
            "is_author": random.random() > 0.9,
            "edited": random.random() > 0.8,
            "edited_at": (
                self.fake.datetime().isoformat()
                if random.random() > 0.8 else None
            ),
            "created_at": self.fake.datetime().isoformat(),
        }
        comment.update(overrides)
        return comment

    def comment_thread(
        self,
        content_id: str | None = None,
        depth: int = 2,
        replies_per_comment: int = 3,
    ) -> list[dict]:
        """Generate a comment thread with nested replies."""
        content_id = content_id or self.fake.uuid()
        comments = []

        # Root comments
        root_count = random.randint(3, 8)
        for _ in range(root_count):
            root_comment = self.comment(content_id=content_id)
            comments.append(root_comment)

            # Replies
            if depth > 0:
                reply_count = random.randint(0, replies_per_comment)
                for _ in range(reply_count):
                    reply = self.comment(
                        content_id=content_id,
                        parent_id=root_comment["id"],
                    )
                    comments.append(reply)

                    # Nested replies
                    if depth > 1 and random.random() > 0.5:
                        nested_count = random.randint(0, 2)
                        for _ in range(nested_count):
                            nested = self.comment(
                                content_id=content_id,
                                parent_id=reply["id"],
                            )
                            comments.append(nested)

        return comments

    def blog_post_with_comments(
        self,
        comment_count: int = 10,
        **overrides: Any,
    ) -> dict:
        """Generate a blog post with comments."""
        post = self.blog_post(**overrides)
        post["comments"] = [
            self.comment(content_id=post["id"])
            for _ in range(comment_count)
        ]
        post["comments_count"] = len(post["comments"])
        return post

    def page(self, **overrides: Any) -> dict:
        """Generate a CMS page."""
        title = self.fake.sentence(words=4).rstrip(".")
        page = {
            "id": self.fake.uuid(),
            "title": title,
            "slug": self.fake.article_slug(title),
            "content": self.fake._faker.article_body_html(8),
            "template": random.choice([
                "default",
                "full-width",
                "sidebar",
                "landing",
                "contact",
            ]),
            "parent_id": None,
            "order": random.randint(0, 100),
            "status": random.choice(["draft", "published", "archived"]),
            "is_homepage": random.random() > 0.95,
            "show_in_nav": random.random() > 0.3,
            "meta": {
                "title": title,
                "description": self.fake.article_excerpt(160),
                "robots": random.choice(["index,follow", "noindex,nofollow"]),
            },
            "custom_css": None,
            "custom_js": None,
            "published_at": self.fake.datetime().isoformat(),
            "created_at": self.fake.datetime().isoformat(),
            "updated_at": self.fake.datetime().isoformat(),
        }
        page.update(overrides)
        return page

    def media_item(self, **overrides: Any) -> dict:
        """Generate a media item (image, video, etc.)."""
        media_types = [
            ("image", ["jpg", "png", "gif", "webp"]),
            ("video", ["mp4", "webm", "mov"]),
            ("audio", ["mp3", "wav", "ogg"]),
            ("document", ["pdf", "doc", "docx"]),
        ]
        media_type, extensions = random.choice(media_types)

        width, height = random.choice([
            (1920, 1080),
            (1280, 720),
            (800, 600),
            (400, 300),
        ])

        item = {
            "id": self.fake.uuid(),
            "filename": f"{self.fake.word()}_{self.fake.uuid()[:8]}.{random.choice(extensions)}",
            "type": media_type,
            "mime_type": f"{media_type}/{random.choice(extensions)}",
            "url": self.fake._faker.image_url(width, height) if media_type == "image" else self.fake.url(),
            "thumbnail_url": self.fake._faker.thumbnail_url() if media_type in ["image", "video"] else None,
            "size_bytes": random.randint(10000, 10000000),
            "width": width if media_type == "image" else None,
            "height": height if media_type == "image" else None,
            "duration_seconds": random.randint(10, 600) if media_type in ["video", "audio"] else None,
            "alt_text": self.fake.sentence(words=6) if media_type == "image" else None,
            "caption": self.fake.sentence() if random.random() > 0.5 else None,
            "folder": random.choice(["uploads", "media", "images", "documents"]),
            "tags": self.fake.tags(random.randint(1, 5)),
            "uploaded_by": self.fake.uuid(),
            "created_at": self.fake.datetime().isoformat(),
        }
        item.update(overrides)
        return item

    def media_library(self, count: int = 20) -> list[dict]:
        """Generate a media library."""
        return [self.media_item() for _ in range(count)]

    def gallery(self, image_count: int = 10, **overrides: Any) -> dict:
        """Generate an image gallery."""
        gallery = {
            "id": self.fake.uuid(),
            "title": self.fake.sentence(words=4).rstrip("."),
            "description": self.fake.text(200),
            "slug": self.fake.article_slug(),
            "cover_image": self.fake._faker.featured_image_url(),
            "images": [
                {
                    "id": self.fake.uuid(),
                    "url": self.fake._faker.image_url(),
                    "thumbnail_url": self.fake._faker.thumbnail_url(),
                    "alt": self.fake.sentence(words=5),
                    "caption": self.fake.sentence() if random.random() > 0.5 else None,
                    "order": i,
                }
                for i in range(image_count)
            ],
            "is_public": random.random() > 0.2,
            "views": random.randint(0, 10000),
            "created_at": self.fake.datetime().isoformat(),
        }
        gallery.update(overrides)
        return gallery

    def category(self, parent_id: str | None = None, **overrides: Any) -> dict:
        """Generate a content category."""
        name = self.fake._faker.category()
        category = {
            "id": self.fake.uuid(),
            "name": name,
            "slug": self.fake.article_slug(name),
            "description": self.fake.text(200),
            "parent_id": parent_id,
            "image_url": self.fake._faker.image_url() if random.random() > 0.5 else None,
            "post_count": random.randint(0, 100),
            "order": random.randint(0, 50),
            "is_visible": random.random() > 0.1,
            "meta": {
                "title": name,
                "description": self.fake.article_excerpt(160),
            },
            "created_at": self.fake.datetime().isoformat(),
        }
        category.update(overrides)
        return category

    def category_tree(self, depth: int = 2, children_per_level: int = 3) -> list[dict]:
        """Generate a category tree with nested categories."""
        categories = []

        root_count = random.randint(3, 6)
        for _ in range(root_count):
            root = self.category()
            categories.append(root)

            if depth > 0:
                child_count = random.randint(1, children_per_level)
                for _ in range(child_count):
                    child = self.category(parent_id=root["id"])
                    categories.append(child)

                    if depth > 1:
                        grandchild_count = random.randint(0, 2)
                        for _ in range(grandchild_count):
                            grandchild = self.category(parent_id=child["id"])
                            categories.append(grandchild)

        return categories

    def tag(self, **overrides: Any) -> dict:
        """Generate a content tag."""
        name = self.fake.tag()
        tag = {
            "id": self.fake.uuid(),
            "name": name,
            "slug": name.lower().replace(" ", "-"),
            "description": self.fake.sentence() if random.random() > 0.5 else None,
            "post_count": random.randint(0, 500),
            "is_featured": random.random() > 0.9,
            "created_at": self.fake.datetime().isoformat(),
        }
        tag.update(overrides)
        return tag

    def newsletter(self, **overrides: Any) -> dict:
        """Generate a newsletter."""
        title = self.fake.sentence(words=6).rstrip(".")
        newsletter = {
            "id": self.fake.uuid(),
            "title": title,
            "subject": title,
            "preview_text": self.fake.sentence(),
            "content_html": self.fake._faker.article_body_html(5),
            "content_text": self.fake._faker.article_body(5),
            "template": random.choice(["default", "promotional", "announcement"]),
            "status": random.choice(["draft", "scheduled", "sent", "cancelled"]),
            "recipient_count": random.randint(100, 10000),
            "open_count": random.randint(0, 5000),
            "click_count": random.randint(0, 1000),
            "open_rate": round(random.uniform(0.1, 0.5), 2),
            "click_rate": round(random.uniform(0.01, 0.1), 2),
            "unsubscribe_count": random.randint(0, 50),
            "scheduled_at": (
                self.fake.future_datetime(days=7).isoformat()
                if random.random() > 0.5 else None
            ),
            "sent_at": (
                self.fake.past_datetime(days=30).isoformat()
                if random.random() > 0.3 else None
            ),
            "created_at": self.fake.datetime().isoformat(),
        }
        newsletter.update(overrides)
        return newsletter

    def subscriber(self, **overrides: Any) -> dict:
        """Generate a newsletter subscriber."""
        subscriber = {
            "id": self.fake.uuid(),
            "email": self.fake.email(),
            "name": self.fake.name() if random.random() > 0.3 else None,
            "status": random.choice(["active", "unsubscribed", "bounced", "complained"]),
            "source": random.choice(["website", "checkout", "popup", "import", "api"]),
            "tags": self.fake.tags(random.randint(0, 5)),
            "preferences": {
                "frequency": random.choice(["daily", "weekly", "monthly"]),
                "categories": [self.fake._faker.category() for _ in range(random.randint(1, 4))],
            },
            "ip_address": self.fake._faker.ipv4(),
            "confirmed_at": self.fake.datetime().isoformat() if random.random() > 0.1 else None,
            "unsubscribed_at": None,
            "created_at": self.fake.datetime().isoformat(),
        }
        subscriber.update(overrides)
        return subscriber

    def content_feed(
        self,
        count: int = 20,
        content_types: list[str] | None = None,
    ) -> list[dict]:
        """Generate a content feed with mixed content types.

        Args:
            count: Number of items to generate.
            content_types: Types to include (article, post, media).

        Returns:
            A list of content items sorted by date.
        """
        if content_types is None:
            content_types = ["article", "post", "media"]

        feed = []
        for _ in range(count):
            content_type = random.choice(content_types)

            if content_type == "article":
                item = self.article()
                item["content_type"] = "article"
            elif content_type == "post":
                item = self.blog_post()
                item["content_type"] = "post"
            else:
                item = self.media_item()
                item["content_type"] = "media"

            feed.append(item)

        return sorted(feed, key=lambda x: x["created_at"], reverse=True)

    def search_result(self, query: str = "", **overrides: Any) -> dict:
        """Generate a search result."""
        content_types = ["article", "page", "product", "user"]
        content_type = random.choice(content_types)

        result = {
            "id": self.fake.uuid(),
            "type": content_type,
            "title": self.fake.sentence(words=6).rstrip("."),
            "excerpt": self.fake.text(200),
            "url": self.fake.url(),
            "thumbnail_url": self.fake._faker.thumbnail_url() if random.random() > 0.3 else None,
            "score": round(random.uniform(0.5, 1.0), 3),
            "highlights": [
                {
                    "field": "content",
                    "snippet": f"...{query}...",
                }
            ] if query else [],
            "created_at": self.fake.datetime().isoformat(),
        }
        result.update(overrides)
        return result

    def search_results(
        self,
        query: str = "",
        count: int = 10,
    ) -> dict:
        """Generate search results with metadata."""
        results = [self.search_result(query) for _ in range(count)]

        return {
            "query": query or self.fake.word(),
            "total": random.randint(count, count * 10),
            "page": 1,
            "per_page": count,
            "results": results,
            "facets": {
                "type": {
                    "article": random.randint(10, 100),
                    "page": random.randint(5, 50),
                    "product": random.randint(20, 200),
                },
                "category": {
                    self.fake._faker.category(): random.randint(5, 50)
                    for _ in range(5)
                },
            },
            "suggestions": self.fake.words(3),
            "took_ms": random.randint(10, 100),
        }

    def revision(
        self,
        content_id: str | None = None,
        user_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a content revision."""
        revision = {
            "id": self.fake.uuid(),
            "content_id": content_id or self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "user_name": self.fake.name(),
            "version": random.randint(1, 50),
            "title": self.fake.sentence(words=6).rstrip("."),
            "content": self.fake._faker.article_body(3),
            "changes_summary": random.choice([
                "Updated content",
                "Fixed typos",
                "Added new section",
                "Reorganized structure",
                "Updated images",
            ]),
            "is_current": False,
            "created_at": self.fake.datetime().isoformat(),
        }
        revision.update(overrides)
        return revision

    def content_with_revisions(
        self,
        revision_count: int = 5,
        **overrides: Any,
    ) -> dict:
        """Generate content with revision history."""
        article = self.article(**overrides)
        content_id = article["id"]

        revisions = []
        for i in range(revision_count):
            revision = self.revision(
                content_id=content_id,
                version=i + 1,
                is_current=(i == revision_count - 1),
            )
            revisions.append(revision)

        article["revisions"] = revisions
        article["current_version"] = revision_count
        return article


# Global instance for convenience
content = ContentGenerator()


def create_content_generator(
    locale: str = "en_US",
    seed: int | None = None,
) -> ContentGenerator:
    """Create a new ContentGenerator with custom settings.

    Args:
        locale: Locale for generated data.
        seed: Seed for reproducible generation.

    Returns:
        A configured ContentGenerator instance.
    """
    from venomqa.data.generators import create_fake

    return ContentGenerator(fake=create_fake(locale, seed))
