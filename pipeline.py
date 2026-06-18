"""
pipeline.py — Crestview Capital Partners: AI-Powered Client Onboarding POC

Entry point. Run with:
    python pipeline.py                                              # full CSV batch
    python pipeline.py --app APP-0303                              # single application by ID
    python pipeline.py --skip-airtable                             # skip Airtable push (local test)
    python pipeline.py --csv data/custom.csv                       # different CSV file
    python pipeline.py --document data/sample_intake_email.txt     # Stage 0: unstructured text
    python pipeline.py --marker-file data/sample_intake.pdf        # Stage 0: PDF via Marker

Pipeline stages per application (CSV path):
    1. Load CSV row → ApplicationRecord
    2. Stage 1: Risk assessment (LLM) → RiskAssessment
    3. Stage 2: Onboarding summary (LLM) → OnboardingSummary
    4. Push to Airtable → record URL

Pipeline stages for document intake (--document or --marker-file):
    0. Stage 0: Document → ApplicationRecord
         --document:     raw text → Claude extracts structure and fields in one pass
         --marker-file:  PDF → Marker parses layout/tables/OCR → Claude extracts fields
    1. Stage 1: Risk assessment (LLM) → RiskAssessment
    2. Stage 2: Onboarding summary (LLM) → OnboardingSummary
    3. Push to Airtable → record URL
"""

import argparse
import sys
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import get_anthropic_client, AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID
from models import ApplicationRecord, ProcessedApplication
from risk_assessment import assess_risk
from onboarding_summary import generate_summary
from airtable_client import AirtableClient
from intake_processor import process_document

console = Console()

RISK_COLOURS = {
    "LOW":      "green",
    "MEDIUM":   "yellow",
    "HIGH":     "red",
    "CRITICAL": "bold red",
}


# ── Display helpers ───────────────────────────────────────────────────────────

def print_header(model: str = ""):
    console.print()
    console.print(Panel.fit(
        "[bold white]Crestview Capital Partners[/bold white]\n"
        "[dim]AI-Powered Client Onboarding Pipeline[/dim]\n"
        f"[dim]Airtable  ·  {model}[/dim]",
        border_style="blue",
        padding=(0, 2),
    ))
    console.print()


def print_application_result(result: ProcessedApplication, idx: int, total: int):
    app  = result.application
    risk = result.risk_assessment
    summ = result.onboarding_summary
    col  = RISK_COLOURS.get(risk.risk_level, "white")

    header = (
        f"[bold]{idx}/{total}[/bold]  "
        f"[bold white]{app.company_name}[/bold white]  "
        f"[dim]{app.application_id}[/dim]"
    )
    console.print(Panel(header, border_style=col, padding=(0, 1)))

    console.print(f"  [bold]Stage 1 — Risk Assessment[/bold]")
    console.print(f"  Risk level : [{col}]{risk.risk_level}[/{col}]")
    console.print(f"  Risk score : [{col}]{risk.risk_score}/100[/{col}]")
    console.print(f"  PEP flag   : {'[red]YES[/red]' if risk.pep_flag else '[green]No[/green]'}")
    console.print(f"  SAR flag   : {'[red]YES[/red]' if risk.sar_flag else '[green]No[/green]'}")
    console.print(f"  Factors    :")
    for factor in risk.risk_factors:
        console.print(f"    [dim]•[/dim] {factor}")
    console.print(f"  Reasoning  : [dim]{risk.reasoning}[/dim]")

    console.print()
    console.print(f"  [bold]Stage 2 — Onboarding Summary[/bold]")
    console.print(f"  {summ.summary}")
    console.print()
    console.print(f"  [bold yellow]Action:[/bold yellow] {summ.action_required}")
    if summ.reviewer_notes:
        console.print(f"  [dim]Notes: {summ.reviewer_notes}[/dim]")

    if result.airtable_record_url:
        console.print()
        console.print(f"  [bold]Airtable:[/bold] [link={result.airtable_record_url}]{result.airtable_record_url}[/link]")

    console.print()


def print_intake_extraction(app: ApplicationRecord):
    """Display Stage 0 extracted fields for human review before Stage 1 runs."""
    console.print(Panel(
        f"[bold]Stage 0 — Document Intake[/bold]  [dim]{app.application_id}[/dim]",
        border_style="cyan", padding=(0, 1),
    ))
    console.print(f"  [bold]Company      :[/bold] [white]{app.company_name}[/white]")
    console.print(f"  [bold]Industry     :[/bold] [dim]{app.industry}[/dim]")
    console.print(f"  [bold]AUM (USD)    :[/bold] [white]${app.aum_usd:,.0f}[/white]")
    console.print(f"  [bold]Domicile     :[/bold] [dim]{app.domicile}[/dim]")
    console.print(f"  [bold]Jurisdictions:[/bold] [dim]{app.num_jurisdictions}[/dim]")
    console.print(f"  [bold]Contact      :[/bold] [dim]{app.primary_contact} · {app.contact_role}[/dim]")
    console.print(f"  [bold]Date         :[/bold] [dim]{app.application_date}[/dim]")
    console.print()
    console.print(
        f"  [bold]Ownership      :[/bold] [dim]"
        f"{app.ownership_structure_notes[:140]}"
        f"{'…' if len(app.ownership_structure_notes) > 140 else ''}[/dim]"
    )
    console.print(
        f"  [bold]Source of funds:[/bold] [dim]"
        f"{app.source_of_funds[:140]}"
        f"{'…' if len(app.source_of_funds) > 140 else ''}[/dim]"
    )
    flags = app.additional_flags.strip()
    if flags.lower() not in ("none", "none.", ""):
        console.print()
        console.print("  [bold yellow]⚠  Compliance flags extracted from document:[/bold yellow]")
        for sentence in flags.replace(". ", ".\n").splitlines():
            sentence = sentence.strip().rstrip(".")
            if sentence:
                console.print(f"    [dim]•[/dim] {sentence}")
    console.print()
    console.print("  [dim]─── Proceeding to Stage 1: Risk Assessment ───[/dim]")
    console.print()


def print_summary_table(results: list[ProcessedApplication]):
    table = Table(
        title="Pipeline Summary",
        box=box.ROUNDED,
        border_style="blue",
        show_lines=True,
    )
    table.add_column("ID",      style="dim",  no_wrap=True)
    table.add_column("Company", style="white")
    table.add_column("AUM",     justify="right", style="dim")
    table.add_column("Risk",    justify="center")
    table.add_column("Score",   justify="center", style="dim")
    table.add_column("PEP",     justify="center")
    table.add_column("SAR",     justify="center")
    table.add_column("Action",  style="dim")

    for r in results:
        app  = r.application
        risk = r.risk_assessment
        col  = RISK_COLOURS.get(risk.risk_level, "white")
        table.add_row(
            app.application_id,
            app.company_name,
            f"${app.aum_usd/1_000_000:.1f}M",
            f"[{col}]{risk.risk_level}[/{col}]",
            str(risk.risk_score),
            "[red]Y[/red]" if risk.pep_flag else "[green]N[/green]",
            "[red]Y[/red]" if risk.sar_flag else "[green]N[/green]",
            r.onboarding_summary.action_required[:60] + ("…" if len(r.onboarding_summary.action_required) > 60 else ""),
        )

    console.print(table)


# ── Output file ──────────────────────────────────────────────────────────────

def write_results(results: list[ProcessedApplication], path: str = "results.csv") -> None:
    import csv

    fieldnames = [
        "application_id",
        "company_name",
        "industry",
        "aum_usd",
        "domicile",
        "application_date",
        "risk_level",
        "risk_score",
        "pep_flag",
        "sar_flag",
        "risk_factors",
        "reasoning",
        "recommended_action",
        "summary",
        "action_required",
        "reviewer_notes",
        "airtable_record_url",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "application_id":    r.application.application_id,
                "company_name":      r.application.company_name,
                "industry":          r.application.industry,
                "aum_usd":           r.application.aum_usd,
                "domicile":          r.application.domicile,
                "application_date":  r.application.application_date,
                "risk_level":        r.risk_assessment.risk_level,
                "risk_score":        r.risk_assessment.risk_score,
                "pep_flag":          r.risk_assessment.pep_flag,
                "sar_flag":          r.risk_assessment.sar_flag,
                "risk_factors":      " | ".join(r.risk_assessment.risk_factors),
                "reasoning":         r.risk_assessment.reasoning,
                "recommended_action":r.risk_assessment.recommended_action,
                "summary":           r.onboarding_summary.summary,
                "action_required":   r.onboarding_summary.action_required,
                "reviewer_notes":    r.onboarding_summary.reviewer_notes,
                "airtable_record_url": r.airtable_record_url or "",
            })

    console.print(f"\n[dim]Results written to {path}[/dim]")


# ── Pipeline helpers ──────────────────────────────────────────────────────────

def _get_airtable_client(skip_airtable: bool) -> AirtableClient | None:
    if skip_airtable:
        return None
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        console.print("[yellow]⚠ AIRTABLE_API_KEY or AIRTABLE_BASE_ID not set — skipping Airtable push[/yellow]\n")
        return None
    try:
        console.print("[dim]Connecting to Airtable…[/dim]")
        client = AirtableClient(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        client.setup()
        console.print(f"[green]✓[/green] Airtable ready (base: {AIRTABLE_BASE_ID})\n")
        return client
    except Exception as e:
        console.print(f"[yellow]⚠ Airtable setup failed: {e}[/yellow]")
        console.print("[yellow]  Continuing without Airtable push[/yellow]\n")
        return None


def _push_to_airtable(airtable: AirtableClient | None, result: ProcessedApplication) -> None:
    if not airtable:
        return
    try:
        record_id, record_url = airtable.create_record(result)
        result.airtable_record_id = record_id
        result.airtable_record_url = record_url
    except Exception as e:
        console.print(f"[yellow]  ⚠ Airtable push failed: {e}[/yellow]")


# ── CSV pipeline ──────────────────────────────────────────────────────────────

def run_pipeline(
    csv_path: str = "data/applications.csv",
    filter_id: str | None = None,
    skip_airtable: bool = False,
) -> list[ProcessedApplication]:

    try:
        anthropic_client, model = get_anthropic_client()
    except EnvironmentError as e:
        print_header()
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)

    print_header(model)

    console.print(f"[dim]Loading applications from {csv_path}…[/dim]")
    df = pd.read_csv(csv_path).fillna("")
    if filter_id:
        df = df[df["application_id"] == filter_id]
        if df.empty:
            console.print(f"[red]No application found with ID: {filter_id}[/red]")
            sys.exit(1)

    if "client_name" in df.columns:
        df = df.rename(columns={
            "client_name":     "company_name",
            "client_type":     "industry",
            "estimated_aum":   "aum_usd",
            "submission_date": "application_date",
        })
        df["application_date"]          = pd.to_datetime(df["application_date"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
        df["primary_contact"]           = df.get("primary_contact",           "Not stated")
        df["contact_role"]              = df.get("contact_role",              "Not stated")
        df["domicile"]                  = df.get("domicile",                  "Not stated")
        df["num_jurisdictions"]         = df.get("num_jurisdictions",         1)
        df["ownership_structure_notes"] = df.get("description",               "Not stated")
        df["beneficial_owners"]         = df.get("beneficial_owners",         "Not stated")
        df["source_of_funds"]           = df.get("source_of_funds",           "Not stated")
        df["regulatory_history"]        = df.get("regulatory_history",        "Not stated")
        df["additional_flags"]          = df.get("description",               "Not stated")

    applications = [ApplicationRecord(**row) for row in df.to_dict("records")]
    console.print(f"[green]✓[/green] {len(applications)} application(s) loaded\n")
    console.print(f"[green]✓[/green] Anthropic ready (model: {model})\n")

    airtable = _get_airtable_client(skip_airtable)

    if airtable:
        before = len(applications)
        applications = [
            app for app in applications
            if not airtable.find_existing(app.application_id)
        ]
        skipped = before - len(applications)
        if skipped:
            console.print(
                f"[yellow]⟳ {skipped} application(s) already in Airtable — skipping[/yellow]\n"
            )
        if not applications:
            console.print("[green]✓ All applications already processed. Nothing to do.[/green]")
            return []

    results: list[ProcessedApplication] = []

    for idx, app in enumerate(applications, 1):
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[dim]Processing {app.application_id}: {app.company_name}…"),
            transient=True,
            console=console,
        ) as progress:
            progress.add_task("", total=None)

            try:
                risk = assess_risk(app, anthropic_client, model)
            except ValueError as e:
                console.print(f"[red]✗ Stage 1 failed for {app.application_id}: {e}[/red]")
                continue

            try:
                summary = generate_summary(app, risk, anthropic_client, model)
            except ValueError as e:
                console.print(f"[red]✗ Stage 2 failed for {app.application_id}: {e}[/red]")
                continue

            result = ProcessedApplication(
                application=app,
                risk_assessment=risk,
                onboarding_summary=summary,
            )
            _push_to_airtable(airtable, result)

        results.append(result)
        print_application_result(result, idx, len(applications))

    if results:
        print_summary_table(results)
        write_results(results)

        high_risk = [r for r in results if r.risk_assessment.risk_level in ("HIGH", "CRITICAL")]
        pep_count = sum(1 for r in results if r.risk_assessment.pep_flag)
        sar_count = sum(1 for r in results if r.risk_assessment.sar_flag)

        console.print()
        console.print(Panel(
            f"[bold]Batch complete[/bold]  —  {len(results)} applications processed\n"
            f"High/Critical risk: [red]{len(high_risk)}[/red]  |  "
            f"PEP flags: [red]{pep_count}[/red]  |  "
            f"SAR indicators: [red]{sar_count}[/red]",
            border_style="green" if not high_risk else "red",
            padding=(0, 2),
        ))

    return results


# ── Document pipeline ─────────────────────────────────────────────────────────

def run_document_pipeline(
    doc_path: str,
    skip_airtable: bool = False,
) -> ProcessedApplication | None:
    try:
        anthropic_client, model = get_anthropic_client()
    except EnvironmentError as e:
        print_header()
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)

    print_header(model)

    try:
        with open(doc_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
    except FileNotFoundError:
        console.print(f"[red]✗ Document not found: {doc_path}[/red]")
        sys.exit(1)

    console.print(f"[dim]Document: {doc_path}  ({len(raw_text):,} chars)[/dim]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[dim]Stage 0 — extracting structured fields from unstructured text…"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        try:
            app = process_document(raw_text, anthropic_client, model, source_label=doc_path)
        except ValueError as e:
            console.print(f"[red]✗ Stage 0 (document intake) failed: {e}[/red]")
            return None

    console.print(f"[green]✓[/green] Stage 0 complete\n")
    print_intake_extraction(app)

    airtable = _get_airtable_client(skip_airtable)

    with Progress(
        SpinnerColumn(),
        TextColumn(f"[dim]Stages 1 + 2: {app.company_name}…"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("", total=None)

        try:
            risk = assess_risk(app, anthropic_client, model)
        except ValueError as e:
            console.print(f"[red]✗ Stage 1 failed: {e}[/red]")
            return None

        try:
            summary = generate_summary(app, risk, anthropic_client, model)
        except ValueError as e:
            console.print(f"[red]✗ Stage 2 failed: {e}[/red]")
            return None

    result = ProcessedApplication(
        application=app,
        risk_assessment=risk,
        onboarding_summary=summary,
    )
    _push_to_airtable(airtable, result)

    print_application_result(result, 1, 1)
    write_results([result], "results_document.csv")
    return result


# ── Marker PDF pipeline ───────────────────────────────────────────────────────

def run_marker_pipeline(
    pdf_path: str,
    skip_airtable: bool = False,
) -> ProcessedApplication | None:
    try:
        anthropic_client, model = get_anthropic_client()
    except EnvironmentError as e:
        print_header()
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)

    print_header(model)

    console.print(Panel(
        "[bold cyan]Stage 0 — Marker Edition[/bold cyan]\n"
        "[dim]PDF → Marker (layout + OCR + tables) → clean markdown → Claude (field extraction)[/dim]",
        border_style="cyan", padding=(0, 2),
    ))
    console.print()

    from marker_intake import process_pdf

    console.print(f"[dim]PDF: {pdf_path}[/dim]")
    try:
        app = process_pdf(pdf_path, anthropic_client, model)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        return None
    except ValueError as e:
        console.print(f"[red]✗ Stage 0 (Marker) failed: {e}[/red]")
        return None

    console.print(f"[green]✓[/green] Stage 0 (Marker) complete\n")
    print_intake_extraction(app)

    airtable = _get_airtable_client(skip_airtable)

    with Progress(
        SpinnerColumn(),
        TextColumn(f"[dim]Stages 1 + 2: {app.company_name}…"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("", total=None)

        try:
            risk = assess_risk(app, anthropic_client, model)
        except ValueError as e:
            console.print(f"[red]✗ Stage 1 failed: {e}[/red]")
            return None

        try:
            summary = generate_summary(app, risk, anthropic_client, model)
        except ValueError as e:
            console.print(f"[red]✗ Stage 2 failed: {e}[/red]")
            return None

    result = ProcessedApplication(
        application=app,
        risk_assessment=risk,
        onboarding_summary=summary,
    )
    _push_to_airtable(airtable, result)

    print_application_result(result, 1, 1)
    write_results([result], "results_marker.csv")
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crestview Client Onboarding Pipeline")
    parser.add_argument("--app",            help="Process a single application by ID (e.g. APP-0303)")
    parser.add_argument("--csv",            default="data/applications.csv", help="Path to applications CSV")
    parser.add_argument("--document",       help="Process a single unstructured document (email, text, memo)")
    parser.add_argument("--marker-file",    help="Process a PDF using Marker for document parsing (Stage 0 Marker edition)")
    parser.add_argument("--skip-airtable",  action="store_true", help="Skip Airtable push")
    args = parser.parse_args()

    if args.marker_file:
        run_marker_pipeline(
            pdf_path=args.marker_file,
            skip_airtable=args.skip_airtable,
        )
    elif args.document:
        run_document_pipeline(
            doc_path=args.document,
            skip_airtable=args.skip_airtable,
        )
    else:
        run_pipeline(
            csv_path=args.csv,
            filter_id=args.app,
            skip_airtable=args.skip_airtable,
        )
