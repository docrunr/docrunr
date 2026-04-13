"""DocRunr CLI — document to clean Markdown and chunks."""

from __future__ import annotations

import fnmatch
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

from . import parsers  # noqa: F401 — triggers parser registration
from .models import BatchReport, Result
from .pipeline import process_file

app = typer.Typer(
    name="docrunr",
    help="You give it a document. It gives you clean Markdown and chunks.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_time=False, show_path=False)],
    )


def _collect_files(input_path: Path, include: str | None = None) -> list[Path]:
    """Collect files from a path — single file or directory."""
    if input_path.is_file():
        return [input_path]

    if input_path.is_dir():
        files = sorted(
            f for f in input_path.rglob("*") if f.is_file() and not f.name.startswith(".")
        )
        if include:
            if "*" in include or "?" in include:
                files = [f for f in files if fnmatch.fnmatch(f.name, include)]
            else:
                files = [f for f in files if include.lower() in f.name.lower()]
        return files

    return []


def _resolve_out_path(filepath: Path, input_root: Path, out_dir: Path) -> tuple[Path, str]:
    """Compute output directory and stem, preserving relative structure."""
    if input_root.is_dir():
        rel = filepath.parent.relative_to(input_root)
        target_dir = out_dir / rel
    else:
        target_dir = out_dir
    return target_dir, filepath.stem


def _process_one(filepath: Path, input_root: Path, out_dir: Path) -> tuple[Path, Result, float]:
    """Process a single file, write output, return (path, result, elapsed)."""
    t0 = time.monotonic()
    result = process_file(filepath)
    elapsed = time.monotonic() - t0
    if result.ok:
        target_dir, stem = _resolve_out_path(filepath, input_root, out_dir)
        result.write(target_dir, stem)
    return filepath, result, elapsed


@app.command()
def main(
    input_path: Path = typer.Argument(
        ...,
        help="File or directory to process.",
        exists=True,
        readable=True,
    ),
    out: Path = typer.Option(
        None,
        "--out",
        "-o",
        help="Output directory. Default: next to input.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show extraction details and timing.",
    ),
    report: bool = typer.Option(
        False,
        "--report",
        "-r",
        help="Write a batch report JSON to output dir.",
    ),
    workers: int = typer.Option(
        0,
        "--workers",
        "-w",
        help="Parallel workers for batch processing. 0 = auto (CPU count).",
    ),
    include: str = typer.Option(
        None,
        "--include",
        "-i",
        help="Filter files by extension or glob (e.g. 'docx', '*.pdf').",
    ),
) -> None:
    """Process documents into clean Markdown and structured chunks."""
    _setup_logging(verbose)

    files = _collect_files(input_path, include)
    if not files:
        msg = f"[red]No files found at {input_path}"
        if include:
            msg += f" matching '{include}'"
        msg += "[/red]"
        console.print(msg)
        raise typer.Exit(code=2)

    out_dir = out or (input_path if input_path.is_dir() else input_path.parent)
    num_workers = workers if workers > 0 else min(os.cpu_count() or 4, len(files))
    use_parallel = len(files) > 1 and num_workers > 1

    batch = BatchReport()
    start = time.monotonic()

    if use_parallel:
        if verbose:
            console.print(f"[dim]Processing {len(files)} files with {num_workers} workers[/dim]\n")
        _run_parallel(files, input_path, out_dir, batch, verbose, num_workers)
    else:
        _run_sequential(files, input_path, out_dir, batch, verbose)

    batch.duration_seconds = time.monotonic() - start

    if report:
        report_path = batch.write(out_dir)
        console.print(f"\n[dim]Report written to {report_path}[/dim]")

    console.print(
        f"\n[bold]{batch.succeeded}/{batch.total}[/bold] files processed"
        f" in {batch.duration_seconds:.1f}s"
    )

    if batch.failed > 0:
        raise typer.Exit(code=1)


def _run_sequential(
    files: list[Path],
    input_root: Path,
    out_dir: Path,
    batch: BatchReport,
    verbose: bool,
) -> None:
    for filepath in files:
        _, result, elapsed = _process_one(filepath, input_root, out_dir)
        batch.add(result)
        _print_result(filepath, result, elapsed, verbose)


def _run_parallel(
    files: list[Path],
    input_root: Path,
    out_dir: Path,
    batch: BatchReport,
    verbose: bool,
    num_workers: int,
) -> None:
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {pool.submit(_process_one, fp, input_root, out_dir): fp for fp in files}
        for future in as_completed(futures):
            filepath, result, elapsed = future.result()
            batch.add(result)
            _print_result(filepath, result, elapsed, verbose)


def _print_result(filepath: Path, result: Result, elapsed: float, verbose: bool) -> None:
    if result.ok:
        if verbose:
            console.print(
                f"  [green]✓[/green] {filepath.name} → "
                f"{len(result.chunks)} chunks, {result.total_tokens} tokens "
                f"[dim]({elapsed:.1f}s)[/dim]"
            )
        else:
            console.print(f"  [green]✓[/green] {filepath.name}")
    else:
        console.print(f"  [red]✗[/red] {filepath.name}: {result.error}")
