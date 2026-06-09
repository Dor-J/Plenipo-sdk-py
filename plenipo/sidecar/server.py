"""Sidecar process lifecycle and uvicorn entrypoint."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys

import uvicorn
from starlette.applications import Starlette

from plenipo.identity.route import declare_route
from plenipo.route_defaults import default_route_service_fields
from plenipo.runtime import PlenipoAgentRuntime
from plenipo.sidecar.api import SidecarApp
from plenipo.sidecar.config import SidecarConfig, remote_bind_warning, validate_bind_host
from plenipo.sidecar.events import EventBuffer, consume_runtime_events

logger = logging.getLogger(__name__)


class _SidecarRuntimeHolder:
    """Mutable holder for runtime state shared with the ASGI app."""

    runtime: PlenipoAgentRuntime | None = None
    event_buffer: EventBuffer | None = None
    consumer_task: asyncio.Task[None] | None = None


_holder = _SidecarRuntimeHolder()


def create_sidecar_app() -> Starlette:
    """Creates the Starlette app using the initialized runtime holder."""
    if _holder.runtime is None or _holder.event_buffer is None:
        raise RuntimeError('Sidecar runtime is not initialized')
    return SidecarApp(_holder.runtime, _holder.event_buffer).create_app()


async def _startup_sidecar(config: SidecarConfig) -> None:
    """Initializes runtime, declares route metadata, and starts event consumption."""
    runtime = PlenipoAgentRuntime()
    await runtime.ensure_ready()

    defaults = default_route_service_fields()
    capabilities = list(dict.fromkeys(['general', config.capability]))

    updated = await declare_route(
        protocols=[config.protocol],
        capabilities=capabilities,
        payment=defaults['payment'],
        limits=defaults['limits'],
    )
    runtime._identity = updated
    runtime._route_declared = True

    event_buffer = EventBuffer(max_size=config.event_buffer_size)
    consumer_task = asyncio.create_task(consume_runtime_events(runtime.events(), event_buffer))

    _holder.runtime = runtime
    _holder.event_buffer = event_buffer
    _holder.consumer_task = consumer_task


async def _shutdown_sidecar() -> None:
    """Stops event consumption and closes the runtime."""
    if _holder.consumer_task is not None:
        _holder.consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _holder.consumer_task
        _holder.consumer_task = None

    if _holder.runtime is not None:
        await _holder.runtime.close()
        _holder.runtime = None

    _holder.event_buffer = None


async def run_sidecar_async(config: SidecarConfig) -> None:
    """Runs the sidecar until interrupted."""
    validate_bind_host(config.host, allow_remote_bind=config.allow_remote_bind)
    if not _is_loopback(config.host):
        print(remote_bind_warning(config.host), file=sys.stderr)

    await _startup_sidecar(config)
    app = create_sidecar_app()

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=config.host,
            port=config.port,
            log_level='info',
            access_log=True,
        )
    )
    try:
        await server.serve()
    finally:
        await _shutdown_sidecar()


def _is_loopback(host: str) -> bool:
    return host.strip().lower() in {'127.0.0.1', 'localhost', '::1'}


def run_sidecar(config: SidecarConfig) -> None:
    """Blocking entrypoint for the sidecar CLI."""
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_sidecar_async(config))
    except KeyboardInterrupt:
        return


def reset_sidecar_holder_for_tests() -> None:
    """Clears module-level holder state for unit tests."""
    _holder.runtime = None
    _holder.event_buffer = None
    _holder.consumer_task = None
