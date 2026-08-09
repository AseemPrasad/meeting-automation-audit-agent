"""Multi-agent DAG architecture for meeting transcript analysis.

Nodes: cleaner -> extractor/auditor -> inspector, orchestrated by a
framework-free state engine with optional human-in-the-loop interruption.
"""

from worker.agents.graph import AgentGraph, build_agent_graph
from worker.agents.state import AgentState

__all__ = ["AgentGraph", "build_agent_graph", "AgentState"]
