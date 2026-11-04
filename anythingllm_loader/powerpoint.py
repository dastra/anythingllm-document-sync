import pathlib
import tempfile
from contextlib import contextmanager


def _shape_text(shape):
    """Extract text from a shape, including tables and grouped shapes."""
    if getattr(shape, "has_table", False):
        return "\n".join(
            " | ".join(cell.text.strip() for cell in row.cells)
            for row in shape.table.rows
        ).strip()

    if getattr(shape, "has_text_frame", False):
        return shape.text.strip()

    if hasattr(shape, "shapes"):
        return "\n".join(
            text for child in shape.shapes
            if (text := _shape_text(child))
        ).strip()

    return ""


def extract_pptx_to_markdown(source_path: str, output_path: str) -> bool:
    """Write slide text and speaker notes to Markdown without modifying the PPTX."""
    from pptx import Presentation

    source = pathlib.Path(source_path).absolute()
    presentation = Presentation(str(source))
    sections = [f"# {source.stem}", "", f"Source file: `{source}`", ""]
    extracted_content = False

    for slide_number, slide in enumerate(presentation.slides, start=1):
        sections.extend([f"## Slide {slide_number}", ""])
        slide_text = [
            text for shape in slide.shapes
            if (text := _shape_text(shape))
        ]
        if slide_text:
            extracted_content = True
            sections.extend(["\n\n".join(slide_text), ""])

        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                extracted_content = True
                sections.extend(["### Speaker notes", "", notes, ""])

    if not extracted_content:
        return False

    pathlib.Path(output_path).write_text("\n".join(sections), encoding="utf-8")
    return True


@contextmanager
def temporary_upload_path(source_path: str):
    """Yield an uploadable path, cleaning up PPTX-derived Markdown afterward."""
    source = pathlib.Path(source_path)
    if source.suffix.lower() != ".pptx":
        yield str(source)
        return

    with tempfile.TemporaryDirectory(prefix="anythingllm-pptx-") as temporary_directory:
        temporary_path = pathlib.Path(temporary_directory) / f"{source.stem}.md"
        if not extract_pptx_to_markdown(str(source), str(temporary_path)):
            raise ValueError(f"No text content found in PowerPoint: {source}")
        yield str(temporary_path)
