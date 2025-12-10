import json
import requests
import ollama

OPS_API_BASE = "http://127.0.0.1:8000"   # port-forward from k8s


# ----------- Tool implementations -----------
def redis_get(key: str):
    return requests.get(f"{OPS_API_BASE}/redis/get", params={"key": key}).json()

def redis_set(key: str, value: str):
    return requests.post(
        f"{OPS_API_BASE}/redis/set",
        json={"key": key, "value": value},
    ).json()

def redis_replication_info():
    return requests.get(f"{OPS_API_BASE}/redis/replication-info").json()

def list_redis_pods():
    return requests.get(f"{OPS_API_BASE}/k8s/pods").json()

def restart_pod(pod_name: str):
    return requests.post(
        f"{OPS_API_BASE}/k8s/restart-pod",
        json={"pod_name": pod_name},
    ).json()


tools = [
    {
        "type": "function",
        "function": {
            "name": "redis_get",
            "description": "Get a value from Redis by key.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redis_set",
            "description": "Set a key in Redis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redis_replication_info",
            "description": "Get master/replica replication details.",
            "parameters": {"type": "object", "properties": {}}
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_redis_pods",
            "description": "List Redis pods from Kubernetes.",
            "parameters": {"type": "object", "properties": {}}
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restart_pod",
            "description": "Restart a Redis pod.",
            "parameters": {
                "type": "object",
                "properties": {"pod_name": {"type": "string"}},
                "required": ["pod_name"]
            },
        },
    },
]

tool_map = {
    "redis_get": redis_get,
    "redis_set": redis_set,
    "redis_replication_info": redis_replication_info,
    "list_redis_pods": list_redis_pods,
    "restart_pod": restart_pod,
}


# ----------- Chat Loop using Ollama -----------
def chat():
    print("🚀 Redis AI Ops (Ollama version) started")
    print("Type 'exit' to quit.\n")

    messages = []

    while True:
        user = input("You: ")
        if user.lower() == "exit":
            break

        messages.append({"role": "user", "content": user})

        # Send to Ollama with tools enabled
        response = ollama.chat(
            model="qwen2.5:1.5b",
            messages=messages,
            tools=tools
        )

        message = response["message"]

        # CASE 1: Ollama wants to call a function
        if "tool_calls" in message:
            for call in message["tool_calls"]:
                name = call["function"]["name"]
                args = call["function"]["arguments"]
                print(f"\n🤖 Model requested tool: {name} {args}")

                # Execute the real function
                result = tool_map[name](**args)
                print(f"🔧 Tool result: {result}")

                # Add tool result back into message stream
                messages.append(message)
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result),
                    "name": name,
                })

            # After tool call: ask model to summarize naturally
            final = ollama.chat(
                model="qwen2.5:1.5b",
                messages=messages
            )
            print(f"\nAI: {final['message']['content']}")
            messages.append({"role": "assistant", "content": final["message"]["content"]})

        else:
            # CASE 2: Normal AI response
            print(f"\nAI: {message['content']}")
            messages.append({"role": "assistant", "content": message["content"]})


if __name__ == "__main__":
    chat()
