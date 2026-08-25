#!/usr/bin/env python3
"""
CartPilot Growth Worker Job (Azure Container Apps Job / Cron)
Executes autonomous growth cycles: stagnant stock detection, A/B experiments,
opportunity detection, and verified empirical revenue attribution learning.
"""

import os
import sys
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv()

from backend.agents.growth_worker import execute_autonomous_cycle, run_autonomous_growth_worker

if __name__ == "__main__":
    is_daemon = os.getenv("RUN_AS_DAEMON", "false").lower() == "true"
    if is_daemon:
        import asyncio
        print("🚀 Starting CartPilot Growth Worker in Continuous Daemon Mode...")
        asyncio.run(run_autonomous_growth_worker())
    else:
        print("🚀 Starting CartPilot Growth Worker One-Shot Execution...")
        res = execute_autonomous_cycle()
        print(f"✅ Growth Worker cycle complete: {res}")
