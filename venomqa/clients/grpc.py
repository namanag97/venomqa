"""gRPC client for VenomQA with service method invocation support."""

from __future__ import annotations

import importlib.util
import logging
import time
from collections.abc import Generator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from venomqa.clients.base import BaseAsyncClient, BaseClient
from venomqa.errors import ConnectionError, RequestFailedError, RequestTimeoutError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import grpc

logger = logging.getLogger(__name__)


@dataclass
class GrpcResponse:
    """Represents a gRPC response."""

    data: Any
    status_code: int = 0
    status_details: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def successful(self) -> bool:
        return self.status_code == 0

    def raise_for_status(self) -> None:
        """Raise exception if response has error status."""
        if self.status_code != 0:
            raise RequestFailedError(
                message=f"gRPC error {self.status_code}: {self.status_details}",
                status_code=self.status_code,
            )


gRPCResponse = GrpcResponse  # noqa: N816


@dataclass
class ProtoMethod:
    """Represents a gRPC method."""

    name: str
    service_name: str
    package: str
    input_type: str
    output_type: str
    client_streaming: bool = False
    server_streaming: bool = False


@dataclass
class ProtoService:
    """Represents a gRPC service."""

    name: str
    package: str
    methods: dict[str, ProtoMethod] = field(default_factory=dict)


class GrpcClient(BaseClient[GrpcResponse]):
    """gRPC client with service method invocation support."""

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
        super().__init__(endpoint, timeout, {}, retry_count, retry_delay)
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
        """Load certificate from bytes, file path, or return as-is."""
        if cert is None:
            return None
        if isinstance(cert, bytes):
            return cert
        if isinstance(cert, (str, Path)):
            path = Path(cert)
            if path.exists():
                return path.read_bytes()
        return None

    def connect(self) -> None:
        """Establish gRPC channel connection."""
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
            raise ConnectionError(message=f"Failed to connect to gRPC server: {e}") from e

    def _create_credentials(self) -> grpc.ChannelCredentials:
        """Create TLS credentials."""
        import grpc

        return grpc.ssl_channel_credentials(
            root_certificates=self.root_certificates,
            private_key=self.private_key,
            certificate_chain=self.certificate_chain,
        )

    def disconnect(self) -> None:
        """Close gRPC channel connection."""
        if self._channel:
            self._channel.close()
            self._channel = None
        self._stubs.clear()
        self._connected = False
        logger.info("gRPC client disconnected")

    def is_connected(self) -> bool:
        return self._connected and self._channel is not None

    def load_proto(
        self,
        proto_file: str | Path,
        module_name: str | None = None,
    ) -> Any:
        """Load a compiled proto module.

        Args:
            proto_file: Path to the compiled _pb2.py file.
            module_name: Name for the module. Defaults to proto file stem.
        """
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
        """Register a gRPC service with its stub class."""
        if not self._connected:
            self.connect()

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
        """Get metadata including auth tokens."""
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
        """Call a unary gRPC method."""
        self._ensure_connected()

        if service not in self._stubs:
            raise ValueError(f"Service '{service}' not registered")

        stub = self._stubs[service]
        method_fn = getattr(stub, method, None)

        if method_fn is None:
            raise ValueError(f"Method '{method}' not found on service '{service}'")

        call_metadata = self.get_metadata()
        if metadata:
            call_metadata.extend(metadata)

        timeout_val = timeout or self.timeout
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
                request_data=str(request),
                response_data=str(response),
                duration_ms=duration_ms,
            )

            return grpc_response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_str = str(e)
            status_code = getattr(e, "code", lambda: -1)()
            status_details = getattr(e, "details", lambda: err_str)()

            self._record_request(
                operation=f"{service}/{method}",
                request_data=str(request),
                response_data=None,
                duration_ms=duration_ms,
                error=status_details,
                metadata={"status_code": status_code},
            )

            if "timeout" in err_str.lower():
                raise RequestTimeoutError(message=f"gRPC call timed out: {e}") from e

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
        """
        self._ensure_connected()

        if service not in self._stubs:
            raise ValueError(f"Service '{service}' not registered")

        stub = self._stubs[service]
        method_fn = getattr(stub, method, None)

        if method_fn is None:
            raise ValueError(f"Method '{method}' not found on service '{service}'")

        call_metadata = self.get_metadata()
        if metadata:
            call_metadata.extend(metadata)

        timeout_val = timeout or self.timeout
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
                    response_data=str(response)[:500],
                    duration_ms=duration_ms,
                )

                yield grpc_response
                start_time = time.perf_counter()

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_str = str(e)
            status_code = getattr(e, "code", lambda: -1)()
            status_details = getattr(e, "details", lambda: err_str)()

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


gRPCClient = GrpcClient  # noqa: N816


class AsyncgRPCClient(BaseAsyncClient[gRPCResponse]):
    """Async gRPC client with service method invocation support."""

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
        super().__init__(endpoint, timeout, {}, retry_count, retry_delay)
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
        return None

    async def connect(self) -> None:
        """Establish async gRPC channel connection."""
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
            raise ConnectionError(message=f"Failed to connect to gRPC server: {e}") from e

    def _create_credentials(self) -> grpc.ChannelCredentials:
        """Create TLS credentials."""
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
        self._connected = False
        logger.info("Async gRPC client disconnected")

    async def is_connected(self) -> bool:
        return self._connected and self._channel is not None

    def load_proto(
        self,
        proto_file: str | Path,
        module_name: str | None = None,
    ) -> Any:
        """Load a compiled proto module."""
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
        """Register a gRPC service with its stub class."""
        if not self._connected or self._channel is None:
            raise ConnectionError(message="Client not connected")

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
        """Get metadata including auth tokens."""
        metadata = list(self.default_metadata)
        auth_header = self.get_auth_header()
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
        """Call a unary gRPC method asynchronously."""
        if not self._connected:
            await self.connect()

        if service not in self._stubs:
            raise ValueError(f"Service '{service}' not registered")

        stub = self._stubs[service]
        method_fn = getattr(stub, method, None)

        if method_fn is None:
            raise ValueError(f"Method '{method}' not found on service '{service}'")

        call_metadata = self.get_metadata()
        if metadata:
            call_metadata.extend(metadata)

        timeout_val = timeout or self.timeout
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
                request_data=str(request),
                response_data=str(response),
                duration_ms=duration_ms,
            )

            return grpc_response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_str = str(e)
            status_code = getattr(e, "code", lambda: -1)()
            status_details = getattr(e, "details", lambda: err_str)()

            self._record_request(
                operation=f"{service}/{method}",
                request_data=str(request),
                response_data=None,
                duration_ms=duration_ms,
                error=status_details,
                metadata={"status_code": status_code},
            )

            if "timeout" in err_str.lower():
                raise RequestTimeoutError(message=f"gRPC call timed out: {e}") from e

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
        """Call a streaming gRPC method asynchronously."""
        if not self._connected:
            await self.connect()

        if service not in self._stubs:
            raise ValueError(f"Service '{service}' not registered")

        stub = self._stubs[service]
        method_fn = getattr(stub, method, None)

        if method_fn is None:
            raise ValueError(f"Method '{method}' not found on service '{service}'")

        call_metadata = self.get_metadata()
        if metadata:
            call_metadata.extend(metadata)

        timeout_val = timeout or self.timeout
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
                    response_data=str(response)[:500],
                    duration_ms=duration_ms,
                )

                yield grpc_response
                start_time = time.perf_counter()

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_str = str(e)
            status_code = getattr(e, "code", lambda: -1)()
            status_details = getattr(e, "details", lambda: err_str)()

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
