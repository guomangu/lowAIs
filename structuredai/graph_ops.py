"""Dependency graph operations: DAG cycle check, critical path & ripple invalidation."""


def detect_cycles(deps: dict[str, list[str]]) -> list[str]:
    """Return a cycle path [A, B, A] if any circular dependency exists, else []."""
    state: dict[str, int] = {}
    stack: list[str] = []

    def dfs(node: str) -> list[str]:
        state[node] = 1
        stack.append(node)
        for nxt in deps.get(node, []):
            if nxt not in deps:
                continue
            if state.get(nxt) == 1:
                idx = stack.index(nxt)
                return stack[idx:] + [nxt]
            if state.get(nxt, 0) == 0:
                cyc = dfs(nxt)
                if cyc:
                    return cyc
        stack.pop()
        state[node] = 2
        return []

    for n in sorted(deps):
        if state.get(n, 0) == 0:
            cyc = dfs(n)
            if cyc:
                return cyc
    return []


def reverse_dependents(nodes: dict[str, dict]) -> dict[str, set[str]]:
    """Map each node to the set of nodes that depend on it."""
    rev: dict[str, set[str]] = {k: set() for k in nodes}
    for name, info in nodes.items():
        for dep in info.get("depends_on", []):
            if dep in rev:
                rev[dep].add(name)
    return rev


def compute_priorities(nodes: dict[str, dict]) -> dict[str, int]:
    """Compute critical-path priority: 3*is_entry + 2*downstream_count - depth."""
    rev = reverse_dependents(nodes)
    scores: dict[str, int] = {}
    for name, info in nodes.items():
        is_entry = 1 if info.get("is_entry") else 0
        depth = max(0, len(name.split("/")) - 1)
        manual_boost = int(info.get("priority_boost", 0))
        scores[name] = (3 * is_entry) + (2 * len(rev.get(name, set()))) - depth + manual_boost
    return scores


def propagate_ripple(nodes: dict[str, dict], changed_node: str) -> list[str]:
    """Flag all 6_LOCKED downstream dependents of changed_node as NEEDS_REVERIFY."""
    rev = reverse_dependents(nodes)
    impacted: list[str] = []
    for dep_name in sorted(rev.get(changed_node, set())):
        if nodes[dep_name].get("state") == "6_LOCKED":
            nodes[dep_name]["state"] = "NEEDS_REVERIFY"
            impacted.append(dep_name)
    return impacted


def next_actionable_node(nodes: dict[str, dict]) -> str | None:
    """Pick highest-priority actionable node (NEEDS_REVERIFY first, then ready DAG nodes)."""
    scores = compute_priorities(nodes)
    reverify = [k for k, v in nodes.items() if v.get("state") == "NEEDS_REVERIFY"]
    if reverify:
        return sorted(reverify, key=lambda k: (-scores.get(k, 0), k))[0]
    active_states = {"0_ARCHITECT", "1_DRAFT", "2_EXTRACT", "3_CRITIQUE", "4_REBALANCE", "5_SYNTHESIS"}
    ready: list[str] = []
    for name, info in nodes.items():
        if info.get("state") not in active_states:
            continue
        deps = info.get("depends_on", [])
        if any(nodes.get(d, {}).get("state") == "FAILED_MANUAL_REVIEW" for d in deps):
            info["state"] = "BLOCKED_BY_UPSTREAM"
            continue
        if all(d not in nodes or nodes[d].get("state") in {"6_LOCKED", "LEGACY_EXEMPT"} for d in deps):
            ready.append(name)
    if not ready:
        return None
    return sorted(ready, key=lambda k: (-scores.get(k, 0), k))[0]
