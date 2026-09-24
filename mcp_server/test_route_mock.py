import asyncio
import httpx2 as httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

async def proxy_forward(request: Request) -> Response:
    print(f"Intercepted: {request.url.path}")
    return Response(content=b"ok", status_code=200)

proxy_app = Starlette(routes=[
    Route("/{path:path}", proxy_forward, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
])

async def main():
    config = uvicorn.Config(app=proxy_app, host="127.0.0.1", port=9998, log_level="critical")
    proxy_server = uvicorn.Server(config)
    proxy_task = asyncio.create_task(proxy_server.serve())
    await asyncio.sleep(0.5)

    async with httpx.AsyncClient() as client:
        await client.get("http://127.0.0.1:9998/api/v1/actors/me")
    
    proxy_task.cancel()

asyncio.run(main())
