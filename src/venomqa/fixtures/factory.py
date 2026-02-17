"""Factory Boy-style data factories with lazy evaluation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

T = TypeVar("T")

try:
    from faker import Faker

    HAS_FAKER = True
except ImportError:
    HAS_FAKER = False
    Faker = None


class LazyAttribute:
    """Lazy attribute that evaluates a callable at creation time."""

    def __init__(self, func: Callable[[Any], Any]):
        self.func = func

    def evaluate(self, obj: Any = None) -> Any:
        return self.func(obj)


class LazyFunction:
    """Lazy attribute that calls a function with no arguments."""

    def __init__(self, func: Callable[[], Any]):
        self.func = func

    def evaluate(self) -> Any:
        return self.func()


class FactoryRegistry:
    """Registry for managing factories."""

    _factories: dict[str, type[DataFactory]] = {}

    @classmethod
    def register(cls, factory_class: type[DataFactory]) -> None:
        name = factory_class.__name__
        cls._factories[name] = factory_class

    @classmethod
    def get(cls, name: str) -> type[DataFactory] | None:
        return cls._factories.get(name)

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._factories.pop(name, None)

    @classmethod
    def clear(cls) -> None:
        cls._factories.clear()

    @classmethod
    def list_factories(cls) -> list[str]:
        return list(cls._factories.keys())


class FactoryContext:
    """Context for tracking created objects during factory operations."""

    def __init__(self):
        self._created: list[Any] = []
        self._by_type: dict[type, list[Any]] = {}

    def track(self, obj: Any) -> None:
        self._created.append(obj)
        obj_type = type(obj)
        if obj_type not in self._by_type:
            self._by_type[obj_type] = []
        self._by_type[obj_type].append(obj)

    def get_all(self) -> list[Any]:
        return self._created.copy()

    def get_by_type(self, obj_type: type) -> list[Any]:
        return self._by_type.get(obj_type, []).copy()

    def clear(self) -> None:
        self._created.clear()
        self._by_type.clear()

    def __len__(self) -> int:
        return len(self._created)


_current_context: FactoryContext | None = None


def get_context() -> FactoryContext:
    global _current_context
    if _current_context is None:
        _current_context = FactoryContext()
    return _current_context


def set_context(ctx: FactoryContext | None) -> None:
    global _current_context
    _current_context = ctx


class _FactoryContextManager:
    """Context manager for scoped factory creation."""

    def __init__(self):
        self.ctx = FactoryContext()
        self._previous: FactoryContext | None = None

    def __enter__(self) -> FactoryContext:
        global _current_context
        self._previous = _current_context
        _current_context = self.ctx
        return self.ctx

    def __exit__(self, *args: Any) -> None:
        global _current_context
        _current_context = self._previous


factory_context = _FactoryContextManager  # noqa: N801


@dataclass
class DataFactory(Generic[T]):
    """Base factory class with lazy evaluation support."""

    _model: type[T] | None = None
    _faker: Faker | None = None
    _lazy_fields: dict[str, LazyAttribute | LazyFunction] = field(default_factory=dict, repr=False)

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)
        FactoryRegistry.register(cls)
        cls._lazy_fields = {}
        for attr_name, attr_value in cls.__dict__.items():
            if isinstance(attr_value, (LazyAttribute, LazyFunction)):
                cls._lazy_fields[attr_name] = attr_value

    @classmethod
    def _get_faker(cls) -> Any:
        if cls._faker is None:
            if HAS_FAKER:
                from venomqa.fixtures.providers import get_faker

                cls._faker = get_faker()
            else:
                raise ImportError("Faker is not installed. Install with: pip install faker")
        return cls._faker

    @classmethod
    def _resolve_value(cls, key: str, value: Any, instance: Any = None) -> Any:
        if isinstance(value, LazyAttribute):
            return value.evaluate(instance)
        elif isinstance(value, LazyFunction):
            return value.evaluate()
        elif callable(value) and not isinstance(value, type):
            return value()
        return value

    @classmethod
    def _build_kwargs(cls, **kwargs: Any) -> dict[str, Any]:
        result = {}
        for key, value in cls.__dict__.items():
            if not key.startswith("_") and not callable(value):
                if key not in kwargs:
                    result[key] = cls._resolve_value(key, value)
        result.update(kwargs)
        return result

    @classmethod
    def build(cls, **kwargs: Any) -> T:
        """Build an instance without tracking in context."""
        data = cls._build_kwargs(**kwargs)
        if cls._model is not None:
            if is_dataclass(cls._model):
                return cls._model(**data)
            return cls._model(**data)
        return data

    @classmethod
    def create(cls, **kwargs: Any) -> T:
        """Create an instance and track in context."""
        instance = cls.build(**kwargs)
        get_context().track(instance)
        return instance

    @classmethod
    def build_batch(cls, size: int, **kwargs: Any) -> list[T]:
        """Build multiple instances without tracking."""
        return [cls.build(**kwargs) for _ in range(size)]

    @classmethod
    def create_batch(cls, size: int, **kwargs: Any) -> list[T]:
        """Create multiple instances with tracking."""
        return [cls.create(**kwargs) for _ in range(size)]

    @classmethod
    def to_dict(cls, instance: T) -> dict[str, Any]:
        """Convert instance to dictionary."""
        if is_dataclass(instance):
            result = {}
            for f in fields(instance):
                value = getattr(instance, f.name)
                result[f.name] = cls._serialize_value(value)
            return result
        elif isinstance(instance, dict):
            return instance
        return {"value": instance}

    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        elif is_dataclass(value):
            return cls.to_dict(value)
        elif isinstance(value, list):
            return [cls._serialize_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: cls._serialize_value(v) for k, v in value.items()}
        return value

    @classmethod
    def to_json(cls, instance: T) -> str:
        """Convert instance to JSON string."""
        return json.dumps(cls.to_dict(instance))


@dataclass
class User:
    id: int
    email: str
    username: str
    first_name: str
    last_name: str
    is_active: bool
    created_at: datetime
    user_type: str


@dataclass
class Item:
    id: int
    name: str
    sku: str
    price: float
    quantity: int
    category: str
    description: str
    created_at: datetime


@dataclass
class OrderItem:
    item_id: int
    quantity: int
    unit_price: float
    subtotal: float


@dataclass
class Order:
    id: int
    user_id: int
    status: str
    items: list[OrderItem]
    total: float
    shipping_address: str
    payment_method: str
    created_at: datetime


class UserFactory(DataFactory[User]):
    """Factory for creating User instances."""

    _model = User

    id: int = LazyFunction(lambda: UserFactory._get_faker().random_int(min=1, max=10000))
    email: LazyAttribute = LazyAttribute(lambda _: UserFactory._get_faker().email())
    username: LazyAttribute = LazyAttribute(lambda _: UserFactory._get_faker().user_name())
    first_name: LazyAttribute = LazyAttribute(lambda _: UserFactory._get_faker().first_name())
    last_name: LazyAttribute = LazyAttribute(lambda _: UserFactory._get_faker().last_name())
    is_active: bool = True
    created_at: LazyAttribute = LazyAttribute(
        lambda _: UserFactory._get_faker().date_time_this_year()
    )
    user_type: LazyAttribute = LazyAttribute(lambda _: UserFactory._get_faker().user_type())


class ItemFactory(DataFactory[Item]):
    """Factory for creating Item instances."""

    _model = Item

    id: int = LazyFunction(lambda: ItemFactory._get_faker().random_int(min=1, max=10000))
    name: LazyAttribute = LazyAttribute(lambda _: ItemFactory._get_faker().product_name())
    sku: LazyAttribute = LazyAttribute(lambda _: ItemFactory._get_faker().sku())
    price: LazyAttribute = LazyAttribute(lambda _: ItemFactory._get_faker().price())
    quantity: LazyAttribute = LazyAttribute(lambda _: ItemFactory._get_faker().quantity())
    category: LazyAttribute = LazyAttribute(lambda _: ItemFactory._get_faker().product_category())
    description: LazyAttribute = LazyAttribute(lambda _: ItemFactory._get_faker().sentence())
    created_at: LazyAttribute = LazyAttribute(
        lambda _: ItemFactory._get_faker().date_time_this_year()
    )


class OrderItemFactory(DataFactory[OrderItem]):
    """Factory for creating OrderItem instances."""

    _model = OrderItem

    item_id: int = LazyFunction(lambda: OrderItemFactory._get_faker().random_int(min=1, max=10000))
    quantity: LazyAttribute = LazyAttribute(
        lambda _: OrderItemFactory._get_faker().quantity(max_qty=10)
    )
    unit_price: LazyAttribute = LazyAttribute(lambda _: OrderItemFactory._get_faker().price())
    subtotal: LazyAttribute = LazyAttribute(
        lambda obj: obj.quantity * obj.unit_price if obj else 0.0
    )


class OrderFactory(DataFactory[Order]):
    """Factory for creating Order instances."""

    _model = Order

    id: int = LazyFunction(lambda: OrderFactory._get_faker().random_int(min=1, max=10000))
    user_id: int = LazyFunction(lambda: OrderFactory._get_faker().random_int(min=1, max=10000))
    status: LazyAttribute = LazyAttribute(lambda _: OrderFactory._get_faker().order_status())
    items: list[OrderItem] = field(default_factory=list)
    total: float = 0.0
    shipping_address: LazyAttribute = LazyAttribute(
        lambda _: OrderFactory._get_faker().full_address()
    )
    payment_method: LazyAttribute = LazyAttribute(
        lambda _: OrderFactory._get_faker().payment_method()
    )
    created_at: LazyAttribute = LazyAttribute(
        lambda _: OrderFactory._get_faker().date_time_this_year()
    )

    @classmethod
    def build(cls, **kwargs: Any) -> Order:
        user = kwargs.pop("user", None)
        if user is not None:
            kwargs["user_id"] = user.id if hasattr(user, "id") else user

        items_data = kwargs.pop("items_data", None)
        if items_data is None:
            items_data = [{"quantity": 1, "unit_price": 50.0}]

        order_items = []
        total = 0.0
        for item_data in items_data:
            item = OrderItemFactory.build(**item_data)
            item.subtotal = item.quantity * item.unit_price
            order_items.append(item)
            total += item.subtotal

        kwargs["items"] = order_items
        kwargs["total"] = kwargs.get("total", total)

        return super().build(**kwargs)
