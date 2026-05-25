# main.py
"""
Drawing QA Agent CLI.
Compares reference drawings (from Input_PDFs) against review drawings (from Creo_PDFs)
using spatial text-matching and OpenCV pixel diffing.
Generates interactive HTML and JSON reports.
"""

import click
import os
import json
import io
from pathlib import Path
from PIL import Image
from core.pdf_utils import pdf_to_images, extract_pdf_text_elements, extract_pdf_drawings
from core.image_utils import create_comparison_image
from core.qa_agent import analyze_page, CATEGORIES_LIST
from core.report import generate_report
from config import (
    PDF_DPI,
    OUTPUT_DIR,
    COMPARISONS_DIR,
    REPORT_HTML_PATH,
    REPORT_JSON_PATH,
    SAVE_COMPARISON_IMAGES
)
from rich.console import Console
from tqdm import tqdm

console = Console()

def sanitize_filename(name: str) -> str:
    """Sanitizes filename for use in output paths."""
    return "".join(c for c in name if c.isalnum() or c in (".", "_", "-")).rstrip()

@click.command()
@click.option("--ref", default="Input_PDFs", help="Path to reference PDF or directory (SolidWorks/SolidEdge)")
@click.option("--review", default="Creo_PDFs", help="Path to review PDF or directory (Creo)")
@click.option("--dpi", default=PDF_DPI, type=int, help="Rendering DPI")
@click.option("--out", default=OUTPUT_DIR, help="Output folder")
def main(ref, review, dpi, out):
    """
    Engineering Drawing QA Agent
    Compares Creo PDFs against SolidWorks/SolidEdge reference PDFs
    without using any LLM/cloud APIs. Runs purely locally using PDF parsing & OpenCV.
    """
    os.makedirs(out, exist_ok=True)
    os.makedirs(os.path.join(out, "comparisons"), exist_ok=True)

    console.print("[bold indigo]Drawing QA Agent (Code-Based)[/bold indigo]")
    console.print(f"  Reference Source : {ref}")
    console.print(f"  Review Target    : {review}")
    console.print(f"  DPI Setting      : {dpi}\n")

    ref_path = Path(ref)
    review_path = Path(review)

    # 1. Establish matched pairs of PDFs
    pairs = []
    if ref_path.is_dir() and review_path.is_dir():
        ref_files = list(ref_path.glob("*.pdf"))
        for rf in ref_files:
            rev_f = review_path / rf.name
            if rev_f.exists():
                pairs.append((rf, rev_f))
            else:
                console.print(f"[yellow]Warning: No matching review PDF found for '{rf.name}'[/yellow]")
    else:
        if not ref_path.exists() or not review_path.exists():
            console.print(f"[red]Error: Reference path '{ref}' or review path '{review}' does not exist.[/red]")
            return
        # If it's single files
        pairs.append((ref_path, review_path))

    if not pairs:
        console.print("[red]Error: No PDF files to compare.[/red]")
        return

    console.print(f"[cyan]Found {len(pairs)} file pair(s) to analyze...[/cyan]")
    all_results = []

    # 2. Iterate through each PDF pair
    for ref_file, review_file in pairs:
        filename = review_file.name
        console.print(f"\n[bold]Comparing: {ref_file.name} vs {filename}[/bold]")
        
        # Load and render reference PDF
        console.print("  Rendering reference pages...")
        ref_images = pdf_to_images(str(ref_file), dpi=dpi)
        ref_text_pages = extract_pdf_text_elements(str(ref_file))

        # Load and render review PDF
        console.print("  Rendering review pages...")
        review_images = pdf_to_images(str(review_file), dpi=dpi)
        review_text_pages = extract_pdf_text_elements(str(review_file))
        review_drawings_pages = extract_pdf_drawings(str(review_file))

        import fitz
        doc_ref = fitz.open(str(ref_file))
        doc_review = fitz.open(str(review_file))
        
        ref_sizes = [(page.rect.width, page.rect.height) for page in doc_ref]
        review_sizes = [(page.rect.width, page.rect.height) for page in doc_review]
        
        doc_ref.close()
        doc_review.close()

        page_count = min(len(ref_images), len(review_images))
        if len(ref_images) != len(review_images):
            console.print(f"  [yellow]Page count mismatch: Reference has {len(ref_images)} pages, review has {len(review_images)} pages. Comparing the first {page_count} page(s).[/yellow]")

        annotated_pages_images = []
        document_pages_results = []

        for page_idx in tqdm(range(page_count), desc=f"  Analyzing {filename}"):
            ref_img_bytes = ref_images[page_idx]
            review_img_bytes = review_images[page_idx]

            ref_text = ref_text_pages[page_idx]
            review_text = review_text_pages[page_idx]
            review_drawings = review_drawings_pages[page_idx]

            ref_size = ref_sizes[page_idx]
            review_size = review_sizes[page_idx]

            # Run analytical rules and visual diffs
            page_result = analyze_page(
                ref_img_bytes,
                review_img_bytes,
                ref_text,
                review_text,
                ref_size,
                review_size,
                page_idx + 1,
                review_drawings=review_drawings,
                dpi=dpi
            )

            # Draw annotations and save comparison image if requested
            if SAVE_COMPARISON_IMAGES:
                # Unique name for the output image based on Creo review PDF
                safe_name = sanitize_filename(review_file.stem)
                img_filename = f"{safe_name}_page_{page_idx + 1}.png"
                save_path = os.path.join(out, "comparisons", img_filename)

                annotated_img_bytes = create_comparison_image(
                    ref_img_bytes,
                    review_img_bytes,
                    page_result["issues"],
                    ref_size,
                    review_size,
                    label_suffix=f" — Page {page_idx + 1}"
                )

                try:
                    if os.path.exists(save_path):
                        os.remove(save_path)
                except Exception:
                    pass

                try:
                    with open(save_path, "wb") as f:
                        f.write(annotated_img_bytes)
                except OSError:
                    import time
                    time.sleep(0.5)
                    try:
                        with open(save_path, "wb") as f:
                            f.write(annotated_img_bytes)
                    except Exception as e2:
                        console.print(f"[yellow]Warning: Could not write comparison image {img_filename}: {e2}[/yellow]")

                # Keep for composite PDF export
                pil_img = Image.open(io.BytesIO(annotated_img_bytes))
                annotated_pages_images.append(pil_img)

                # Store absolute or relative path for report rendering
                page_result["comparison_image"] = save_path

            # Adjust page label for the multi-file list
            page_result["page"] = f"{filename} (Page {page_idx + 1})"
            all_results.append(page_result)
            document_pages_results.append(page_result)

            # CLI output for feedback
            _print_page_summary(page_result)

        # Save composite PDF containing all pages for this document pair
        if annotated_pages_images:
            pdf_save_path = os.path.join(out, "comparisons", f"{safe_name}.pdf")
            try:
                if os.path.exists(pdf_save_path):
                    os.remove(pdf_save_path)
            except Exception:
                pass

            try:
                annotated_pages_images[0].save(
                    pdf_save_path,
                    save_all=True,
                    append_images=annotated_pages_images[1:]
                )
                console.print(f"  Saved composite PDF at: {pdf_save_path}")
            except Exception:
                import time
                time.sleep(0.5)
                try:
                    annotated_pages_images[0].save(
                        pdf_save_path,
                        save_all=True,
                        append_images=annotated_pages_images[1:]
                    )
                    console.print(f"  Saved composite PDF at: {pdf_save_path}")
                except Exception as e2:
                    console.print(f"[red]Error: Could not save composite PDF {pdf_save_path}: {e2}[/red]")

        # Save individual JSON report file for this drawing comparison
        if document_pages_results:
            doc_has_issues = any(pr["page_has_issues"] for pr in document_pages_results)
            doc_status = "FAIL" if doc_has_issues else "PASS"

            doc_total_checks = sum(pr["summary_counts"]["total_checks"] for pr in document_pages_results)
            doc_failed_checks = sum(pr["summary_counts"]["failed"] for pr in document_pages_results)
            doc_passed_checks = doc_total_checks - doc_failed_checks

            doc_categories = {name: [] for name in CATEGORIES_LIST}
            for pr in document_pages_results:
                for cat in pr["categories_report"]:
                    if cat["status"] == "FAIL":
                        doc_categories[cat["name"]].extend(cat["issues"])

            categories_list_json = []
            for cat_name in CATEGORIES_LIST:
                cat_issues = doc_categories[cat_name]
                categories_list_json.append({
                    "name": cat_name,
                    "status": "FAIL" if len(cat_issues) > 0 else "PASS",
                    "issues": cat_issues
                })

            doc_report = {
                "drawing_id": review_file.stem,
                "status": doc_status,
                "summary": {
                    "total_checks": doc_total_checks,
                    "passed": doc_passed_checks,
                    "failed": doc_failed_checks
                },
                "categories": categories_list_json,
                "pages": [
                    {
                        "page_num": pr["page"],
                        "status": pr["status"],
                        "summary": pr["summary_counts"],
                        "categories": pr["categories_report"]
                    } for pr in document_pages_results
                ]
            }

            json_save_path = os.path.join(out, "comparisons", f"{safe_name}.json")
            try:
                if os.path.exists(json_save_path):
                    os.remove(json_save_path)
            except Exception:
                pass

            try:
                with open(json_save_path, "w") as f:
                    json.dump(doc_report, f, indent=2)
                console.print(f"  Saved comparison JSON report at: {json_save_path}")
            except Exception as e:
                console.print(f"[red]Error: Could not save JSON report {json_save_path}: {e}[/red]")

    # 3. Write structured outputs
    report_json_file = os.path.join(out, "report.json")
    with open(report_json_file, "w") as f:
        json.dump(all_results, f, indent=2)

    report_html_file = os.path.join(out, "report.html")
    generate_report(all_results, output_path=report_html_file)

    console.print(f"\n[bold green]Success! Report generated at: {report_html_file}[/bold green]")

def _print_page_summary(result: dict):
    """Print issues summary on the terminal."""
    issues = result.get("issues", [])
    if result.get("page_has_issues"):
        console.print(f"    [red]Warning: {len(issues)} issue(s) identified[/red]")
        for idx, issue in enumerate(issues, start=1):
            sev = issue.get("severity")
            color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "blue"}.get(sev, "white")
            console.print(f"      [bold {color}]#{idx} [{sev}] {issue.get('type')}[/bold {color}] - {issue.get('location')}")
    else:
        console.print("    [green]Pages match perfectly[/green]")

if __name__ == "__main__":
    main()
