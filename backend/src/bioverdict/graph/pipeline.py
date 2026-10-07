"""A4 DAG: collection -> immutable bundle. Reason/score/report wiring is a later integration."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from bioverdict.graph.collect_nodes import CollectNodes, CollectState


def collection_graph(
    nodes: CollectNodes,
) -> CompiledStateGraph[CollectState, None, CollectState, CollectState]:
    graph = StateGraph(CollectState)
    graph.add_node("collect", nodes.collect)
    graph.add_node("freeze", nodes.freeze)
    graph.add_edge(START, "collect")
    graph.add_edge("collect", "freeze")
    graph.add_edge("freeze", END)
    return graph.compile()
