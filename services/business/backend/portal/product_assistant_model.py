"""Product assistant's authorized native tool-call streaming boundary."""

import asyncio
import json
import queue
import socket
import threading
from contextlib import closing
from time import monotonic

import httpx

from django.conf import settings

from model_gateway.agent_protocol import (RESPONSE_LIMIT, _invalid_constant, _unique_object,
                                          validate_request, validate_result)
from . import model_gateway as gateway
from .security import audit


_DNS_SLOTS = threading.BoundedSemaphore(2)


async def _resolve_gateway(host, port, *, family=0, type=0, proto=0, flags=0):
    if not _DNS_SLOTS.acquire(blocking=False):
        raise gateway.GatewayError("busy", status=503)
    result = queue.Queue(maxsize=1)
    def lookup():
        try:
            result.put((True, socket.getaddrinfo(host, port, family, type, proto, flags)))
        except Exception as error:
            result.put((False, error))
        finally:
            _DNS_SLOTS.release()
    # ponytail: OS DNS cannot be killed; cap late resolvers at 2 and return busy
    # when full. Use an async resolver if stalled DNS becomes an operational issue.
    worker = threading.Thread(target=lookup, daemon=True, name="assistant-gateway-dns")
    try:
        worker.start()
    except Exception:
        _DNS_SLOTS.release()
        raise gateway.GatewayError("gateway_unavailable", status=503) from None
    while True:
        try:
            success, value = result.get_nowait()
            if success:
                return value
            raise value
        except queue.Empty:
            await asyncio.sleep(.05)


class ModelStreamCancelled(Exception):
    code = "cancelled"


def _check_cancelled(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise ModelStreamCancelled("模型流已取消。")


async def _cancellable(awaitable, cancelled, deadline):
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            _check_cancelled(cancelled)
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise gateway.GatewayError("timeout", status=504)
            await asyncio.wait((task,), timeout=min(0.05, remaining))
        return task.result()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class _StreamReader:
    def __init__(self, response, run):
        self.run = run
        self.chunks = response.aiter_raw().__aiter__()
        self.buffer = bytearray()
        self.eof = False

    async def _read(self, limit, line):
        while not self.eof and len(self.buffer) < limit and (not line or b"\n" not in self.buffer):
            chunk = await anext(self.chunks, None)
            if chunk is None:
                self.eof = True
            else:
                if len(chunk) > 65536:
                    raise gateway.GatewayError("response_too_large")
                self.buffer.extend(chunk)
        end = min(limit, len(self.buffer))
        if line:
            newline = self.buffer.find(b"\n", 0, end)
            if newline >= 0:
                end = newline + 1
        result = bytes(self.buffer[:end])
        del self.buffer[:end]
        return result

    def readline(self, limit):
        return self.run(self._read(limit, True))

    def read(self, limit):
        return self.run(self._read(limit, False))


def _agent_events(response, deadline, names, cancelled=None):
    total = 0
    terminal = None
    # ponytail: bounded 1 MiB accumulation; use fragments if output limits grow.
    content = ""
    while True:
        _check_cancelled(cancelled)
        if monotonic() >= deadline:
            raise gateway.GatewayError("timeout", status=504)
        line = response.readline(RESPONSE_LIMIT + 65537)
        _check_cancelled(cancelled)
        if not line:
            break
        total += len(line)
        # The terminal repeats the text so consumers can validate the full turn.
        if total > RESPONSE_LIMIT * 3 or len(line) > RESPONSE_LIMIT + 65536:
            raise gateway.GatewayError("response_too_large")
        if terminal is not None or not line.endswith(b"\n") or not line.startswith(b"data: "):
            raise gateway.GatewayError("invalid_response")
        if response.readline(3) not in (b"\n", b"\r\n"):
            raise gateway.GatewayError("invalid_response")
        total += 2
        try:
            event = json.loads(line[6:], object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
            if not isinstance(event, dict):
                raise ValueError
            if set(event) == {"delta"} and isinstance(event["delta"], str) and event["delta"]:
                content += event["delta"]
                if len(content.encode()) > RESPONSE_LIMIT or "**ERROR**" in content:
                    raise ValueError
                yield event
            elif event.get("done") is True:
                result = validate_result({key: value for key, value in event.items() if key != "done"}, names)
                if (result["content"] or "") != content:
                    raise ValueError
                terminal = event
            elif (set(event) == {"error"} and isinstance(event["error"], dict)
                  and set(event["error"]) == {"code", "detail"}
                  and isinstance(event["error"]["code"], str) and isinstance(event["error"]["detail"], str)):
                raise gateway.GatewayError(event["error"]["code"])
            else:
                raise ValueError
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise gateway.GatewayError("invalid_response") from None
    if monotonic() >= deadline:
        raise gateway.GatewayError("timeout", status=504)
    if terminal is None:
        raise gateway.GatewayError("invalid_response")
    yield terminal


def _request_agent_stream(payload, *, cancelled=None):
    names = validate_request(payload["messages"], payload["tools"], payload.get("tool_choice"))
    request, timeout = gateway._gateway_request(payload, "/v1/generate-agent-stream")
    _check_cancelled(cancelled)
    deadline = monotonic() + timeout
    with asyncio.Runner() as runner:
        runner.get_loop().getaddrinfo = _resolve_gateway
        client = httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=timeout)
        response = None
        def run(awaitable):
            return runner.run(_cancellable(awaitable, cancelled, deadline))
        try:
            native = client.build_request(request.get_method(), request.full_url,
                                          content=request.data, headers=dict(request.header_items()))
            response = run(client.send(native, stream=True))
            reader = _StreamReader(response, run)
            if response.status_code >= 300:
                try:
                    code = json.loads(reader.read(8192)).get("code", "upstream_error")
                except (ValueError, AttributeError):
                    code = "upstream_error"
                raise gateway.GatewayError(code)
            if (response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "text/event-stream"
                    or response.headers.get("Content-Encoding", "identity").lower() != "identity"):
                raise gateway.GatewayError("invalid_response")
            yield from _agent_events(reader, deadline, names, cancelled)
        except (httpx.HTTPError, TimeoutError, OSError):
            _check_cancelled(cancelled)
            raise gateway.GatewayError("gateway_unavailable", status=503) from None
        except Exception:
            _check_cancelled(cancelled)
            raise
        finally:
            try:
                if response is not None:
                    runner.run(response.aclose())
            finally:
                runner.run(client.aclose())


def stream_agent_for_use(user, purpose_code, messages, tools, *, recheck, tool_choice=None, cancelled=None):
    if purpose_code != getattr(settings, "PRODUCT_KNOWLEDGE_MODEL_ROUTE", None):
        raise gateway.GatewayError("forbidden", status=403)
    _check_cancelled(cancelled)
    recheck()
    user, route = gateway._route_for(user, purpose_code, assistant=True)
    if route.module.code != "product":
        raise gateway.GatewayError("forbidden", status=403)
    try:
        names = validate_request(messages, tools, tool_choice)
    except (ValueError, TypeError, RecursionError):
        raise gateway.GatewayError("invalid_request", status=400) from None
    model, _, version = gateway._select_route_model(user, route)
    config = gateway._model_config(model)
    selection = {"model_id": str(model.public_id), "config_version": version}
    payload = {**config, "messages": messages, "tools": tools, "tool_choice": tool_choice, "purpose": "business"}
    record = gateway._reserve(user, model, "business", route, version)
    started = monotonic()
    callback_failed = False

    def authorize():
        nonlocal callback_failed
        _check_cancelled(cancelled)
        if purpose_code != getattr(settings, "PRODUCT_KNOWLEDGE_MODEL_ROUTE", None):
            raise gateway.GatewayError("forbidden", status=403)
        try:
            recheck()
        except Exception:
            callback_failed = True
            raise
        fresh, current = gateway._route_for(user, purpose_code, assistant=True)
        if fresh.grant_version != user.grant_version or current.module.code != "product":
            raise gateway.GatewayError("forbidden", status=403)
        current_model, _, current_version = gateway._select_route_model(fresh, current, selection)
        if (current_version != version or current_model.pk != model.pk
                or gateway._model_config(current_model) != config):
            raise gateway.GatewayError("model_configuration_changed", status=409)

    try:
        completed = False
        # ponytail: bounded 1 MiB accumulation; use fragments if output limits grow.
        content = ""
        with closing(_request_agent_stream(payload, cancelled=cancelled)) as stream:
            while True:
                authorize()
                event = next(stream, None)
                authorize()
                if event is None:
                    break
                if not isinstance(event, dict) or completed:
                    raise gateway.GatewayError("invalid_response")
                if set(event) == {"delta"} and isinstance(event["delta"], str) and event["delta"]:
                    content += event["delta"]
                    if len(content.encode()) > RESPONSE_LIMIT or "**ERROR**" in content:
                        raise gateway.GatewayError("invalid_response")
                elif event.get("done") is True:
                    try:
                        result = validate_result({key: value for key, value in event.items() if key != "done"}, names)
                        if (result["content"] or "") != content:
                            raise ValueError
                    except (ValueError, TypeError, RecursionError):
                        raise gateway.GatewayError("invalid_response") from None
                    record.prompt_tokens, record.completion_tokens = event["prompt_tokens"], event["completion_tokens"]
                    completed = True
                    record.status = "success"
                else:
                    raise gateway.GatewayError("invalid_response")
                yield event
        if not completed:
            raise gateway.GatewayError("invalid_response")
        record.status = "success"
    except gateway.GatewayError as error:
        record.status = "cancelled" if cancelled is not None and cancelled.is_set() else error.code
        _check_cancelled(cancelled)
        raise
    except ModelStreamCancelled:
        record.status = "cancelled"
        raise
    except GeneratorExit:
        record.status = "success" if completed else "cancelled"
        raise
    except Exception:
        record.status = ("cancelled" if cancelled is not None and cancelled.is_set()
                         else "forbidden" if callback_failed else "internal_error")
        _check_cancelled(cancelled)
        if callback_failed:
            raise
        raise gateway.GatewayError("internal_error") from None
    finally:
        record.duration_ms = max(0, int((monotonic() - started) * 1000))
        record.save(update_fields=["status", "duration_ms", "prompt_tokens", "completion_tokens"])
        audit(user, "model_call", record.pk, result=record.status)
