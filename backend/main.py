import json
import uuid
import re
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import socketio
import asyncio

# ============ APP INITIALIZATION ============
app = FastAPI(title="FlowZint AI Customer Support", description="AI Customer Support System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Try to import redis (optional)
try:
    import redis
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    redis_client.ping()
    print("✅ Redis connected")
    REDIS_AVAILABLE = True
except:
    redis_client = None
    REDIS_AVAILABLE = False
    print("⚠️ Redis not available - using in-memory storage")

# Socket.IO for real-time handoffs
sio = socketio.AsyncServer(cors_allowed_origins='*', async_mode='asgi')
socket_app = socketio.ASGIApp(sio, app)

# ============ DATA STORAGE ============
chat_histories: Dict[str, List[dict]] = {}
handoffs: Dict[str, dict] = {}

# ============ HELPER FUNCTIONS ============
def save_to_memory(user_id: str, role: str, content: str):
    """Save conversation to memory"""
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    }
    
    if REDIS_AVAILABLE and redis_client:
        redis_client.lpush(f"chat:{user_id}", json.dumps(message))
        redis_client.expire(f"chat:{user_id}", 604800)  # 7 days
    else:
        if user_id not in chat_histories:
            chat_histories[user_id] = []
        chat_histories[user_id].append(message)
        # Keep only last 50 messages
        if len(chat_histories[user_id]) > 50:
            chat_histories[user_id] = chat_histories[user_id][-50:]

def get_recent_memory(user_id: str, limit: int = 5) -> List[dict]:
    """Get recent conversation history"""
    if REDIS_AVAILABLE and redis_client:
        items = redis_client.lrange(f"chat:{user_id}", 0, limit - 1)
        return [json.loads(item) for item in items]
    else:
        return chat_histories.get(user_id, [])[-limit:]

def extract_order_id(text: str) -> Optional[str]:
    """Extract order ID from text"""
    patterns = [
        r'ORD[-\s]?(\d{5,})',
        r'order\s*#?\s*(\d{5,})',
        r'#(\d{5,})',
        r'\b(\d{8,})\b'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return f"ORD-{match.group(1)}"
    return None

# ============ RESPONSES ============
def get_tracking_response(order_id: str) -> str:
    return f"✅ Order {order_id} is out for delivery and will arrive today by 6:00 PM. You can track it at: https://flowzint.com/track/{order_id}"

def get_refund_response(order_id: str) -> str:
    refund_id = str(uuid.uuid4())[:8].upper()
    return f"✅ Refund of $49.99 has been processed for order {order_id}. Refund ID: REF-{refund_id}. Amount will reflect in 3-5 business days."

def get_cancel_response(order_id: str) -> str:
    return f"✅ Order {order_id} has been cancelled successfully. No charges will be made."

def get_escalation_response(handoff_id: str) -> str:
    return f"👨‍💼 I understand you need human assistance. I'm transferring you to a live agent. Your ticket ID is {handoff_id}. Please hold for a moment."

def get_greeting_response(user_id: str) -> str:
    history = get_recent_memory(user_id, 2)
    if history:
        return "👋 Welcome back! How can I help you today? I can assist with order tracking, refunds, cancellations, or answer product questions."
    else:
        return "👋 Hello! I'm your AI customer support assistant. I can help you with:\n• Track your order\n• Process refunds\n• Cancel orders\n• Answer questions\n\nHow may I assist you today?"

def get_fallback_response() -> str:
    return "I'm here to help! You can ask me to:\n• 'Track my order ORD-12345'\n• 'Refund order ORD-12345'\n• 'Cancel order ORD-12345'\n• 'I need a human'\n\nWhat would you like to do?"

# ============ TRIAGE AGENT ============
def should_escalate(user_input: str) -> tuple[bool, str]:
    """Check if request should go to human"""
    sensitive_keywords = [
        "refund", "complaint", "lawyer", "lawsuit", "manager", 
        "supervisor", "escalate", "billing dispute", "chargeback",
        "fraud", "unauthorized", "damaged", "broken"
    ]
    
    urgent_keywords = ["urgent", "emergency", "asap", "immediately"]
    
    for keyword in sensitive_keywords:
        if keyword in user_input.lower():
            return True, f"Detected: {keyword}"
    
    for keyword in urgent_keywords:
        if keyword in user_input.lower():
            return True, f"Urgent: {keyword}"
    
    return False, ""

def create_handoff(user_id: str, user_input: str, reason: str) -> dict:
    """Create a handoff ticket"""
    handoff_id = str(uuid.uuid4())[:8]
    handoff_data = {
        "handoff_id": handoff_id,
        "user_id": user_id,
        "query": user_input,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
        "status": "pending",
        "conversation_summary": get_recent_memory(user_id, 3)
    }
    
    if REDIS_AVAILABLE and redis_client:
        redis_client.setex(f"handoff:{handoff_id}", 3600, json.dumps(handoff_data))
    else:
        handoffs[handoff_id] = handoff_data
    
    return handoff_data

# ============ MAIN PROCESSING ============
async def process_message(user_id: str, user_input: str) -> dict:
    """Main message processing logic"""
    
    # Save user message
    save_to_memory(user_id, "user", user_input)
    
    # Check for escalation
    escalate, reason = should_escalate(user_input)
    
    if escalate:
        handoff = create_handoff(user_id, user_input, reason)
        response = get_escalation_response(handoff["handoff_id"])
        save_to_memory(user_id, "assistant", response)
        
        # Emit via socket.io for real-time updates
        await sio.emit('new_handoff', handoff)
        
        return {
            "escalated": True,
            "handoff_id": handoff["handoff_id"],
            "response": response
        }
    
    # Extract order ID if present
    order_id = extract_order_id(user_input)
    user_lower = user_input.lower()
    
    # Route to appropriate handler
    if any(word in user_lower for word in ["track", "where", "status", "delivery"]):
        if order_id:
            response = get_tracking_response(order_id)
        else:
            response = "I'd be happy to track your order! Please provide your order number (like ORD-12345 or #12345678)."
    
    elif any(word in user_lower for word in ["refund", "return", "money back"]):
        if order_id:
            response = get_refund_response(order_id)
        else:
            response = "I can help with a refund. Please provide your order number so I can process it for you."
    
    elif any(word in user_lower for word in ["cancel", "cancellation"]):
        if order_id:
            response = get_cancel_response(order_id)
        else:
            response = "I can help cancel your order. Please share your order number."
    
    elif any(word in user_lower for word in ["hello", "hi", "hey", "greetings"]):
        response = get_greeting_response(user_id)
    
    elif any(word in user_lower for word in ["help", "what can you do", "capabilities"]):
        response = get_fallback_response()
    
    else:
        response = get_fallback_response()
    
    # Save assistant response
    save_to_memory(user_id, "assistant", response)
    
    return {
        "escalated": False,
        "response": response
    }

# ============ API ENDPOINTS ============
class ChatRequest(BaseModel):
    user_id: str
    message: str

class VoiceRequest(BaseModel):
    user_id: str
    audio_base64: str = ""

@app.get("/")
async def root():
    return {
        "service": "FlowZint AI Customer Support",
        "status": "running",
        "version": "1.0.0",
        "endpoints": ["/chat", "/voice", "/handoffs", "/ws/{user_id}"]
    }

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    result = await process_message(request.user_id, request.message)
    return result

@app.post("/voice")
async def voice_endpoint(request: VoiceRequest):
    # For now, just return a placeholder
    result = await process_message(request.user_id, "I need help with my order")
    return result

@app.get("/handoffs")
async def get_handoffs():
    if REDIS_AVAILABLE and redis_client:
        keys = redis_client.keys("handoff:*")
        result = []
        for key in keys:
            data = redis_client.get(key)
            if data:
                result.append(json.loads(data))
        return result
    else:
        return list(handoffs.values())

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            result = await process_message(user_id, data)
            await websocket.send_json(result)
    except WebSocketDisconnect:
        print(f"User {user_id} disconnected")

# ============ START SERVER ============
if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🎧 FlowZint AI Customer Support System")
    print("=" * 60)
    print(f"📍 API Server: http://localhost:8000")
    print(f"📖 API Docs: http://localhost:8000/docs")
    print(f"🔌 WebSocket: ws://localhost:8000/ws/{{user_id}}")
    print("=" * 60)
    print("✅ Ready to accept connections!")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000) 	