"""Pass 0 (Architect) and Pass 2 Antithesis (Critique & Rebalance) handlers."""

from pathlib import Path
from structuredai.graph_ops import detect_cycles, propagate_ripple
from structuredai.prompts import build_prompt, wrap_untrusted
from structuredai.validators import check_line_limit, check_placeholders


def run_architect(ctx: dict, spec_text: str) -> list[str]:
    """0_ARCHITECT: decompose SPEC.md into DAG-verified node contracts."""
    sys_p, usr_p = build_prompt("0_ARCHITECT", ctx["cfg"], [("SPEC", wrap_untrusted("SPEC.md", spec_text))])
    files = ctx["llm"].complete("0_ARCHITECT", sys_p, usr_p).data.get("files", [])
    deps = {f["path"].lstrip("./"): [d.lstrip("./") for d in f.get("depends_on", [])] for f in files}
    cyc = detect_cycles(deps)
    if cyc:
        raise ValueError(f"Circular dependency rejected in DAG: {' -> '.join(cyc)}")
    for f in files:
        rel = f["path"].lstrip("./")
        if len(Path(rel).parts) > ctx["cfg"].max_tree_depth:
            raise ValueError(f"Path exceeds MAX_TREE_DEPTH: {rel}")
        ctx["jail"].assert_writable_by_agent(rel)
        ctx["nodes"].setdefault(rel, {
            "state": "1_DRAFT", "purpose": f.get("purpose", ""), "depends_on": deps[rel],
            "req_ids": f.get("req_ids", []), "is_entry": bool(f.get("is_entry", False)),
            "retries": 0, "rebalance_cycles": 0, "time_spent_seconds": 0.0, "history_hashes": [],
        })
        cpath = ctx["meta_dir"] / rel / "CONTRACT.md"
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(f"# CONTRACT: {rel}\n- deps: {deps[rel]}\n- reqs: {f.get('req_ids', [])}\n- purpose: {f.get('purpose', '')}\n", encoding="utf-8")
    return list(deps.keys())


def run_critique(ctx: dict, rel: str, node: dict) -> str:
    """3_CRITIQUE: confront root SPEC vs aggregated REALITY.md, bounded by max_rebalance."""
    if node.get("rebalance_cycles", 0) >= ctx["cfg"].max_rebalance_cycles:
        return "5_SYNTHESIS"
    realities = []
    for p in sorted(ctx["meta_dir"].rglob("REALITY.md")):
        realities.append(p.read_text(encoding="utf-8"))
    secs = [("SPEC", wrap_untrusted("SPEC.md", ctx["spec_text"])), ("REALITIES", "\n".join(realities)), ("TARGET", rel)]
    sys_p, usr_p = build_prompt("3_CRITIQUE", ctx["cfg"], secs)
    res = ctx["llm"].complete("3_CRITIQUE", sys_p, usr_p).data
    orders = [o for o in res.get("orders", []) if o.get("target_path", "").lstrip("./") == rel]
    if res.get("converged", False) or not orders:
        return "5_SYNTHESIS"
    opath = ctx["meta_dir"] / rel / "REFACTOR_ORDERS.md"
    opath.parent.mkdir(parents=True, exist_ok=True)
    opath.write_text("\n".join(f"- [{o['action']}] {o['reason']}" for o in orders) + "\n", encoding="utf-8")
    return "4_REBALANCE"


def run_rebalance(ctx: dict, rel: str, node: dict, temp: float | None) -> str:
    """4_REBALANCE: apply REFACTOR_ORDERS.md (incl. safe split) and trigger re-extract."""
    cfg = ctx["cfg"]
    target = ctx["jail"].assert_writable_by_agent(rel)
    cur_code = target.read_text(encoding="utf-8") if target.is_file() else ""
    orders_p = ctx["meta_dir"] / rel / "REFACTOR_ORDERS.md"
    orders_txt = orders_p.read_text(encoding="utf-8") if orders_p.is_file() else ""
    sys_p, usr_p = build_prompt("4_REBALANCE", cfg, [("CODE", wrap_untrusted(rel, cur_code)), ("ORDERS", orders_txt)])
    files = ctx["llm"].complete("4_REBALANCE", sys_p, usr_p, temp=temp).data.get("files", [])
    if not files:
        raise RuntimeError("Refactorer returned no files")
    for item in files:
        fpath = item["path"].lstrip("./")
        fcode = item["code"]
        err = check_line_limit(fpath, fcode, cfg) or check_placeholders(fcode)
        if not err and len(files) > 1 and len(fcode.splitlines()) < cfg.min_split_lines:
            err = f"Split fragment too small (<{cfg.min_split_lines} lines): {fpath}"
        if err:
            raise RuntimeError(err)
        dest = ctx["jail"].assert_writable_by_agent(fpath)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(fcode if fcode.endswith("\n") else fcode + "\n", encoding="utf-8")
        if fpath != rel and fpath not in ctx["nodes"]:
            ctx["nodes"][fpath] = {"state": "2_EXTRACT", "depends_on": [], "retries": 0, "rebalance_cycles": 1, "time_spent_seconds": 0.0, "history_hashes": []}
    node["rebalance_cycles"] = int(node.get("rebalance_cycles", 0)) + 1
    propagate_ripple(ctx["nodes"], rel)
    return "2_EXTRACT"
