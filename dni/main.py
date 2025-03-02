#!/usr/bin/env python3

from typing import Optional, List
import subprocess
import re
import typer
import click
import shlex
from pathlib import Path

app = typer.Typer(
    help="Devcontainer Nix Injector (dni) - Tool for injecting devcontainers with Nix configs"
)

def run_command(
    cmd: List[str], show_output: bool = True
) -> subprocess.CompletedProcess:
    """Run a shell command and optionally show its output."""
    return subprocess.run(cmd, check=False, capture_output=not show_output, text=True)


def devcontainer_exec(
    workspace_folder: str, command: str, remote_env: Optional[dict] = None
) -> subprocess.CompletedProcess:
    """Execute a command in the devcontainer."""
    cmd = ["devcontainer", "exec", "--workspace-folder", workspace_folder]

    if remote_env:
        for key, value in remote_env.items():
            cmd.extend(["--remote-env", f"{key}={value}"])

    cmd.extend(["bash", "-c", command])
    return run_command(cmd)


def command_in_container_available(workspace_folder: str, command: str) -> bool:
    """Check that programm is available in container."""
    cmd = [
        "devcontainer",
        "exec",
        "--workspace-folder",
        str(workspace_folder),
        "bash",
        "-c",
        f"command -v {shlex.quote(command)}",
    ]
    return run_command(cmd, show_output=False).returncode == 0


def start_devcontainer(workspace_dir: Path, purge: bool) -> subprocess.CompletedProcess:
    typer.echo(f"Starting devcontainer in {workspace_dir}...")

    cmd = ["devcontainer", "up"]
    cmd.extend(["--workspace-folder", workspace_dir])
    if purge:
        cmd.extend(["--remove-existing-container"])

    return run_command(cmd)


def validate_url(value: str) -> str:
    if value is None:
        return None
    url_pattern = re.compile(r"^https?://[\w\-\.]+\.[a-z]{2,}(/.*)?$")
    if not url_pattern.match(value):
        raise typer.BadParameter(f"Invalid URL: {value}")
    return value


def validate_github(value: str) -> str:
    if value is None:
        return None
    github_pattern = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    if not github_pattern.match(value):
        raise typer.BadParameter(
            "Invalid GitHub repo format. Use format: username/repo"
        )
    return value


def validate_sources(ctx: typer.Context, param: click.Parameter, value: str) -> str:
    other_param = "github" if param.name == "repo" else "repo"
    other_value = ctx.params.get(other_param)

    if value is not None and other_value is not None:
        raise typer.BadParameter("Cannot specify both --repo and --github")

    if param.name == "github" and value is None and ctx.params.get("repo") is None:
        raise typer.BadParameter("Must specify either --repo or --github")

    return value


@app.command("setup")
def setup_devcontainer(
    workspace_dir: Path = typer.Argument(
        Path("."),
        dir_okay=True,
        file_okay=False,
        help="Work directory containing devcontainer",
    ),
    repo: Optional[str] = typer.Option(
        None,
        "--repo",
        "-r",
        callback=lambda ctx, param, value: validate_sources(
            ctx, param, validate_url(value)
        ),
        help="URL to the repository",
    ),
    github: Optional[str] = typer.Option(
        None,
        "--github",
        "-g",
        callback=lambda ctx, param, value: validate_sources(
            ctx, param, validate_github(value)
        ),
        help="GitHub repo in format username/repo",
    ),
    config: str = typer.Option(..., help="Config name to apply"),
    purge: bool = typer.Option(False, "--purge", help="Purge existing docker instance"),
) -> None:
    """Set up a devcontainer with Nix, home-manager and personal configurations."""

    if start_devcontainer(workspace_dir, purge).returncode:
        typer.echo("Failed to run container!")
        return

    typer.echo("Devcontainer started successfully! Start environment setup...")

    typer.echo("Installing system dependencies...")
    if not command_in_container_available(workspace_dir, "apt"):
        typer.echo("System doesn't contain supported package manager!")
        return

    deps_to_install = "curl"
    if not command_in_container_available(workspace_dir, deps_to_install):
        devcontainer_exec(
            workspace_dir, f"sudo apt update && sudo apt install -y {deps_to_install}"
        ).check_returncode()

    if not command_in_container_available(workspace_dir, "nix"):
        typer.echo("Installing nix...")

        devcontainer_exec(
            workspace_dir,
            "curl -L https://nixos.org/nix/install | "
            + "sh -s -- --no-daemon --nix-extra-conf-file <(echo 'sandbox = false') && "
            + ". $HOME/.nix-profile/etc/profile.d/nix.sh",
        ).check_returncode()

    if not command_in_container_available(workspace_dir, "home-manager"):
        typer.echo("Installing home-manager...")

        devcontainer_exec(
            workspace_dir,
            "nix-channel --add https://github.com/nix-community/home-manager/archive/master.tar.gz home-manager &> /dev/null "
            + "nix-channel --update && nix-shell '<home-manager>' -A install &> /dev/null",
        ).check_returncode()

    typer.echo("Applying personal configuration...")

    formatted_nix_input = f"github:{github}" if github else repo
    nix_env = {
        "NIX_CONFIG": "experimental-features = nix-command flakes"
    }
    
    command = (
        f"nix run --inputs-from {formatted_nix_input} home-manager -- "
        f"switch --flake {formatted_nix_input}#{config} -b backup"
    )
    
    # Execute the command with the environment variable
    devcontainer_exec(workspace_dir, command, remote_env=nix_env).check_returncode()

    typer.echo("Devcontainer setup completed successfully!")


@app.command("shell")
def shell_devcontainer(
    workspace_dir: Path = typer.Argument(
        Path("."),
        dir_okay=True,
        file_okay=False,
        help="Work directory containing devcontainer",
    ),
):
    """Open an interactive shell in the devcontainer"""
    typer.echo(f"Opening shell in devcontainer at {workspace_dir}...")

    cmd = ["devcontainer", "exec", "--workspace-folder", workspace_dir, "zsh", "-i"]
    if run_command(cmd).returncode:
        typer.echo("Failed to run shell in container!")


if __name__ == "__main__":
    app()
