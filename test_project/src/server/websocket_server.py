import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from src.server.chat_session import ChatSession

app = FastAPI(title="Orchestrator Chat Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions = {}

# ✅ Read from environment
USE_RABBITMQ = os.getenv("USE_RABBITMQ", "true").lower() == "true"

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin", "*")
    print(f"🔌 WebSocket connection from origin: {origin}")
    
    await websocket.accept()
    
    session = ChatSession(
        websocket, 
        llm_provider="openai",
        use_rabbitmq=USE_RABBITMQ  # ✅ Pass flag
    )
    session_id = id(websocket)
    sessions[session_id] = session

    try:
        mode = "RabbitMQ Worker Mode" if USE_RABBITMQ else "Direct Mode"
        await websocket.send_json({
            "type": "system",
            "message": f"🟢 Connected ({mode}). Send your query as a plain string."
        })

        while True:
            user_text = await websocket.receive_text()
            user_text = user_text.strip()
            if not user_text:
                continue

            if user_text.lower() == "exit":
                await websocket.send_json({"type": "system", "message": "👋 Session ended."})
                break

            try:
                await session.handle_user_message(user_text)
            except Exception as e:
                import traceback
                print(f"❌ Error handling message: {e}")
                traceback.print_exc()
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        print(f"🔌 Client disconnected: {session_id}")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        await session.cleanup()
        sessions.pop(session_id, None)
        print(f"🗑️ Session {session_id} cleaned up")


@app.get("/health")
async def health_check():
    mode = "rabbitmq" if USE_RABBITMQ else "direct"
    return {
        "status": "ok", 
        "sessions": len(sessions),
        "mode": mode
    }