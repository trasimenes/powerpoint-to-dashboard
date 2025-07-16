from pptx import Presentation


def parse_slide_text(slide):
    texts = []
    for shape in slide.shapes:
        if hasattr(shape, "text"):
            text = shape.text.strip()
            if text:
                texts.append(text)
    return texts


def parse_table(slide):
    for shape in slide.shapes:
        if shape.has_table:
            table = shape.table
            headers = [cell.text.strip() for cell in table.rows[0].cells]
            rows = []
            for row in table.rows[1:]:
                rows.append([cell.text.strip() for cell in row.cells])
            return {"headers": headers, "rows": rows}
    return {"headers": [], "rows": []}


def extract_pptx(path, slide_start, slide_end):
    prs = Presentation(path)
    slides = prs.slides
    if slide_start - 1 >= len(slides) or slide_end - 1 >= len(slides):
        raise ValueError("Slide range out of bounds")
    kpi_slide = slides[slide_start - 1]
    table_slide = slides[slide_end - 1]
    kpis = parse_slide_text(kpi_slide)
    table = parse_table(table_slide)
    return kpis, table
