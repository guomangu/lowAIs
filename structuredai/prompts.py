"""Ultra-compact (<150 tok) system prompts and 4096-token budget assembly."""

from structuredai.config import Config

SYSTEM_PROMPTS: dict[str, str] = {
    "0_ARCHITECT": (
        "Role: Software Architect ({stack}). Split SPEC into <= {max_files} files/dir, max depth {max_depth}. "
        "No circular dependencies. Map every REQ-* id. Return ONLY valid JSON."
    ),
    "1_DRAFT": (
        "Role: Unit Coder ({stack}). Implement ONLY the contract. Complete code without TODO, pass, ... or stubs. "
        "Max {max_lines} lines. Use ONLY imports listed in REALITY or DEPS. Return ONLY valid JSON."
    ),
    "2_EXTRACT": (
        "Role: Semantic Summarizer. Given code and AST signatures, write <= 2 concise sentences describing purpose "
        "and side effects. Return ONLY valid JSON."
    ),
    "3_CRITIQUE": (
        "Role: Root Critic. Compare SPEC REQ-* vs REALITY signatures. Report ONLY: interface mismatches, "
        "files >= 85 lines to split, missing REQs. No circular splits. Return ONLY valid JSON."
    ),
    "4_REBALANCE": (
        "Role: Refactorer ({stack}). Apply REFACTOR_ORDERS cleanly. If splitting a file, re-export moved public symbols "
        "and keep >= {min_split} lines per file, <= {max_lines} max. Return ONLY valid JSON."
    ),
    "5_SYNTHESIS": (
        "Role: Optimizer & Tester ({stack}). Harden edge cases and write real unit tests calling the module directly. "
        "No assert True or self-mocking. Code & tests each <= {max_lines} lines. Return ONLY valid JSON."
    ),
}


def estimate_tokens(text: str) -> int:
    """Fast conservative token estimator (~3.2 chars/token)."""
    return max(1, int(len(text) / 3.2) + 1)


def wrap_untrusted(label: str, content: str) -> str:
    """Delimit repo/external text to neutralize indirect prompt injection."""
    safe = content.replace("</UNTRUSTED_CODE>", "<\\/UNTRUSTED_CODE>")
    return f'<UNTRUSTED_CODE source="{label}">\n{safe}\n</UNTRUSTED_CODE>'


def build_prompt(role: str, cfg: Config, sections: list[tuple[str, str]]) -> tuple[str, str]:
    """Format compact system + user prompt strictly within LLM_CTX_SIZE budget."""
    sys_t = SYSTEM_PROMPTS[role].format(
        stack=cfg.target_stack,
        max_files=cfg.max_files_per_dir,
        max_depth=cfg.max_tree_depth,
        max_lines=cfg.max_lines_per_file,
        min_split=cfg.min_split_lines,
    )
    budget = cfg.llm_ctx_size - cfg.llm_max_output_tokens - estimate_tokens(sys_t) - 256
    chunks: list[str] = []
    used = 0
    for title, body in sections:
        if not body.strip():
            continue
        block = f"## {title}\n{body.strip()}\n"
        toks = estimate_tokens(block)
        if used + toks <= budget:
            chunks.append(block)
            used += toks
        else:
            rem_chars = max(0, int((budget - used) * 3.0) - len(title) - 24)
            if rem_chars > 120:
                chunks.append(f"## {title} (truncated)\n{body[:rem_chars]}\n")
            break
    return sys_t, "\n".join(chunks)
