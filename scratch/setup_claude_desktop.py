"""
Helper script to configure Claude Desktop with CartPilot MCP Server
"""

import os
import json

CONFIG_DIR = os.path.expanduser("~/Library/Application Support/Claude")
CONFIG_PATH = os.path.join(CONFIG_DIR, "claude_desktop_config.json")

PROJECT_DIR = "/Users/vishaldhariwal/Code/Projects/CartPilot"
PYTHON_BIN = os.path.join(PROJECT_DIR, "venv/bin/python")
DB_PATH = os.path.join(PROJECT_DIR, "cartpilot.db")
ENV_PATH = os.path.join(PROJECT_DIR, ".env")

os.makedirs(CONFIG_DIR, exist_ok=True)

# Parse project .env file
env_vars = {
    "PYTHONPATH": PROJECT_DIR,
    "BYPASS_RAZORPAY": "true",
    "CARTPILOT_DB": DB_PATH,
    "PYTHONDONTWRITEBYTECODE": "1"
}

if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()

existing_config = {}
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            existing_config = json.load(f)
    except Exception:
        existing_config = {}

if "mcpServers" not in existing_config:
    existing_config["mcpServers"] = {}

# Configure CartPilot MCP server with all project env variables
existing_config["mcpServers"]["cartpilot"] = {
    "command": PYTHON_BIN,
    "args": ["-B", "-m", "backend.mcp_server"],
    "cwd": PROJECT_DIR,
    "env": env_vars
}

with open(CONFIG_PATH, "w") as f:
    json.dump(existing_config, f, indent=2)

print("=" * 60)
print("✅ Claude Desktop configuration updated successfully with all .env keys!")
print(f"📁 Config file: {CONFIG_PATH}")
print(f"🔑 Included Keys: {', '.join(env_vars.keys())}")
print("=" * 60)
print("\n👉 Next Step: Restart Claude Desktop (Cmd + Q, then reopen it).")