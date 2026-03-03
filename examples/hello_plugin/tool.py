"""
Hello World Plugin — AgentOS Example
======================================
Demonstrates the minimal plugin structure for AgentOS.
Use this as a template for building your own plugins.
"""

# REQUIRED: TOOL_SCHEMA defines how the Agent sees and uses your tool
TOOL_SCHEMA = {
    "name": "hello_world",
    "description": "A simple greeting tool that says hello to the user in multiple languages.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the person to greet"
            },
            "language": {
                "type": "string",
                "enum": ["en", "zh", "ja", "ko", "es"],
                "default": "en",
                "description": "Language for the greeting"
            }
        },
        "required": ["name"]
    },
    "requires_network": False
}


def execute(arguments: dict) -> str:
    """
    Main entry point — called by AgentOS when the tool is invoked.

    Args:
        arguments: Parsed arguments matching TOOL_SCHEMA.parameters

    Returns:
        String result to send back to the Agent
    """
    name = arguments.get("name", "World")
    language = arguments.get("language", "en")

    greetings = {
        "en": f"Hello, {name}! 👋 Welcome to AgentOS.",
        "zh": f"你好，{name}！👋 歡迎使用 AgentOS。",
        "ja": f"こんにちは、{name}！👋 AgentOS へようこそ。",
        "ko": f"안녕하세요, {name}! 👋 AgentOS에 오신 것을 환영합니다.",
        "es": f"¡Hola, {name}! 👋 Bienvenido a AgentOS.",
    }

    return greetings.get(language, greetings["en"])
