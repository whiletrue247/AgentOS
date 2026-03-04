# AgentOS Architecture Overview

AgentOS is built upon 11 core modules that work together to provide a robust, resilient, and highly scalable OS layer for AI Agents.

## The Modules
1. **01_Kernel**: The entry point. Loads the Agent's identity via `SOUL.md`.
2. **02_Memory**: Hybrid storage (SQLite, ChromaDB) integrating specialized memory engines like Mem0.
3. **03_Tool_System**: A sandboxed execution environment (Docker, MCP) to run external logic safely.
4. **04_Engine**: The core router and executor handling messages, loops, cost-guards, and zero-trust policies.
5. **05_Orchestrator**: Sub-agent swarms using LangGraph/CrewAI for multi-agent DAG flows.
6. **06_Embodiment**: GUI visualization and desktop control via Puppeteer/CDP and Semantic Vision.
7. **07_PKG**: Personal Knowledge Graph via Neo4j and NetworkX.
8. **08_Dashboard**: Terminal CLI & Dashboard observability.
9. **09_OS_Integration**: Bridging the gap natively with the host OS (Applescript, Accessibility APIs).
10. **10_Marketplace**: A decentralized platform to exchange tools, souls, and extensions.
11. **11_Sync_Handoff**: P2P web-socket transfer to hand off current state and tasks seamlessly to another device.

## Security (Zero Trust)
All terminal and high-impact executions trigger a `Human-in-the-Loop` verification inside the **04_Engine**. Sandbox timeouts and network blocks ensure the Agent does not corrupt its host machine.
