"""gRPC client for VenomQA with service method invocation support.

This module provides gRPC clients for testing gRPC services, including
support for unary, server streaming, client streaming, and bidirectional
streaming RPCs.

Classes:
    GrpcResponse: Data class for gRPC responses.
    ProtoMethod: Represents a gRPC method definition.
    ProtoService: Represents a gRPC service definition.
    GrpcClient: Synchronous gRPC client.
    AsyncgRPCClient: Asynchronous gRPC client.

Example:
    >>> from venomqa.clients.grpc import GrpcClient
    >>> client = GrpcClient("localhost:50051")
    >>> client.connect()
    >>> # Load proto module and register service
    >>> response = client.call("MyService", "MyMethod", request)
    >>> print(response.data)
"""

from __future__ import annotations

import importlib.util
import logging
import time
from collections.abc import AsyncGenerator, Generator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from venomqa.clients.base import (
    BaseAsyncClient,
    BaseClient,
    ValidationError,
)
from venomqa.errors import ConnectionError, RequestFailedError, RequestTimeoutError

if TYPE_CHECKING:
    import grpc

logger = logging.getLogger(__name__)


def _extract_grpc_error(e: Exception) -> tuple[int, str]:
    """Extract gRPC status code and details from an exception.

    Args:
        e: The exception to extract error info from.

    Returns:
        Tuple of (status_code, status_details).
    """
    err_str = str(e)
    status_code = getattr(e, "code", lambda: -1)()
    if callable(status_code):
        status_code = -1
    else:
        try:
            status_code = int(status_code)
        except (TypeError, ValueError):
            status_code = -1
    status_details = getattr(e, "details", lambda: err_str)()
    if callable(status_details):
        status_details = err_str
    return status_code, status_details


def _validate_grpc_service_method(service: str, method: str, stubs: dict[str, Any]) -> Any:
    """Validate service and method names and return the method function.

    Args:
        service: Service name to validate.
        method: Method name to validate.
        stubs: Dictionary of registered stubs.

    Returns:
        The method function from the stub.

    Raises:
        ValidationError: If service or method is invalid.
    """
    if not service:
        raise ValidationError(
            "Service name cannot be empty",
            field_name="service",
            value=service,
        )
    if not method:
        raise ValidationError(
            "Method name cannot be empty",
            field_name="method",
            value=method,
        )

    if service not in stubs:
        raise ValidationError(
            f"Service '{service}' not registered. Available: {list(stubs.keys())}",
            field_name="service",
            value=service,
        )

    stub = stubs[service]
    method_fn = getattr(stub, method, None)

    if method_fn is None:
        raise ValidationError(
            f"Method '{method}' not found on service '{service}'. "
            f"Available: {list(stubs[service].__class__.__dict__.keys())}",
            field_name="method",
            value=method,
        )

    return method_fn


@dataclass
class GrpcResponse:
    """Represents a gRPC response with status and metadata.

    Attributes:
        data: The response message/object from the gRPC call.
        status_code: gRPC status code (0 = OK).
        status_details: Human-readable status details.
        duration_ms: Response time in milliseconds.
        metadata: Response metadata (trailers).

    Example:
        >>> response = GrpcResponse(data=result, status_code=0, duration_ms=45.2)
        >>> if response.successful:
        ...     print(response.data)
    """

    data: Any
    status_code: int = 0
    status_details: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def successful(self) -> bool:
        """Check if the response indicates success.

        Returns:
            True if status_code is 0 (OK).
        """
        return self.status_code == 0

    def raise_for_status(self) -> None:
        """Raise exception if response has error status.

        Raises:
            RequestFailedError: If status_code is not 0.
        """
        if self.status_code != 0:
            raise RequestFailedError(
                message=f"gRPC error {self.status_code}: {self.status_details}",
                status_code=self.status_code,
            )


gRPCResponse = GrpcResponse  # noqa: N816


@dataclass
class ProtoMethod:
    """Represents a gRPC method definition.

    Attributes:
        name: Method name.
        service_name: Parent service name.
        package: Protocol package name.
        input_type: Input message type name.
        output_type: Output message type name.
        client_streaming: Whether method accepts client stream.
        server_streaming: Whether method returns server stream.
    """

    name: str
    service_name: str
    package: str
    input_type: str
    output_type: str
    client_streaming: bool = False
    server_streaming: bool = False

    @property
    def full_name(self) -> str:
        """Get fully qualified method name.

        Returns:
            package.Service/Method format.
        """
        if self.package:
            return f"{self.package}.{self.service_name}/{self.name}"
        return f"{self.service_name}/{self.name}"


@dataclass
class ProtoService:
    """Represents a gRPC service definition.

    Attributes:
        name: Service name.
        package: Protocol package name.
        methods: Dictionary of method name to ProtoMethod.
    """

    name: str
    package: str
    methods: dict[str, ProtoMethod] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        """Get fully qualified service name.

        Returns:
            package.Service format.
        """
        if self.package:
            return f"{self.package}.{self.name}"
        return self.name


def _validate_grpc_endpoint(endpoint: str) -> str:
    """Validate gRPC endpoint format.

    Args:
        endpoint: The gRPC endpoint (host:port or URL).

    Returns:
        Validated endpoint string.

    Raises:
        ValidationError: If endpoint is invalid.
    """
    if not endpoint:
        raise ValidationError(
            "gRPC endpoint cannot be empty",
            field_name="endpoint",
            value=endpoint,
        )

    endpoint = endpoint.strip()

    if endpoint.startswith(("http://", "https://")):
        raise ValidationError(
            "gRPC endpoint should not include http/https scheme. Use host:port format.",
            field_name="endpoint",
            value=endpoint,
        )

    return endpoint


class GrpcClient(BaseClient[GrpcResponse]):
    """Synchronous gRPC client with service method invocation support.

    Supports all gRPC communication patterns:
    - Unary RPC
    - Server streaming RPC
    - Client streaming RPC
    - Bidirectional streaming RPC

    Example:
        >>> from venomqa.clients.grpc import GrpcClient
        >>> client = GrpcClient("localhost:50051", use_tls=True)
        >>> client.connect()
        >>> proto = client.load_proto("generated/service_pb2.py")
        >>> client.register_service("MyService", proto.MyServiceStub)
        >>> response = client.call("MyService", "GetData", request)
        >>> print(response.data)

    Attributes:
        proto_dir: Directory containing proto files.
        default_metadata: Default gRPC metadata for all calls.
        use_tls: Whether to use TLS encryption.
    """

    def __init__(
        self,
        endpoint: str,
        proto_dir: str | Path | None = None,
        timeout: float = 30.0,
        default_metadata: list[tuple[str, str]] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        use_tls: bool = False,
        root_certificates: bytes | str | Path | None = None,
        private_key: bytes | str | Path | None = None,
        certificate_chain: bytes | str | Path | None = None,
    ) -> None:
        """Initialize the gRPC client.

        Args:
            endpoint: Server endpoint in host:port format.
            proto_dir: Directory containing compiled proto files (optional).
            timeout: Default RPC timeout in seconds (default: 30.0).
            default_metadata: Default metadata for all RPCs (optional).
            retry_count: Maximum retry attempts (default: 3).
            retry_delay: Base retry delay in seconds (default: 1.0).
            use_tls: Enable TLS encryption (default: False).
            root_certificates: Root CA certificates (optional).
            private_key: Client private key for mTLS (optional).
            certificate_chain: Client certificate chain for mTLS (optional).

        Raises:
            ValidationError: If parameters are invalid.
        """
        validated_endpoint = _validate_grpc_endpoint(endpoint)
        super().__init__(validated_endpoint, timeout, {}, retry_count, retry_delay)

        self.proto_dir = Path(proto_dir) if proto_dir else None
        self.default_metadata = default_metadata or []
        self.use_tls = use_tls
        self.root_certificates = self._load_cert(root_certificates)
        self.private_key = self._load_cert(private_key)
        self.certificate_chain = self._load_cert(certificate_chain)
        self._channel: grpc.Channel | None = None
        self._stubs: dict[str, Any] = {}
        self._services: dict[str, ProtoService] = {}
        self._loaded_modules: dict[str, Any] = {}

    def _load_cert(self, cert: bytes | str | Path | None) -> bytes | None:
        """Load certificate from bytes, file path, or return as-is.

        Args:
            cert: Certificate data or path.

        Returns:
            Certificate bytes, or None if not provided.
        """
        if cert is None:
            return None
        if isinstance(cert, bytes):
            return cert
        if isinstance(cert, (str, Path)):
            path = Path(cert)
            if path.exists():
                return path.read_bytes()
            logger.warning(f"Certificate file not found: {path}")
        return None

    def connect(self) -> None:
        """Establish gRPC channel connection.

        Creates either secure or insecure channel based on use_tls setting.

        Raises:
            ConnectionError: If connection fails.
        """
        import grpc

        if self._channel is not None:
            return

        try:
            if self.use_tls:
                credentials = self._create_credentials()
                self._channel = grpc.secure_channel(self.endpoint, credentials)
            else:
                self._channel = grpc.insecure_channel(self.endpoint)

            self._connected = True
            logger.info(f"gRPC client connected to {self.endpoint}")

        except Exception as e:
            raise ConnectionError(
                message=f"Failed to connect to gRPC server at {self.endpoint}: {e}"
            ) from e

    def _create_credentials(self) -> grpc.ChannelCredentials:
        """Create TLS channel credentials.

        Returns:
            gRPC channel credentials for secure connection.
        """
        import grpc

        return grpc.ssl_channel_credentials(
            root_certificates=self.root_certificates,
            private_key=self.private_key,
            certificate_chain=self.certificate_chain,
        )

    def disconnect(self) -> None:
        """Close gRPC channel connection.

        Clears all registered services and stubs.
        """
        if self._channel:
            self._channel.close()
            self._channel = None
        self._stubs.clear()
        self._services.clear()
        self._connected = False
        logger.info("gRPC client disconnected")

    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            True if channel is established.
        """
        return self._connected and self._channel is not None

    def load_proto(
        self,
        proto_file: str | Path,
        module_name: str | None = None,
    ) -> Any:
        """Load a compiled proto module dynamically.

        Args:
            proto_file: Path to the compiled _pb2.py file.
            module_name: Name for the module (default: proto file stem).

        Returns:
            The loaded proto module.

        Raises:
            FileNotFoundError: If proto file doesn't exist.
            ImportError: If module cannot be loaded.
            ValidationError: If proto_file is empty.
        """
        if not proto_file:
            raise ValidationError(
                "Proto file path cannot be empty",
                field_name="proto_file",
                value=proto_file,
            )

        proto_path = Path(proto_file)
        if not proto_path.exists():
            raise FileNotFoundError(f"Proto file not found: {proto_path}")

        module = module_name or proto_path.stem
        if module in self._loaded_modules:
            return self._loaded_modules[module]

        spec = importlib.util.spec_from_file_location(module, proto_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {proto_path}")

        loaded_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded_module)
        self._loaded_modules[module] = loaded_module

        return loaded_module

    def register_service(
        self,
        service_name: str,
        stub_class: Any,
        package: str = "",
    ) -> ProtoService:
        """Register a gRPC service with its stub class.

        Args:
            service_name: Name to identify the service.
            stub_class: The generated stub class from proto compilation.
            package: Protocol package name (optional).

        Returns:
            ProtoService instance for the registered service.

        Raises:
            ValidationError: If service_name is empty.
            ConnectionError: If not connected.
        """
        if not service_name:
            raise ValidationError(
                "Service name cannot be empty",
                field_name="service_name",
                value=service_name,
            )

        if not self._connected:
            self.connect()

        if self._channel is None:
            raise ConnectionError(message="gRPC channel not established")

        stub = stub_class(self._channel)
        self._stubs[service_name] = stub

        service = ProtoService(name=service_name, package=package)
        self._services[service_name] = service

        for name in dir(stub):
            if not name.startswith("_"):
                method_info = getattr(stub, name, None)
                if callable(method_info):
                    service.methods[name] = ProtoMethod(
                        name=name,
                        service_name=service_name,
                        package=package,
                        input_type="",
                        output_type="",
                    )

        logger.info(f"Registered gRPC service: {service_name}")
        return service

    def get_metadata(self) -> list[tuple[str, str]]:
        """Get metadata including auth tokens.

        Returns:
            List of metadata tuples for gRPC call.
        """
        metadata = list(self.default_metadata)
        auth_header = self.get_auth_header()
        if auth_header:
            token = auth_header.get("Authorization", "")
            if token.startswith("Bearer "):
                metadata.append(("authorization", token))
        return metadata

    def call(
        self,
        service: str,
        method: str,
        request: Any,
        timeout: float | None = None,
        metadata: list[tuple[str, str]] | None = None,
    ) -> gRPCResponse:
        """Call a unary gRPC method.

        Args:
            service: Registered service name.
            method: Method name on the service.
            request: Request message object.
            timeout: RPC timeout in seconds (optional).
            metadata: Additional metadata for this call (optional).

        Returns:
            gRPCResponse with result or error.

        Raises:
            ValidationError: If service/method not found.
            RequestTimeoutError: If call times out.
        """
        self._ensure_connected()
        method_fn = _validate_grpc_service_method(service, method, self._stubs)

        call_metadata = self.get_metadata()
        if metadata:
            call_metadata.extend(metadata)

        timeout_val = timeout if timeout is not None else self.timeout
        start_time = time.perf_counter()

        try:
            response = method_fn(
                request,
                timeout=timeout_val,
                metadata=call_metadata,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000

            grpc_response = gRPCResponse(
                data=response,
                status_code=0,
                duration_ms=duration_ms,
            )

            self._record_request(
                operation=f"{service}/{method}",
                request_data=str(request)[:500] if request else None,
                response_data=str(response)[:500] if response else None,
                duration_ms=duration_ms,
            )

            return grpc_response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            status_code, status_details = _extract_grpc_error(e)

            self._record_request(
                operation=f"{service}/{method}",
                request_data=str(request)[:500] if request else None,
                response_data=None,
                duration_ms=duration_ms,
                error=status_details,
                metadata={"status_code": status_code},
            )

            if "timeout" in status_details.lower() or status_code == 4:
                raise RequestTimeoutError(
                    message=f"gRPC call to {service}/{method} timed out after {timeout_val}s"
                ) from e

            return gRPCResponse(
                data=None,
                status_code=status_code,
                status_details=status_details,
                duration_ms=duration_ms,
            )

    def stream(
        self,
        service: str,
        method: str,
        requests: Iterator[Any] | None = None,
        timeout: float | None = None,
        metadata: list[tuple[str, str]] | None = None,
    ) -> Generator[gRPCResponse, None, None]:
        """Call a streaming gRPC method.

        Supports:
        - Server streaming: requests is None
        - Client streaming: requests is an iterator
        - Bidirectional streaming: requests is an iterator

        Args:
            service: Registered service name.
            method: Method name on the service.
            requests: Iterator of request messages (optional).
            timeout: RPC timeout in seconds (optional).
            metadata: Additional metadata for this call (optional).

        Yields:
            gRPCResponse for each response in the stream.
        """
        self._ensure_connected()

        if not service:
            raise ValidationError(
                "Service name cannot be empty",
                field_name="service",
                value=service,
            )

        if service not in self._stubs:
            raise ValidationError(
                f"Service '{service}' not registered",
                field_name="service",
                value=service,
            )

        stub = self._stubs[service]
        method_fn = getattr(stub, method, None)

        if method_fn is None:
            raise ValidationError(
                f"Method '{method}' not found on service '{service}'",
                field_name="method",
                value=method,
            )

        call_metadata = self.get_metadata()
        if metadata:
            call_metadata.extend(metadata)

        timeout_val = timeout if timeout is not None else self.timeout
        start_time = time.perf_counter()

        try:
            if requests is not None:
                responses = method_fn(
                    requests,
                    timeout=timeout_val,
                    metadata=call_metadata,
                )
            else:
                responses = method_fn(
                    timeout=timeout_val,
                    metadata=call_metadata,
                )

            for response in responses:
                duration_ms = (time.perf_counter() - start_time) * 1000

                grpc_response = gRPCResponse(
                    data=response,
                    status_code=0,
                    duration_ms=duration_ms,
                )

                self._record_request(
                    operation=f"{service}/{method}/stream",
                    request_data="<streaming>",
                    response_data=str(response)[:500] if response else None,
                    duration_ms=duration_ms,
                )

                yield grpc_response
                start_time = time.perf_counter()

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_str = str(e)
            status_code = getattr(e, "code", lambda: -1)()
            if callable(status_code):
                status_code = -1
            status_details = getattr(e, "details", lambda: err_str)()
            if callable(status_details):
                status_details = err_str

            self._record_request(
                operation=f"{service}/{method}/stream",
                request_data="<streaming>",
                response_data=None,
                duration_ms=duration_ms,
                error=status_details,
                metadata={"status_code": status_code},
            )

            yield gRPCResponse(
                data=None,
                status_code=status_code,
                status_details=status_details,
                duration_ms=duration_ms,
            )

    def get_service(self, service_name: str) -> ProtoService | None:
        """Get a registered service by name.

        Args:
            service_name: Name of the service.

        Returns:
            ProtoService or None if not found.
        """
        return self._services.get(service_name)

    def list_services(self) -> list[str]:
        """List all registered service names.

        Returns:
            List of service name strings.
        """
        return list(self._services.keys())

    def list_methods(self, service_name: str) -> list[str]:
        """List all methods for a service.

        Args:
            service_name: Name of the service.

        Returns:
            List of method name strings.
        """
        service = self._services.get(service_name)
        if service:
            return list(service.methods.keys())
        return []


gRPCClient = GrpcClient  # noqa: N816


class AsyncgRPCClient(BaseAsyncClient[gRPCResponse]):
    """Asynchronous gRPC client with service method invocation support.

    Provides the same functionality as GrpcClient but with async/await
    support for non-blocking operations.

    Example:
        >>> from venomqa.clients.grpc import AsyncgRPCClient
        >>> client = AsyncgRPCClient("localhost:50051")
        >>> await client.connect()
        >>> proto = client.load_proto("generated/service_pb2.py")
        >>> client.register_service("MyService", proto.MyServiceStub)
        >>> response = await client.call("MyService", "GetData", request)

    Attributes:
        proto_dir: Directory containing proto files.
        default_metadata: Default gRPC metadata for all calls.
        use_tls: Whether to use TLS encryption.
    """

    def __init__(
        self,
        endpoint: str,
        proto_dir: str | Path | None = None,
        timeout: float = 30.0,
        default_metadata: list[tuple[str, str]] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        use_tls: bool = False,
        root_certificates: bytes | str | Path | None = None,
        private_key: bytes | str | Path | None = None,
        certificate_chain: bytes | str | Path | None = None,
    ) -> None:
        """Initialize the async gRPC client.

        Args:
            endpoint: Server endpoint in host:port format.
            proto_dir: Directory containing compiled proto files (optional).
            timeout: Default RPC timeout in seconds (default: 30.0).
            default_metadata: Default metadata for all RPCs (optional).
            retry_count: Maximum retry attempts (default: 3).
            retry_delay: Base retry delay in seconds (default: 1.0).
            use_tls: Enable TLS encryption (default: False).
            root_certificates: Root CA certificates (optional).
            private_key: Client private key for mTLS (optional).
            certificate_chain: Client certificate chain for mTLS (optional).

        Raises:
            ValidationError: If parameters are invalid.
        """
        validated_endpoint = _validate_grpc_endpoint(endpoint)
        super().__init__(validated_endpoint, timeout, {}, retry_count, retry_delay)

        self.proto_dir = Path(proto_dir) if proto_dir else None
        self.default_metadata = default_metadata or []
        self.use_tls = use_tls
        self.root_certificates = self._load_cert(root_certificates)
        self.private_key = self._load_cert(private_key)
        self.certificate_chain = self._load_cert(certificate_chain)
        self._channel: grpc.aio.Channel | None = None
        self._stubs: dict[str, Any] = {}
        self._services: dict[str, ProtoService] = {}
        self._loaded_modules: dict[str, Any] = {}

    def _load_cert(self, cert: bytes | str | Path | None) -> bytes | None:
        """Load certificate from bytes, file path, or return as-is."""
        if cert is None:
            return None
        if isinstance(cert, bytes):
            return cert
        if isinstance(cert, (str, Path)):
            path = Path(cert)
            if path.exists():
                return path.read_bytes()
            logger.warning(f"Certificate file not found: {path}")
        return None

    async def connect(self) -> None:
        """Establish async gRPC channel connection.

        Raises:
            ConnectionError: If connection fails.
        """
        import grpc

        if self._channel is not None:
            return

        try:
            if self.use_tls:
                credentials = self._create_credentials()
                self._channel = grpc.aio.secure_channel(self.endpoint, credentials)
            else:
                self._channel = grpc.aio.insecure_channel(self.endpoint)

            self._connected = True
            logger.info(f"Async gRPC client connected to {self.endpoint}")

        except Exception as e:
            raise ConnectionError(
                message=f"Failed to connect to gRPC server at {self.endpoint}: {e}"
            ) from e

    def _create_credentials(self) -> grpc.ChannelCredentials:
        """Create TLS channel credentials."""
        import grpc

        return grpc.ssl_channel_credentials(
            root_certificates=self.root_certificates,
            private_key=self.private_key,
            certificate_chain=self.certificate_chain,
        )

    async def disconnect(self) -> None:
        """Close async gRPC channel connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
        self._stubs.clear()
        self._services.clear()
        self._connected = False
        logger.info("Async gRPC client disconnected")

    async def is_connected(self) -> bool:
        """Check if async client is connected.

        Returns:
            True if channel is established.
        """
        return self._connected and self._channel is not None

    def load_proto(
        self,
        proto_file: str | Path,
        module_name: str | None = None,
    ) -> Any:
        """Load a compiled proto module dynamically.

        Args:
            proto_file: Path to the compiled _pb2.py file.
            module_name: Name for the module (default: proto file stem).

        Returns:
            The loaded proto module.

        Raises:
            FileNotFoundError: If proto file doesn't exist.
            ImportError: If module cannot be loaded.
        """
        if not proto_file:
            raise ValidationError(
                "Proto file path cannot be empty",
                field_name="proto_file",
                value=proto_file,
            )

        proto_path = Path(proto_file)
        if not proto_path.exists():
            raise FileNotFoundError(f"Proto file not found: {proto_path}")

        module = module_name or proto_path.stem
        if module in self._loaded_modules:
            return self._loaded_modules[module]

        spec = importlib.util.spec_from_file_location(module, proto_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {proto_path}")

        loaded_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded_module)
        self._loaded_modules[module] = loaded_module

        return loaded_module

    def register_service(
        self,
        service_name: str,
        stub_class: Any,
        package: str = "",
    ) -> ProtoService:
        """Register a gRPC service with its stub class.

        Args:
            service_name: Name to identify the service.
            stub_class: The generated stub class from proto compilation.
            package: Protocol package name (optional).

        Returns:
            ProtoService instance for the registered service.

        Raises:
            ValidationError: If service_name is empty.
            ConnectionError: If not connected.
        """
        if not service_name:
            raise ValidationError(
                "Service name cannot be empty",
                field_name="service_name",
                value=service_name,
            )

        if not self._connected or self._channel is None:
            raise ConnectionError(message="Client not connected. Call connect() first.")

        stub = stub_class(self._channel)
        self._stubs[service_name] = stub

        service = ProtoService(name=service_name, package=package)
        self._services[service_name] = service

        for name in dir(stub):
            if not name.startswith("_"):
                method_info = getattr(stub, name, None)
                if callable(method_info):
                    service.methods[name] = ProtoMethod(
                        name=name,
                        service_name=service_name,
                        package=package,
                        input_type="",
                        output_type="",
                    )

        logger.info(f"Registered async gRPC service: {service_name}")
        return service

    def get_metadata(self) -> list[tuple[str, str]]:
        """Get metadata including auth tokens.

        Note: For async clients, this uses the base credentials directly.
        For async token refresh, use get_metadata_async instead.
        """
        metadata = list(self.default_metadata)
        if self._credentials:
            token = self._credentials.authorization_header
            metadata.append(("authorization", token))
        return metadata

    async def get_metadata_async(self) -> list[tuple[str, str]]:
        """Get metadata including auth tokens (async version).

        Uses async token refresh if configured.
        """
        metadata = list(self.default_metadata)
        auth_header = await self.get_auth_header()
        if auth_header:
            token = auth_header.get("Authorization", "")
            if token.startswith("Bearer "):
                metadata.append(("authorization", token))
        return metadata

    async def call(
        self,
        service: str,
        method: str,
        request: Any,
        timeout: float | None = None,
        metadata: list[tuple[str, str]] | None = None,
    ) -> gRPCResponse:
        """Call a unary gRPC method asynchronously.

        Args:
            service: Registered service name.
            method: Method name on the service.
            request: Request message object.
            timeout: RPC timeout in seconds (optional).
            metadata: Additional metadata for this call (optional).

        Returns:
            gRPCResponse with result or error.
        """
        if not self._connected:
            await self.connect()

        if not service:
            raise ValidationError(
                "Service name cannot be empty",
                field_name="service",
                value=service,
            )
        if not method:
            raise ValidationError(
                "Method name cannot be empty",
                field_name="method",
                value=method,
            )

        if service not in self._stubs:
            raise ValidationError(
                f"Service '{service}' not registered. Available: {list(self._stubs.keys())}",
                field_name="service",
                value=service,
            )

        stub = self._stubs[service]
        method_fn = getattr(stub, method, None)

        if method_fn is None:
            raise ValidationError(
                f"Method '{method}' not found on service '{service}'",
                field_name="method",
                value=method,
            )

        call_metadata = self.get_metadata()
        if metadata:
            call_metadata.extend(metadata)

        timeout_val = timeout if timeout is not None else self.timeout
        start_time = time.perf_counter()

        try:
            response = await method_fn(
                request,
                timeout=timeout_val,
                metadata=call_metadata,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000

            grpc_response = gRPCResponse(
                data=response,
                status_code=0,
                duration_ms=duration_ms,
            )

            self._record_request(
                operation=f"{service}/{method}",
                request_data=str(request)[:500] if request else None,
                response_data=str(response)[:500] if response else None,
                duration_ms=duration_ms,
            )

            return grpc_response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_str = str(e)
            status_code = getattr(e, "code", lambda: -1)()
            if callable(status_code):
                status_code = -1
            status_details = getattr(e, "details", lambda: err_str)()
            if callable(status_details):
                status_details = err_str

            self._record_request(
                operation=f"{service}/{method}",
                request_data=str(request)[:500] if request else None,
                response_data=None,
                duration_ms=duration_ms,
                error=status_details,
                metadata={"status_code": status_code},
            )

            if "timeout" in err_str.lower() or status_code == 4:
                raise RequestTimeoutError(
                    message=f"gRPC call to {service}/{method} timed out after {timeout_val}s"
                ) from e

            return gRPCResponse(
                data=None,
                status_code=status_code,
                status_details=status_details,
                duration_ms=duration_ms,
            )

    async def stream(
        self,
        service: str,
        method: str,
        requests: Any | None = None,
        timeout: float | None = None,
        metadata: list[tuple[str, str]] | None = None,
    ) -> AsyncGenerator[gRPCResponse, None]:
        """Call a streaming gRPC method asynchronously.

        Args:
            service: Registered service name.
            method: Method name on the service.
            requests: Iterator/async iterator of request messages (optional).
            timeout: RPC timeout in seconds (optional).
            metadata: Additional metadata for this call (optional).

        Yields:
            gRPCResponse for each response in the stream.
        """
        if not self._connected:
            await self.connect()

        if not service:
            raise ValidationError(
                "Service name cannot be empty",
                field_name="service",
                value=service,
            )

        if service not in self._stubs:
            raise ValidationError(
                f"Service '{service}' not registered",
                field_name="service",
                value=service,
            )

        stub = self._stubs[service]
        method_fn = getattr(stub, method, None)

        if method_fn is None:
            raise ValidationError(
                f"Method '{method}' not found on service '{service}'",
                field_name="method",
                value=method,
            )

        call_metadata = self.get_metadata()
        if metadata:
            call_metadata.extend(metadata)

        timeout_val = timeout if timeout is not None else self.timeout
        start_time = time.perf_counter()

        try:
            if requests is not None:
                responses = method_fn(
                    requests,
                    timeout=timeout_val,
                    metadata=call_metadata,
                )
            else:
                responses = method_fn(
                    timeout=timeout_val,
                    metadata=call_metadata,
                )

            async for response in responses:
                duration_ms = (time.perf_counter() - start_time) * 1000

                grpc_response = gRPCResponse(
                    data=response,
                    status_code=0,
                    duration_ms=duration_ms,
                )

                self._record_request(
                    operation=f"{service}/{method}/stream",
                    request_data="<streaming>",
                    response_data=str(response)[:500] if response else None,
                    duration_ms=duration_ms,
                )

                yield grpc_response
                start_time = time.perf_counter()

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_str = str(e)
            status_code = getattr(e, "code", lambda: -1)()
            if callable(status_code):
                status_code = -1
            status_details = getattr(e, "details", lambda: err_str)()
            if callable(status_details):
                status_details = err_str

            self._record_request(
                operation=f"{service}/{method}/stream",
                request_data="<streaming>",
                response_data=None,
                duration_ms=duration_ms,
                error=status_details,
                metadata={"status_code": status_code},
            )

            yield gRPCResponse(
                data=None,
                status_code=status_code,
                status_details=status_details,
                duration_ms=duration_ms,
            )

    def get_service(self, service_name: str) -> ProtoService | None:
        """Get a registered service by name."""
        return self._services.get(service_name)

    def list_services(self) -> list[str]:
        """List all registered service names."""
        return list(self._services.keys())

    def list_methods(self, service_name: str) -> list[str]:
        """List all methods for a service."""
        service = self._services.get(service_name)
        if service:
            return list(service.methods.keys())
        return []
