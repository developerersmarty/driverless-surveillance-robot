# websoket_server.py                                             
import asyncio
import aiohttp
from aiohttp import web
import json
import logging
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("websocket_server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Store connected clients
browser_control_clients = set()
browser_distance_clients = set()
pi_control_client = None
pi_distance_client = None

async def handle_control(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    browser_control_clients.add(ws)
    logger.info(f"Browser control client connected: {request.remote}")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    logger.info(f"Browser control message: {msg.data}")
                    data = json.loads(msg.data)
                    action = data.get("action")
                    value = data.get("value")
                    if not action:
                        logger.error(f"Missing action in control data: {data}")
                        continue
                    # Forward to Pi
                    if pi_control_client and not pi_control_client.closed:
                        await pi_control_client.send_json(data)
                        logger.info(f"Forwarded to Pi: {data}")
                    else:
                        logger.warning("No Pi control client connected")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from browser control: {msg.data}, Error: {e}")
                except Exception as e:
                    logger.error(f"Error processing browser control: {type(e).__name__}: {e}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"Browser control WebSocket error: {ws.exception()}")
    except Exception as e:
        logger.error(f"Unexpected error in browser control: {type(e).__name__}: {e}")
    finally:
        browser_control_clients.discard(ws)
        logger.info(f"Browser control client disconnected: {request.remote}")
    return ws

async def handle_distance(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    browser_distance_clients.add(ws)
    logger.info(f"Browser distance client connected: {request.remote}")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                logger.info(f"Browser distance message (unexpected): {msg.data}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"Browser distance WebSocket error: {ws.exception()}")
    except Exception as e:
        logger.error(f"Unexpected error in browser distance: {type(e).__name__}: {e}")
    finally:
        browser_distance_clients.discard(ws)
        logger.info(f"Browser distance client disconnected: {request.remote}")
    return ws

async def handle_pi_control(request):
    global pi_control_client
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    pi_control_client = ws
    logger.info(f"Pi control client connected: {request.remote}")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                logger.info(f"Pi control message (unexpected): {msg.data}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"Pi control WebSocket error: {ws.exception()}")
    except Exception as e:
        logger.error(f"Unexpected error in Pi control: {type(e).__name__}: {e}")
    finally:
        pi_control_client = None
        logger.info(f"Pi control client disconnected: {request.remote}")
    return ws

async def handle_pi_control(request):
    global pi_control_client
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    pi_control_client = ws
    logger.info(f"Pi control client connected: {request.remote}")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                logger.info(f"Pi control message (unexpected): {msg.data}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"Pi control WebSocket error: {ws.exception()}")
    except Exception as e:
        logger.error(f"Unexpected error in Pi control: {type(e).__name__}: {e}")
    finally:
        pi_control_client = None
        logger.info(f"Pi control client disconnected: {request.remote}")
    return ws

async def handle_pi_distance(request):
    global pi_distance_client
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    pi_distance_client = ws
    logger.info(f"Pi distance client connected: {request.remote}")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    logger.info(f"Pi distance message: {msg.data}")
                    data = json.loads(msg.data)
                    if data.get("type") == "distance":
                        value = data.get("value")
                        if value is None:
                            logger.error(f"Missing value in distance data: {data}")
                            continue
                        broadcast_data = {"type": "distance", "value": float(value)}
                        # Broadcast to browser distance clients
                        await asyncio.gather(
                            *[client.send_json(broadcast_data) for client in browser_distance_clients if not client.closed],
                            return_exceptions=True
                        )
                        logger.info(f"Broadcasted distance: {value}")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from Pi distance: {msg.data}, Error: {e}")
                except Exception as e:
                    logger.error(f"Error processing Pi distance: {type(e).__name__}: {e}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"Pi distance WebSocket error: {ws.exception()}")
    except Exception as e:
        logger.error(f"Unexpected error in Pi distance: {type(e).__name__}: {e}")
    finally:
        pi_distance_client = None
        logger.info(f"Pi distance client disconnected: {request.remote}")
    return ws

async def main():
    app = web.Application()
    app.add_routes([
        web.get('/control', handle_control),
        web.get('/distance', handle_distance),
        web.static('/', os.path.join(os.getcwd(), 'static'))
    ])
    logger.info("WebSocket server started on http://your_server_ip:9000")
    return app

if __name__ == "__main__":
    try:
        web.run_app(main(), host="0.0.0.0", port=9000)
    except KeyboardInterrupt:
        logger.info("Server shut down by user")
    except Exception as e:
        logger.error(f"Fatal server error: {type(e).__name__}: {e}")