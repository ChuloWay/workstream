import asyncio
import httpx2 as httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

proxy_in_flight = 0
proxy_max_in_flight = 0
proxy_barrier = asyncio.Barrier(2)

async def proxy_forward(request: Request) -> Response:
    global proxy_in_flight, proxy_max_in_flight
    
    if request.url.path == "/api/v1/actors/me" and request.method == "GET":
        proxy_in_flight += 1
        if proxy_in_flight > proxy_max_in_flight:
            proxy_max_in_flight = proxy_in_flight
        
        try:
            await asyncio.wait_for(proxy_barrier.wait(), timeout=5.0)
        except (TimeoutError, asyncio.BrokenBarrierError):
            pass
        
        proxy_in_flight -= 1
        
    # Mocking the forward, just returning 200
    return Response(content=b"ok", status_code=200)

proxy_app = Starlette(routes=[
    Route("/{path:path}", proxy_forward, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
])

async def main():
    config = uvicorn.Config(app=proxy_app, host="127.0.0.1", port=9999, log_level="critical")
    proxy_server = uvicorn.Server(config)
    proxy_task = asyncio.create_task(proxy_server.serve())
    await asyncio.sleep(0.5)

    async def hit():
        async with httpx.AsyncClient() as client:
            await client.get("http://127.0.0.1:9999/api/v1/actors/me")

    tasks = [asyncio.create_task(hit()) for _ in range(2)]
    await asyncio.gather(*tasks)
    
    assert proxy_max_in_flight == 2
    proxy_task.cancel()
    print("Proxy test passed successfully!")

asyncio.run(main())
