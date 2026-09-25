"""lica command line: init / serve / hook / run / packs / report / doctor."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

import lica
from lica import client
from lica.config import CONFIG_FILENAME, DEFAULT_CONFIG, Config, load_config
from lica.hooks import get_adapter
from lica.packs.loader import PROJECT_PACK_DIR, USER_PACK_DIR, load_packs

app = typer.Typer(
    name="lica",
    help="Typed decision packs for coding agents, powered by Laya.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"lica {lica.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", callback=_version_callback, is_eager=True)
    ] = False,
) -> None:
    pass


def _load(project_dir: Path | None = None) -> tuple[Config, dict, list[str]]:
    config = load_config()
    loaded, errors = load_packs(project_dir or Path.cwd())
    return config, loaded, errors


# --------------------------------------------------------------------------- init


@app.command()
def init(
    project_dir: Annotated[Path, typer.Argument()] = Path("."),
    command: Annotated[
        str, typer.Option(help="Hook command written into agent configs")
    ] = "lica hook --adapter claude-code",
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing lica.toml")] = False,
) -> None:
    """Write lica.toml and install hooks into detected agent configs."""
    project_dir = project_dir.resolve()
    config_path = project_dir / CONFIG_FILENAME

    if config_path.exists() and not force:
        console.print(
            f"[yellow]{CONFIG_FILENAME} already exists[/yellow] (use --force to overwrite)"
        )
    else:
        config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
        console.print(f"[green]wrote {config_path}[/green]")

    (project_dir / PROJECT_PACK_DIR).mkdir(parents=True, exist_ok=True)

    config, loaded, _ = _load(project_dir)
    hook_points = sorted(
        {hp for lp in loaded.values() if config.pack_enabled(lp.pack.pack) for hp in lp.pack.hooks},
        key=lambda p: p.value,
    )

    claude_dir = project_dir / ".claude"
    if config.hooks.get("claude_code") or claude_dir.is_dir():
        claude_dir.mkdir(exist_ok=True)
        settings_path = claude_dir / "settings.json"
        settings: dict[str, Any] = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                console.print(
                    f"[red]{settings_path} is not valid JSON — leaving it untouched[/red]"
                )
                raise typer.Exit(1) from None

        from lica.hooks.claude_code import ClaudeCodeAdapter

        snippet = ClaudeCodeAdapter().settings_snippet(command, hook_points)
        installed = 0
        for event_name, entries in snippet["hooks"].items():
            existing = settings.setdefault("hooks", {}).setdefault(event_name, [])
            already = any(
                "lica hook" in h.get("command", "")
                for entry in existing
                for h in entry.get("hooks", [])
            )
            if not already:
                existing.extend(entries)
                installed += 1

        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        if installed:
            console.print(
                f"[green]installed hooks into {settings_path}[/green] ({installed} events)"
            )
        else:
            console.print("[dim]claude hooks already installed[/dim]")

    console.print(
        "\nNext: [bold]lica serve[/bold] to start the decision daemon, "
        "then use your agent normally. Run [bold]lica doctor[/bold] to check the wiring."
    )


# --------------------------------------------------------------------------- serve


@app.command()
def serve(
    port: Annotated[int | None, typer.Option(help="Override lica.toml server_port")] = None,
    host: Annotated[str | None, typer.Option(help="Override lica.toml server_host")] = None,
) -> None:
    """Run the local decision daemon (keeps the model warm)."""
    from lica.server import run_server

    config, loaded, errors = _load()
    for e in errors:
        err_console.print(f"[red]pack error: {e}[/red]")
    if port:
        config.lica.server_port = port
    if host:
        config.lica.server_host = host

    enabled = [lp.pack for lp in loaded.values() if config.pack_enabled(lp.pack.pack)]
    console.print(
        f"lica daemon on [bold]{config.lica.server_host}:{config.lica.server_port}[/bold] "
        f"— {len(enabled)} packs ({', '.join(p.pack for p in enabled) or 'none'}) "
        f"[{config.lica.mode} mode]"
    )
    run_server(config, enabled, Path.cwd())


# --------------------------------------------------------------------------- hook


@app.command()
def hook(
    adapter: Annotated[str, typer.Option(help="claude-code | generic")] = "generic",
    timeout: Annotated[float, typer.Option(help="Daemon timeout seconds")] = 10.0,
) -> None:
    """Hook entrypoint: stdin JSON -> daemon -> agent-native verdict on stdout."""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)  # unreadable input: exit clean rather than break the agent

    try:
        adapt = get_adapter(adapter)
    except ValueError as e:
        err_console.print(str(e))
        sys.exit(0)

    try:
        event = adapt.parse(payload)
    except ValueError as e:
        err_console.print(f"lica: {e}")
        sys.exit(0)

    config = load_config()
    request = {
        "hook": event.hook_point.value,
        "tool_name": event.tool_name,
        "tool_input": event.tool_input,
        "tool_output": event.tool_output,
        "context": event.context,
    }

    try:
        result = client.decide(
            request, host=config.lica.server_host, port=config.lica.server_port, timeout=timeout
        )
    except client.DaemonUnavailable:
        result = {
            "action": config.lica.on_error,
            "reason": f"lica daemon unreachable — {config.lica.on_error} (is `lica serve` running?)",
            "packs": [],
        }

    out = adapt.emit(
        event,
        result.get("action", "allow"),
        result.get("reason", ""),
        result.get("packs", []),
    )
    if out is not None:
        sys.stdout.write(json.dumps(out) + "\n")
    sys.exit(0)


# --------------------------------------------------------------------------- run


@app.command()
def run(
    pack_name: Annotated[str, typer.Argument(help="Pack to evaluate")],
    stdin: Annotated[bool, typer.Option("--stdin", help="Read event JSON from stdin")] = False,
    state_file: Annotated[
        Path | None, typer.Option("--state-file", help="Read raw state text from file")
    ] = None,
    server: Annotated[bool, typer.Option("--server", help="Evaluate via the daemon")] = False,
    tool: Annotated[str, typer.Option(help="Tool name for matching")] = "Bash",
    hook_point: Annotated[str, typer.Option("--hook", help="Hook point")] = "post_tool_call",
) -> None:
    """Evaluate a single pack against a state — for testing and scripting."""
    if stdin:
        payload = json.loads(sys.stdin.read() or "{}")
        context = {
            "tool_name": payload.get("tool_name", tool),
            "tool_input": payload.get("tool_input") or {},
            "tool_output": payload.get("tool_output", payload.get("tool_response")),
            "cwd": payload.get("cwd", str(Path.cwd())),
        }
    elif state_file:
        context = {
            "tool_name": tool,
            "tool_input": {},
            "tool_output": state_file.read_text(encoding="utf-8"),
            "cwd": str(Path.cwd()),
        }
    else:
        console.print("[red]provide --stdin or --state-file[/red]")
        raise typer.Exit(2)

    context["hook"] = hook_point

    if server:
        config = load_config()
        result = client.decide(
            {**context, "hook": hook_point},
            host=config.lica.server_host,
            port=config.lica.server_port,
        )
        console.print_json(json.dumps(result))
        return

    from lica.engine import DecisionEngine

    config, loaded, errors = _load()
    for e in errors:
        err_console.print(f"[red]{e}[/red]")
    if pack_name not in loaded:
        console.print(f"[red]unknown pack {pack_name!r}[/red] — have: {sorted(loaded)}")
        raise typer.Exit(1)

    engine = DecisionEngine(config)
    verdict = engine.evaluate(loaded[pack_name].pack, context)
    console.print_json(
        json.dumps(
            {
                "action": verdict.action.value,
                "reason": verdict.reason,
                "pack": verdict.pack,
                "latency_ms": round(verdict.latency_ms, 1),
                "answers": verdict.answers,
            },
            default=str,
        )
    )


# --------------------------------------------------------------------------- packs


@app.command(name="packs")
def packs_cmd(
    explain: Annotated[
        str | None, typer.Option("--explain", help="Show one pack's questions and rules")
    ] = None,
) -> None:
    """List loaded decision packs and where they came from."""
    config, loaded, errors = _load()
    for e in errors:
        err_console.print(f"[red]{e}[/red]")

    if explain:
        if explain not in loaded:
            console.print(f"[red]unknown pack {explain!r}[/red]")
            raise typer.Exit(1)
        pack = loaded[explain].pack
        console.print(f"[bold]{pack.pack}[/bold] v{pack.version} — {pack.description}")
        console.print(
            f"hooks: {[h.value for h in pack.hooks]}  tools: {pack.match.tools}  model: {pack.model or config.lica.model}"
        )
        for name, q in pack.questions.items():
            console.print(f"  [cyan]{name}[/cyan] ({q.type}): {q.instructions}")
        console.print("decision:")
        for rule in pack.decision:
            if rule.default is not None:
                console.print(f"  default -> {rule.default.value}")
            else:
                cond = (
                    rule.condition.model_dump(exclude_none=True, by_alias=True)
                    if rule.condition
                    else {}
                )
                console.print(f"  if {cond} -> {rule.action.value}")
        return

    table = Table("pack", "version", "hooks", "enabled", "source")
    for name, lp in sorted(loaded.items()):
        table.add_row(
            name,
            lp.pack.version,
            ", ".join(h.value for h in lp.pack.hooks),
            "yes" if config.pack_enabled(name) else "[dim]no[/dim]",
            lp.source,
        )
    console.print(table)
    console.print(f"[dim]user packs: {USER_PACK_DIR} · project packs: {PROJECT_PACK_DIR}[/dim]")


# --------------------------------------------------------------------------- report


@app.command()
def report(
    json_out: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    last: Annotated[int | None, typer.Option(help="Only the last N entries")] = None,
) -> None:
    """Summarize the decision log — including shadow-mode 'would have' stats."""
    config = load_config()
    log_path = Path.cwd() / config.lica.log_path
    if not log_path.is_file():
        console.print(f"[yellow]no decision log at {log_path}[/yellow]")
        raise typer.Exit(0)

    from lica.log import DecisionLog

    entries = list(DecisionLog(log_path).iter())
    if last:
        entries = entries[-last:]

    by_pack: dict[str, dict[str, int]] = {}
    enforced = {"block": 0, "ask": 0}
    shadow_would = {"block": 0, "ask": 0}
    for e in entries:
        action = e.get("action", "allow")
        for p in e.get("packs", []):
            stats = by_pack.setdefault(p["name"], {})
            stats[p["action"]] = stats.get(p["action"], 0) + 1
        if e.get("shadow") and action in shadow_would:
            shadow_would[action] += 1
        elif e.get("enforced") and action in enforced:
            enforced[action] += 1

    if json_out:
        console.print_json(
            json.dumps(
                {
                    "total": len(entries),
                    "by_pack": by_pack,
                    "enforced": enforced,
                    "shadow_would": shadow_would,
                }
            )
        )
        return

    console.print(f"[bold]{len(entries)}[/bold] decisions logged at {log_path}")
    table = Table("pack", "allow", "log", "ask", "block")
    for name, stats in sorted(by_pack.items()):
        table.add_row(
            name,
            str(stats.get("allow", 0)),
            str(stats.get("log", 0)),
            str(stats.get("ask", 0)),
            str(stats.get("block", 0)),
        )
    console.print(table)
    if enforced["block"] or enforced["ask"]:
        console.print(f"enforced: {enforced['block']} blocks, {enforced['ask']} asks")
    if shadow_would["block"] or shadow_would["ask"]:
        console.print(
            f"[yellow]shadow mode:[/yellow] would have blocked {shadow_would['block']}, "
            f"asked on {shadow_would['ask']}"
        )


# --------------------------------------------------------------------------- doctor


@app.command()
def doctor() -> None:
    """Check install, model availability, daemon reachability, and hook wiring."""
    ok = True

    def check(good: bool, label: str, detail: str = "") -> None:
        nonlocal ok
        ok = ok and good
        mark = "[green]ok[/green]" if good else "[red]fail[/red]"
        console.print(f"  {mark}  {label}{(' — ' + detail) if detail else ''}")

    console.print("[bold]lica doctor[/bold]")
    check(True, "python", f"{sys.version.split()[0]}")

    try:
        import laya

        check(True, "laya installed", getattr(laya, "__version__", "?"))
    except ImportError:
        check(False, "laya installed", "pip install laya")

    try:
        import torch

        check(True, "torch", f"{torch.__version__} (cuda: {torch.cuda.is_available()})")
    except ImportError:
        check(False, "torch", "needed by laya")

    config_path = Path.cwd() / CONFIG_FILENAME
    check(
        config_path.is_file(),
        f"{CONFIG_FILENAME} found",
        str(config_path) if config_path.is_file() else "run `lica init`",
    )

    config = load_config()
    _, loaded, errors = _load()
    check(
        not errors,
        "packs valid",
        f"{len(loaded)} loaded" + (f", {len(errors)} errors" if errors else ""),
    )

    try:
        h = client.health(config.lica.server_host, config.lica.server_port)
        check(True, f"daemon on :{config.lica.server_port}", f"warmed={h.get('warmed')}")
    except Exception:
        check(False, f"daemon on :{config.lica.server_port}", "run `lica serve`")

    settings = Path.cwd() / ".claude" / "settings.json"
    if settings.is_file():
        wired = "lica hook" in settings.read_text(encoding="utf-8")
        check(wired, "claude hooks", str(settings))
    else:
        console.print("  [dim]--[/dim]  .claude/settings.json absent (adapter not installed here)")

    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
