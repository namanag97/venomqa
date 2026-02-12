"""Test file generation utilities for images, PDFs, CSVs, JSON, and binary files."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import random
import string
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GeneratedFile:
    """Result of file generation."""

    path: Path
    filename: str
    size_bytes: int
    content_type: str
    hash_md5: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def read_text(self) -> str:
        return self.path.read_text()

    def cleanup(self) -> None:
        if self.path.exists():
            self.path.unlink()


class FileGenerator:
    """Base class for test file generators."""

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = (
            Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="venomqa_gen_"))
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _generate_filename(self, prefix: str = "test", extension: str = "dat") -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"{prefix}_{timestamp}_{unique_id}.{extension}"

    def _create_result(
        self,
        path: Path,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> GeneratedFile:
        content = path.read_bytes()
        return GeneratedFile(
            path=path,
            filename=path.name,
            size_bytes=len(content),
            content_type=content_type,
            hash_md5=hashlib.md5(content).hexdigest(),
            metadata=metadata or {},
        )


class ImageGenerator(FileGenerator):
    """Generate test images in various formats."""

    SUPPORTED_FORMATS = ("png", "jpeg", "jpg", "gif", "bmp", "webp")

    def generate(
        self,
        size: tuple[int, int] = (100, 100),
        format: str = "png",
        color: tuple[int, int, int] | None = None,
        gradient: bool = False,
        pattern: str | None = None,
        text: str | None = None,
        filename: str | None = None,
    ) -> GeneratedFile:
        try:
            from PIL import Image, ImageDraw
        except ImportError as e:
            raise ImportError(
                "Pillow is required for image generation. Install with: pip install Pillow"
            ) from e

        format_lower = format.lower()
        if format_lower == "jpg":
            format_lower = "jpeg"

        if format_lower not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported image format: {format}. Supported: {self.SUPPORTED_FORMATS}"
            )

        img = Image.new(
            "RGB",
            size,
            color=color or (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)),
        )

        if gradient:
            for y in range(size[1]):
                r = int((y / size[1]) * 255)
                for x in range(size[0]):
                    g = int((x / size[0]) * 255)
                    img.putpixel((x, y), (r, g, 128))

        if pattern:
            draw = ImageDraw.Draw(img)
            self._draw_pattern(draw, size, pattern)

        if text:
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), text, fill=(255, 255, 255))

        ext = "jpg" if format_lower == "jpeg" else format_lower
        output_filename = filename or self._generate_filename(prefix="image", extension=ext)
        output_path = self.output_dir / output_filename

        save_kwargs = {}
        if format_lower == "jpeg":
            save_kwargs["quality"] = 85

        img.save(output_path, format=format_lower.upper(), **save_kwargs)

        content_types = {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "jpg": "image/jpeg",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "webp": "image/webp",
        }

        return self._create_result(
            output_path,
            content_types.get(format_lower, "image/png"),
            metadata={"size": size, "format": format_lower},
        )

    def _draw_pattern(self, draw, size: tuple[int, int], pattern: str) -> None:
        if pattern == "grid":
            for x in range(0, size[0], 20):
                draw.line([(x, 0), (x, size[1])], fill=(200, 200, 200))
            for y in range(0, size[1], 20):
                draw.line([(0, y), (size[0], y)], fill=(200, 200, 200))
        elif pattern == "circles":
            for i in range(0, min(size), 30):
                draw.ellipse([i, i, size[0] - i, size[1] - i], outline=(100, 100, 100))
        elif pattern == "stripes":
            for i in range(0, size[1], 10):
                color = (0, 0, 0) if (i // 10) % 2 == 0 else (255, 255, 255)
                draw.rectangle([0, i, size[0], i + 10], fill=color)

    def generate_png(self, size: tuple[int, int] = (100, 100), **kwargs) -> GeneratedFile:
        return self.generate(size=size, format="png", **kwargs)

    def generate_jpeg(self, size: tuple[int, int] = (100, 100), **kwargs) -> GeneratedFile:
        return self.generate(size=size, format="jpeg", **kwargs)

    def generate_thumbnail(
        self, source_path: str | Path, size: tuple[int, int] = (64, 64)
    ) -> GeneratedFile:
        try:
            from PIL import Image
        except ImportError as e:
            raise ImportError("Pillow is required. Install with: pip install Pillow") from e

        with Image.open(source_path) as img:
            img.thumbnail(size)
            output_filename = self._generate_filename(prefix="thumb", extension="png")
            output_path = self.output_dir / output_filename
            img.save(output_path, "PNG")

        return self._create_result(
            output_path,
            "image/png",
            metadata={"original": str(source_path), "thumbnail_size": size},
        )


class PDFGenerator(FileGenerator):
    """Generate test PDF files."""

    def generate(
        self,
        pages: int = 1,
        title: str = "Test Document",
        content: list[str] | None = None,
        include_images: bool = False,
        filename: str | None = None,
    ) -> GeneratedFile:
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate
        except ImportError as e:
            raise ImportError(
                "reportlab is required for PDF generation. Install with: pip install reportlab"
            ) from e

        output_filename = filename or self._generate_filename(prefix="document", extension="pdf")
        output_path = self.output_dir / output_filename

        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(title, styles["Title"]))
        story.append(Paragraph(f"Generated: {datetime.now().isoformat()}", styles["Normal"]))
        story.append(Paragraph(f"Pages: {pages}", styles["Normal"]))
        story.append(Paragraph("", styles["Normal"]))

        for page_num in range(pages):
            if page_num > 0:
                story.append(PageBreak())

            story.append(Paragraph(f"Page {page_num + 1}", styles["Heading1"]))

            if content and page_num < len(content):
                story.append(Paragraph(content[page_num], styles["Normal"]))
            else:
                paragraphs = self._generate_random_paragraphs(3)
                for para in paragraphs:
                    story.append(Paragraph(para, styles["Normal"]))

            if include_images:
                img_gen = ImageGenerator(self.output_dir)
                img_file = img_gen.generate(size=(200, 200))
                story.append(Image(str(img_file.path), width=2 * inch, height=2 * inch))

        doc.build(story)

        return self._create_result(
            output_path,
            "application/pdf",
            metadata={"pages": pages, "title": title},
        )

    def _generate_random_paragraphs(self, count: int) -> list[str]:
        lorem = [
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.",
            "Duis aute irure dolor in reprehenderit in voluptate velit esse.",
            "Excepteur sint occaecat cupidatat non proident, sunt in culpa.",
        ]
        return [random.choice(lorem) for _ in range(count)]

    def generate_invoice(
        self,
        invoice_number: str = "INV-001",
        items: list[dict[str, Any]] | None = None,
        filename: str | None = None,
    ) -> GeneratedFile:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
        except ImportError as e:
            raise ImportError("reportlab is required. Install with: pip install reportlab") from e

        items = items or [
            {"description": "Service A", "quantity": 1, "price": 100.00},
            {"description": "Service B", "quantity": 2, "price": 50.00},
        ]

        output_filename = filename or self._generate_filename(prefix="invoice", extension="pdf")
        output_path = self.output_dir / output_filename

        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"Invoice #{invoice_number}", styles["Title"]))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d')}", styles["Normal"]))
        story.append(Paragraph("", styles["Normal"]))

        table_data = [["Description", "Quantity", "Price", "Total"]]
        total = 0
        for item in items:
            item_total = item["quantity"] * item["price"]
            total += item_total
            table_data.append(
                [
                    item["description"],
                    str(item["quantity"]),
                    f"${item['price']:.2f}",
                    f"${item_total:.2f}",
                ]
            )
        table_data.append(["", "", "Total:", f"${total:.2f}"])

        table = Table(table_data, colWidths=[3 * inch, 1 * inch, 1 * inch, 1 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -2), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )

        story.append(table)
        doc.build(story)

        return self._create_result(
            output_path,
            "application/pdf",
            metadata={"invoice_number": invoice_number, "total": total},
        )


class CSVGenerator(FileGenerator):
    """Generate test CSV files."""

    def generate(
        self,
        rows: int = 10,
        columns: int = 5,
        headers: list[str] | None = None,
        data_types: list[str] | None = None,
        delimiter: str = ",",
        include_header: bool = True,
        filename: str | None = None,
    ) -> GeneratedFile:
        output_filename = filename or self._generate_filename(prefix="data", extension="csv")
        output_path = self.output_dir / output_filename

        if headers is None:
            headers = [f"column_{i + 1}" for i in range(columns)]

        if data_types is None:
            data_types = ["string"] * columns

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=delimiter)

            if include_header:
                writer.writerow(headers)

            for _ in range(rows):
                row = []
                for _i, dtype in enumerate(data_types[:columns]):
                    row.append(self._generate_value(dtype))
                writer.writerow(row)

        return self._create_result(
            output_path,
            "text/csv",
            metadata={"rows": rows, "columns": columns, "delimiter": delimiter},
        )

    def _generate_value(self, dtype: str) -> Any:
        if dtype == "string":
            return "".join(random.choices(string.ascii_letters, k=random.randint(5, 15)))
        elif dtype == "integer":
            return random.randint(0, 1000)
        elif dtype == "float":
            return round(random.random() * 1000, 2)
        elif dtype == "boolean":
            return random.choice(["true", "false"])
        elif dtype == "date":
            return (datetime.now() - timedelta(days=random.randint(0, 365))).strftime("%Y-%m-%d")
        elif dtype == "email":
            return f"{random.choice(string.ascii_lowercase)}@test.com"
        elif dtype == "uuid":
            return str(uuid.uuid4())
        else:
            return "".join(random.choices(string.ascii_letters, k=10))

    def generate_users(self, count: int = 10, filename: str | None = None) -> GeneratedFile:
        return self.generate(
            rows=count,
            columns=5,
            headers=["id", "name", "email", "created_at", "active"],
            data_types=["uuid", "string", "email", "date", "boolean"],
            filename=filename,
        )

    def generate_transactions(
        self,
        count: int = 100,
        filename: str | None = None,
    ) -> GeneratedFile:
        return self.generate(
            rows=count,
            columns=6,
            headers=["transaction_id", "user_id", "amount", "currency", "status", "timestamp"],
            data_types=["uuid", "uuid", "float", "string", "string", "date"],
            filename=filename,
        )


class JSONGenerator(FileGenerator):
    """Generate test JSON files."""

    def generate(
        self,
        data: Any = None,
        schema: dict[str, Any] | None = None,
        root_type: str = "object",
        count: int = 10,
        pretty: bool = True,
        filename: str | None = None,
    ) -> GeneratedFile:
        output_filename = filename or self._generate_filename(prefix="data", extension="json")
        output_path = self.output_dir / output_filename

        if data is not None:
            json_data = data
        elif schema is not None:
            json_data = self._generate_from_schema(schema)
        else:
            json_data = self._generate_random(root_type, count)

        with open(output_path, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(json_data, f, indent=2, default=str)
            else:
                json.dump(json_data, f, default=str)

        return self._create_result(
            output_path,
            "application/json",
            metadata={"root_type": root_type, "count": count},
        )

    def _generate_random(self, root_type: str, count: int) -> Any:
        if root_type == "object":
            return {
                "id": str(uuid.uuid4()),
                "name": "".join(random.choices(string.ascii_letters, k=10)),
                "value": random.randint(0, 100),
                "active": random.choice([True, False]),
                "created_at": datetime.now().isoformat(),
            }
        elif root_type == "array":
            return [self._generate_random("object", 0) for _ in range(count)]
        elif root_type == "nested":
            return {
                "user": {
                    "id": str(uuid.uuid4()),
                    "profile": {
                        "name": "Test User",
                        "email": "test@example.com",
                    },
                },
                "items": [{"id": i, "value": random.randint(0, 100)} for i in range(count)],
            }
        else:
            return "test_value"

    def _generate_from_schema(self, schema: dict[str, Any]) -> Any:
        if "type" not in schema:
            return {}

        schema_type = schema["type"]

        if schema_type == "object":
            result = {}
            properties = schema.get("properties", {})
            for key, prop_schema in properties.items():
                result[key] = self._generate_from_schema(prop_schema)
            return result

        elif schema_type == "array":
            items_schema = schema.get("items", {})
            min_items = schema.get("minItems", 1)
            return [self._generate_from_schema(items_schema) for _ in range(min_items)]

        elif schema_type == "string":
            if schema.get("format") == "email":
                return "test@example.com"
            elif schema.get("format") == "date-time":
                return datetime.now().isoformat()
            elif schema.get("format") == "uuid":
                return str(uuid.uuid4())
            return "".join(random.choices(string.ascii_letters, k=10))

        elif schema_type == "integer":
            minimum = schema.get("minimum", 0)
            maximum = schema.get("maximum", 100)
            return random.randint(minimum, maximum)

        elif schema_type == "number":
            minimum = schema.get("minimum", 0.0)
            maximum = schema.get("maximum", 100.0)
            return round(random.uniform(minimum, maximum), 2)

        elif schema_type == "boolean":
            return random.choice([True, False])

        return None

    def generate_api_response(
        self,
        success: bool = True,
        data: Any = None,
        message: str = "OK",
        filename: str | None = None,
    ) -> GeneratedFile:
        response = {
            "success": success,
            "message": message,
            "data": data or {"id": str(uuid.uuid4()), "value": "test"},
            "timestamp": datetime.now().isoformat(),
        }
        return self.generate(data=response, filename=filename)

    def generate_error_response(
        self,
        error_code: str = "VALIDATION_ERROR",
        message: str = "Invalid input",
        details: list[str] | None = None,
        filename: str | None = None,
    ) -> GeneratedFile:
        response = {
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "details": details or ["Field 'name' is required"],
            },
            "timestamp": datetime.now().isoformat(),
        }
        return self.generate(data=response, filename=filename)


class BinaryGenerator(FileGenerator):
    """Generate binary test files."""

    def generate(
        self,
        size_bytes: int = 1024,
        pattern: str = "random",
        content_type: str = "application/octet-stream",
        filename: str | None = None,
    ) -> GeneratedFile:
        output_filename = filename or self._generate_filename(prefix="binary", extension="bin")
        output_path = self.output_dir / output_filename

        if pattern == "random":
            data = os.urandom(size_bytes)
        elif pattern == "zeros":
            data = b"\x00" * size_bytes
        elif pattern == "ones":
            data = b"\xff" * size_bytes
        elif pattern == "sequential":
            data = bytes(range(256)) * (size_bytes // 256 + 1)
            data = data[:size_bytes]
        elif pattern == "text":
            data = "".join(random.choices(string.printable, k=size_bytes)).encode("utf-8")
        else:
            data = os.urandom(size_bytes)

        output_path.write_bytes(data)

        return self._create_result(
            output_path,
            content_type,
            metadata={"size_bytes": size_bytes, "pattern": pattern},
        )

    def generate_zip(
        self,
        files: list[tuple[str, bytes]] | None = None,
        file_count: int = 3,
        filename: str | None = None,
    ) -> GeneratedFile:
        import zipfile

        output_filename = filename or self._generate_filename(prefix="archive", extension="zip")
        output_path = self.output_dir / output_filename

        if files is None:
            files = []
            for i in range(file_count):
                content = f"File {i + 1} content: {uuid.uuid4()}".encode()
                files.append((f"file_{i + 1}.txt", content))

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files:
                zf.writestr(name, content)

        return self._create_result(
            output_path,
            "application/zip",
            metadata={"file_count": len(files)},
        )

    def generate_chunked(
        self,
        total_size: int = 10240,
        chunk_size: int = 1024,
        filename: str | None = None,
    ) -> GeneratedFile:
        output_filename = filename or self._generate_filename(prefix="chunked", extension="bin")
        output_path = self.output_dir / output_filename

        written = 0
        with open(output_path, "wb") as f:
            while written < total_size:
                chunk = os.urandom(min(chunk_size, total_size - written))
                f.write(chunk)
                written += len(chunk)

        return self._create_result(
            output_path,
            "application/octet-stream",
            metadata={"total_size": total_size, "chunk_size": chunk_size},
        )
