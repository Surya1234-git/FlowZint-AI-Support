"use client";
import { useState, useEffect } from "react";
import axios from "axios";

export default function Home() {
  const [userId, setUserId] = useState("");
useEffect(() => {
  setUserId(`user_${Math.random().toString(36).substr(2, 9)}`);
}, []);
  const [messages, setMessages] = useState<{role: string, content: string}[]>([]);
  const [input, setInput] = useState("");
  const [handoffs, setHandoffs] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {const res = await axios.get("/api/handoffs");
        setHandoffs(res.data);
      } catch (e) {
        console.log("Backend not connected yet");
      }
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const sendMessage = async () => {
    if (!input.trim()) return;
    
    const userMessage = input;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);
    
    try {
      const res = await axios.post("/api/chat",  { 
        user_id: userId, 
        message: userMessage 
      });
      
      setMessages(prev => [...prev, { role: "assistant", content: res.data.response }]);
      
      if (res.data.escalated) {
        setMessages(prev => [...prev, { 
          role: "system", 
          content: `⚠️ Escalated to human agent. Reference: ${res.data.handoff_id}` 
        }]);
      }
    } catch (error) {
      setMessages(prev => [...prev, { 
        role: "system", 
        content: "❌ Error connecting to server. Make sure backend is running on port 8000" 
      }]);
    }
    setIsLoading(false);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <div className="bg-gradient-to-r from-blue-600 to-purple-600 p-4 shadow-lg">
        <h1 className="text-2xl font-bold">🎧 FlowZint AI Customer Support</h1>
        <p className="text-sm opacity-90">User ID: {userId} | Persistent Memory Active</p>
      </div>

      <div className="flex h-[calc(100vh-80px)]">
        <div className="flex-1 flex flex-col p-4">
          <div className="flex-1 overflow-y-auto space-y-2 mb-4">
            {messages.length === 0 && (
              <div className="text-center text-gray-400 mt-10">
                <p>👋 Welcome! Try asking:</p>
                <p className="text-sm mt-2">• &quot;Hello&quot;</p>
                <p className="text-sm">• &quot;Track my order ORD-12345&quot;</p>
                <p className="text-sm">• &quot;I want a refund&quot;</p>
                <p className="text-sm">• &quot;Cancel my order&quot;</p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-md p-3 rounded-lg ${
                  msg.role === "user" ? "bg-blue-600" : 
                  msg.role === "system" ? "bg-yellow-600" : "bg-gray-700"
                }`}>
                  {msg.content}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-gray-700 p-3 rounded-lg">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100"></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200"></div>
                  </div>
                </div>
              </div>
            )}
          </div>
          
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && sendMessage()}
              className="flex-1 p-3 rounded-lg bg-gray-800 border border-gray-700 text-white focus:outline-none focus:border-blue-500"
              placeholder="Type your message here..."
              disabled={isLoading}
            />
            <button 
              onClick={sendMessage}
              disabled={isLoading}
              className="px-6 py-3 bg-blue-600 rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
            >
              Send
            </button>
          </div>
          
          <div className="mt-4 text-xs text-gray-400 text-center flex justify-center gap-6">
            <span>⚡ Response time: ~1s</span>
            <span>🧠 Memory: Active</span>
            <span>✅ Guardrails: Enabled</span>
          </div>
        </div>

        <div className="w-80 bg-gray-800 border-l border-gray-700 p-4 overflow-y-auto">
          <h2 className="font-bold mb-3 text-yellow-400 flex items-center gap-2">
            <span>👥</span> Human Escalation Queue
            {handoffs.length > 0 && (
              <span className="bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">{handoffs.length}</span>
            )}
          </h2>
          {handoffs.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">No active handoffs</p>
          ) : (
            handoffs.map((h, i) => (
              <div key={i} className="bg-gray-700 p-3 rounded-lg mb-3 text-sm">
                <p className="font-mono text-xs text-gray-300 mb-1">ID: {h.handoff_id}</p>
                <p className="text-gray-300 text-xs mb-1">{new Date(h.timestamp).toLocaleTimeString()}</p>
                <p className="text-white text-sm font-medium truncate">{h.query}</p>
                <button className="mt-2 w-full px-3 py-1 bg-green-600 rounded text-xs hover:bg-green-700 transition">
                  Claim & Respond
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}