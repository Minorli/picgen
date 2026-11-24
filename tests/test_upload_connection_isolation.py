from __future__ import annotations

import asyncio
import json
from contextlib import suppress

import pytest

from picgen.errors import APIError
from picgen.upstream.client import HttpxAsyncClient


@pytest.mark.asyncio
@pytest.mark.parametrize("upload_status", [404, 200])
async def test_file_upload_does_not_reuse_its_connection_for_responses(upload_status, monkeypatch):
    # Exercise the real HTTP connection pool, with no proxy or paid upstream.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    requests = []
    handler_errors = []
    connections = 0
    handlers = set()

    async def handle_connection(reader, writer):
        nonlocal connections
        connections += 1
        connection_id = connections
        rejected_upload = False

        async def reply(status, body):
            encoded = body.encode("utf-8")
            writer.write(
                f"HTTP/1.1 {status} Response\r\n"
                f"Content-Length: {len(encoded)}\r\n"
                "Content-Type: application/json\r\n"
                "Connection: keep-alive\r\n\r\n".encode("ascii") + encoded
            )
            await writer.drain()

        try:
            while True:
                head = await reader.readuntil(b"\r\n\r\n")
                lines = head.decode("ascii").split("\r\n")
                method, path, _version = lines[0].split(" ")
                headers = dict(line.lower().split(": ", 1) for line in lines[1:] if line)
                requests.append((connection_id, method, path, headers))
                body_size = int(headers.get("content-length", 0))
                if path == "/v1/files":
                    if upload_status == 404:
                        # Simulate a gateway that responds before consuming the
                        # upload and leaves this connection unsuitable for reuse.
                        rejected_upload = True
                        await reply(404, '{"error":{"message":"Files unavailable"}}')
                        await reader.readexactly(body_size)
                    else:
                        await reader.readexactly(body_size)
                        await reply(200, '{"id":"file-test"}')
                elif path == "/v1/responses":
                    await reader.readexactly(body_size)
                    if rejected_upload:
                        await reply(400, "Bad Request")
                    else:
                        await reply(200, json.dumps({"id": "resp-test", "status": "completed", "output": []}))
                else:
                    raise AssertionError(f"Unexpected local request path: {path}")
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        except Exception as exc:
            handler_errors.append(exc)
        finally:
            writer.close()
            with suppress(ConnectionError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), timeout=1)

    def connected(reader, writer):
        task = asyncio.create_task(handle_connection(reader, writer))
        handlers.add(task)
        task.add_done_callback(handlers.discard)

    server = await asyncio.start_server(connected, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = HttpxAsyncClient(total_timeout=2, connect_timeout=1, max_retries=0)
    try:
        async with asyncio.timeout(5):
            upload = client.run_file_upload(
                f"http://127.0.0.1:{port}/v1/files",
                "test-local-key",
                {"filename": "source.jpg", "content_type": "image/jpeg", "data": b"test-upload"},
                "PicGen-Test",
            )
            if upload_status == 404:
                with pytest.raises(APIError) as info:
                    await upload
                assert info.value.status == 404
            else:
                assert (await upload)["id"] == "file-test"
            result = await client.run_responses(
                f"http://127.0.0.1:{port}/v1/responses",
                "test-local-key",
                {"model": "test-model", "input": "test"},
                "PicGen-Test",
            )
            assert result["id"] == "resp-test"
            assert len(requests) == 2
            assert requests[0][0] != requests[1][0]
            assert requests[0][3].get("connection") == "close"
            assert requests[1][3].get("connection") != "close"
    finally:
        await client.aclose()
        server.close()
        await server.wait_closed()
        pending = list(handlers)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    assert not handler_errors
