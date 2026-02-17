"""Product test data fixtures for e-commerce journeys.

Factory-based test data generation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from venomqa.fixtures.factory import DataFactory, LazyAttribute, LazyFunction


@dataclass
class Product:
    id: int
    name: str
    sku: str
    price: float
    compare_at_price: float | None
    stock: int
    category: str
    description: str
    is_active: bool
    created_at: datetime


@dataclass
class Category:
    id: int
    name: str
    slug: str
    parent_id: int | None
    description: str


@dataclass
class ProductVariant:
    id: int
    product_id: int
    sku: str
    name: str
    price: float
    stock: int
    attributes: dict


class ProductFactory(DataFactory[Product]):
    _model = Product

    id: int = LazyFunction(lambda: ProductFactory._get_faker().random_int(min=1, max=99999))
    name: LazyAttribute = LazyAttribute(lambda _: ProductFactory._get_faker().product_name())
    sku: LazyAttribute = LazyAttribute(lambda _: ProductFactory._get_faker().sku())
    price: LazyAttribute = LazyAttribute(lambda _: round(ProductFactory._get_faker().price(), 2))
    compare_at_price: LazyAttribute = LazyAttribute(
        lambda _: round(ProductFactory._get_faker().price() * 1.2, 2)
    )
    stock: LazyAttribute = LazyAttribute(
        lambda _: ProductFactory._get_faker().random_int(min=0, max=500)
    )
    category: LazyAttribute = LazyAttribute(
        lambda _: ProductFactory._get_faker().product_category()
    )
    description: LazyAttribute = LazyAttribute(lambda _: ProductFactory._get_faker().sentence())
    is_active: bool = True
    created_at: LazyAttribute = LazyAttribute(
        lambda _: ProductFactory._get_faker().date_time_this_year()
    )

    @classmethod
    def electronics(cls, **kwargs: Any) -> Product:
        return cls.build(
            category="Electronics",
            name=cls._get_faker().word()
            + " "
            + cls._get_faker().random_element(["Pro", "Plus", "Ultra", "Max"]),
            **kwargs,
        )

    @classmethod
    def clothing(cls, **kwargs: Any) -> Product:
        sizes = ["XS", "S", "M", "L", "XL", "XXL"]
        colors = ["Red", "Blue", "Green", "Black", "White"]
        return cls.build(
            category="Clothing",
            name=f"{cls._get_faker().random_element(colors)} "
            f"{cls._get_faker().word().title()} "
            f"{cls._get_faker().random_element(sizes)}",
            **kwargs,
        )

    @classmethod
    def in_stock(cls, **kwargs: Any) -> Product:
        return cls.build(stock=cls._get_faker().random_int(min=10, max=100), **kwargs)

    @classmethod
    def out_of_stock(cls, **kwargs: Any) -> Product:
        return cls.build(stock=0, **kwargs)

    @classmethod
    def on_sale(cls, discount_percent: float = 20.0, **kwargs: Any) -> Product:
        price = kwargs.get("price", cls._get_faker().price())
        return cls.build(
            price=round(price * (1 - discount_percent / 100), 2),
            compare_at_price=round(price, 2),
            **kwargs,
        )


class CategoryFactory(DataFactory[Category]):
    _model = Category

    id: int = LazyFunction(lambda: CategoryFactory._get_faker().random_int(min=1, max=9999))
    name: LazyAttribute = LazyAttribute(lambda _: CategoryFactory._get_faker().product_category())
    slug: LazyAttribute = LazyAttribute(lambda _: CategoryFactory._get_faker().slug())
    parent_id: int | None = None
    description: LazyAttribute = LazyAttribute(lambda _: CategoryFactory._get_faker().sentence())


class ProductVariantFactory(DataFactory[ProductVariant]):
    _model = ProductVariant

    id: int = LazyFunction(lambda: ProductVariantFactory._get_faker().random_int(min=1, max=99999))
    product_id: int = LazyFunction(
        lambda: ProductVariantFactory._get_faker().random_int(min=1, max=9999)
    )
    sku: LazyAttribute = LazyAttribute(lambda _: ProductVariantFactory._get_faker().sku())
    name: LazyAttribute = LazyAttribute(lambda _: ProductVariantFactory._get_faker().word())
    price: LazyAttribute = LazyAttribute(
        lambda _: round(ProductVariantFactory._get_faker().price(), 2)
    )
    stock: LazyAttribute = LazyAttribute(
        lambda _: ProductVariantFactory._get_faker().random_int(min=0, max=100)
    )
    attributes: dict = {}

    @classmethod
    def with_size(cls, size: str = "M", **kwargs: Any) -> ProductVariant:
        return cls.build(name=f"Size {size}", attributes={"size": size}, **kwargs)

    @classmethod
    def with_color(cls, color: str = "Blue", **kwargs: Any) -> ProductVariant:
        return cls.build(name=f"{color} Variant", attributes={"color": color}, **kwargs)
