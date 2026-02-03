import asyncio, json, uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import pymunk
from pathlib import Path
from fastapi.responses import HTMLResponse

app = FastAPI()

# simulation
space = pymunk.Space()
space.gravity = (0, 900)  # tweak

# simple floor
floor = pymunk.Segment(space.static_body, (0, 500), (10000, 500), 0)
floor.friction = 1.0
space.add(floor)

# bodies store: id -> body, shape
bodies = {}

def spawn_circle(x, y, radius=20, mass=1):
    body = pymunk.Body(mass, pymunk.moment_for_circle(mass, 0, radius))
    body.position = x, y
    shape = pymunk.Circle(body, radius)
    shape.friction = 0.6
    space.add(body, shape)
    oid = str(uuid.uuid4())
    bodies[oid] = (body, shape)
    return oid

# start with one ball
spawn_circle(500, 50)

# websocket clients
clients = set()

async def broadcast_state():
    state = []
    for oid, (body, _) in bodies.items():
        state.append({
            "id": oid,
            "x": body.position.x,
            "y": body.position.y,
            "angle": body.angle,
            "vx": body.velocity.x,
            "vy": body.velocity.y
        })
    text = json.dumps({"type": "state", "state": state})
    dead = []
    for ws in clients:
        try:
            await ws.send_text(text)
        except:
            dead.append(ws)
    for d in dead:
        clients.discard(d)

async def sim_loop():
    dt = 1/30
    while True:
        space.step(dt)
        await broadcast_state()
        await asyncio.sleep(dt)

@app.on_event("startup")
async def startup():
    asyncio.create_task(sim_loop())

@app.get("/")
async def serve_index():
    return HTMLResponse((Path(__file__).parent / "index.html").read_text())

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            # handle simple actions: spawn or push
            if data.get("type") == "spawn":
                x = data.get("x", 100)
                y = data.get("y", 100)
                spawn_circle(x, y)
            elif data.get("type") == "force":
                oid = data.get("id")
                fx = data.get("fx", 0)
                fy = data.get("fy", 0)
                if oid in bodies:
                    body, _ = bodies[oid]
                    body.apply_impulse_at_local_point((fx, fy))
    except WebSocketDisconnect:
        clients.discard(websocket)

