"""Thesis (1_DRAFT / 2_EXTRACT) and Synthesis (5_SYNTHESIS) pass handlers."""

from pathlib import Path
from structuredai.ast_reality import ast_sig_hash, extract_symbols, format_reality_md
from structuredai.error_distiller import check_degeneration, distill_error
from structuredai.graph_ops import propagate_ripple
from structuredai.prompts import build_prompt, wrap_untrusted
from structuredai.security_gate import scan_dangerous_calls
from structuredai.validators import anti_trivial_test_gate, check_line_limit, check_placeholders, check_test_monotonicity, preflight_imports


def run_draft(ctx: dict, rel: str, node: dict, temp: float | None, hint: str) -> str:
    """1_DRAFT: generate <=100L code, validate line cap, placeholders, imports & syntax."""
    cfg = ctx["cfg"]
    cpath = ctx["meta_dir"] / rel / "CONTRACT.md"
    contract = cpath.read_text(encoding="utf-8") if cpath.exists() else node.get("purpose", "")
    real_ctx = "\n".join(
        (ctx["meta_dir"] / d / "REALITY.md").read_text(encoding="utf-8")
        for d in node.get("depends_on", []) if (ctx["meta_dir"] / d / "REALITY.md").exists()
    )
    sections = [("CONTRACT", contract), ("NEIGHBOR_REALITY", real_ctx), ("DEPS", ctx["deps_md"])]
    if hint or node.get("last_error"):
        sections.append(("FIX_HINT", f"{hint}\n{node.get('last_error', '')}".strip()))
    sys_p, usr_p = build_prompt("1_DRAFT", cfg, sections)
    code = ctx["llm"].complete("1_DRAFT", sys_p, usr_p, temp=temp).data["code"]
    err = check_line_limit(rel, code, cfg) or check_placeholders(code)
    if not err and cfg.enable_import_preflight:
        imp_errs = preflight_imports(code, Path(rel).suffix, ctx["exports"], ctx["installed_pkgs"])
        err = "; ".join(imp_errs) if imp_errs else None
    if err:
        raise RuntimeError(err)
    target = ctx["jail"].assert_writable_by_agent(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code if code.endswith("\n") else code + "\n", encoding="utf-8")
    ok_syn, out_syn = ctx["adapter"].check_syntax(rel)
    if not ok_syn:
        raise RuntimeError(distill_error(out_syn, code))
    return "2_EXTRACT"


def run_extract(ctx: dict, rel: str, node: dict) -> str:
    """2_EXTRACT: deterministic AST signature extraction + short LLM summary -> REALITY.md."""
    target = ctx["jail"].assert_writable_by_agent(rel)
    code = target.read_text(encoding="utf-8")
    syms = extract_symbols(code, target.suffix)
    ctx["exports"][rel] = set(syms.get("exports", []))
    new_hash = ast_sig_hash(syms)
    if node.get("ast_sig_hash") and node["ast_sig_hash"] != new_hash:
        propagate_ripple(ctx["nodes"], rel)
    node["ast_sig_hash"] = new_hash
    s_p, u_p = build_prompt("2_EXTRACT", ctx["cfg"], [("CODE", wrap_untrusted(rel, code)), ("SIGNATURES", str(syms.get("signatures", [])))])
    purpose = ctx["llm"].complete("2_EXTRACT", s_p, u_p).data.get("purpose_summary", node.get("purpose", ""))
    rpath = ctx["meta_dir"] / rel / "REALITY.md"
    rpath.parent.mkdir(parents=True, exist_ok=True)
    rpath.write_text(format_reality_md(rel, len(code.splitlines()), syms, purpose), encoding="utf-8")
    return "3_CRITIQUE"


def run_synthesis(ctx: dict, rel: str, node: dict, temp: float | None, hint: str) -> str:
    """5_SYNTHESIS -> 6_LOCKED: harden code, write tests, enforce all safety/quality gates."""
    cfg = ctx["cfg"]
    target = ctx["jail"].assert_writable_by_agent(rel)
    prev_code = target.read_text(encoding="utf-8")
    test_rel = ctx["stack"].get("test_pattern", "tests/test_{stem}.py").format(stem=target.stem, dir=str(Path(rel).parent))
    t_path = ctx["jail"].assert_writable_by_agent(test_rel)
    prev_test = t_path.read_text(encoding="utf-8") if t_path.exists() else ""
    secs = [("CODE", wrap_untrusted(rel, prev_code)), ("CONTRACT", node.get("purpose", "")), ("TARGET_TEST", test_rel)]
    if hint or node.get("last_error"):
        secs.append(("FIX_HINT", f"{hint}\n{node.get('last_error', '')}".strip()))
    sys_p, usr_p = build_prompt("5_SYNTHESIS", cfg, secs)
    res = ctx["llm"].complete("5_SYNTHESIS", sys_p, usr_p, temp=temp).data
    opt_code, test_code = res["optimized_code"], res["test_code"]
    err = check_line_limit(rel, opt_code, cfg) or check_line_limit(test_rel, test_code, cfg) or check_placeholders(opt_code) or check_placeholders(test_code)
    err = err or check_degeneration(prev_code, opt_code)
    if not err and cfg.enable_test_monotonicity:
        err = check_test_monotonicity(prev_test, test_code)
    if not err and cfg.enable_dangerous_scan:
        d_errs = scan_dangerous_calls(opt_code) + scan_dangerous_calls(test_code)
        err = "; ".join(d_errs) if d_errs else None
    if not err and cfg.enable_anti_trivial:
        t_errs = anti_trivial_test_gate(test_code, target.stem, target.suffix)
        err = "; ".join(t_errs) if t_errs else None
    if err:
        raise RuntimeError(err)
    target.write_text(opt_code if opt_code.endswith("\n") else opt_code + "\n", encoding="utf-8")
    t_path.parent.mkdir(parents=True, exist_ok=True)
    t_path.write_text(test_code if test_code.endswith("\n") else test_code + "\n", encoding="utf-8")
    ok_l, out_l = ctx["adapter"].lint(rel)
    ok_t, out_t = ctx["adapter"].test_targeted(rel, test_rel)
    if not ok_l or not ok_t:
        raise RuntimeError(distill_error(out_l + "\n" + out_t, opt_code + "\n" + test_code))
    node["test_path"] = test_rel
    node["commit_sha"] = ctx["git"].stage_and_commit([rel, test_rel], f"feat(node): lock {rel}")
    return "6_LOCKED"
