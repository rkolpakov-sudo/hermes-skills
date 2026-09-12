"""Smeta PDF generator using fpdf2 with Cyrillic support."""
import os

# Font paths — auto-detect OS
WIN_ARIAL = r"C:\Windows\Fonts\arial.ttf"
LINUX_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def _get_font():
    if os.path.exists(WIN_ARIAL):
        return WIN_ARIAL
    elif os.path.exists(LINUX_FONT):
        return LINUX_FONT
    for path in ["/usr/share/fonts/TTF/DejaVuSans.ttf", "/System/Library/Fonts/Arial.ttf"]:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("No Cyrillic-capable font found. Install DejaVu or Arial.")


def create_smeta_report(
    title: str = "Сметная ведомость",
    project_name: str = "",
    items: list = None,
    output_path: str = "/tmp/smeta.pdf",
):
    """Generate a сметная ведомость PDF.
    
    Args:
        title: Document title
        project_name: Project/object name
        items: List of dicts with keys: code, description, unit, quantity, rate, amount
        output_path: Where to save the PDF
    
    Returns:
        Path to generated PDF file
    """
    from fpdf import FPDF

    if items is None:
        items = []

    font_path = _get_font()
    
    class SmetaPDF(FPDF):
        def __init__(self, title_text, project_name_text):
            super().__init__()
            self._title = title_text
            self._project_name = project_name_text
            
            # Register Cyrillic font BEFORE adding pages
            FONT_FAMILY = "Cyrillic"
            self.add_font(FONT_FAMILY, "", font_path, uni=True)
            self.add_font(FONT_FAMILY, "B", font_path, uni=True)
            
        def header(self):
            self.set_font("Cyrillic", "B", 14)
            self.cell(0, 10, self._title, new_x="LMARGIN", new_y="NEXT")
            if self._project_name:
                self.set_font("Cyrillic", "", 11)
                self.cell(0, 8, f"Объект: {self._project_name}", new_x="LMARGIN", new_y="NEXT")
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font("Cyrillic", "", 8)
            self.cell(0, 10, f"Страница {self.page_no()}/{{nb}}", align="C")

    pdf = SmetaPDF(title, project_name)
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Table header
    col_widths = [25, 100, 18, 22, 22, 25]
    headers = ["№ п/п", "Наименование работ (ГЭСН)", "Ед.\nизм.", "Кол-во", "Цена\nед.", "Сумма,\nруб."]
    
    pdf.set_font("Cyrillic", "B", 9)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 14, h, border=1, align="C")
    pdf.ln()
    
    # Table rows
    total = 0
    pdf.set_font("Cyrillic", "", 9)
    for idx, item in enumerate(items, 1):
        row = [
            str(idx),
            item.get("code", "") + " " + item.get("description", ""),
            item.get("unit", ""),
            f"{item.get('quantity', 0):.2f}",
            f"{item.get('rate', 0):,.2f}",
            f"{item.get('amount', 0):,.2f}",
        ]
        for i, val in enumerate(row):
            pdf.cell(col_widths[i], 10, val, border=1, align="R" if i >= 3 else "L")
        total += item.get("amount", 0)
        pdf.ln()
    
    # Summary
    pdf.set_font("Cyrillic", "B", 9)
    pdf.cell(25 + 100 + 18 + 22, 10, "", border=1)
    pdf.cell(22, 10, "ИТОГО:", border=1, align="R")
    pdf.cell(25, 10, f"{total:,.2f}", border=1, align="R")
    pdf.ln()
    
    # НДС (if needed)
    nds = total * 0.2 if total > 0 else 0
    grand_total = total + nds
    
    if nds > 0:
        pdf.cell(25 + 100 + 18 + 22, 10, "", border=1)
        pdf.cell(22, 10, "НДС (20%)", border=1, align="R")
        pdf.cell(25, 10, f"{nds:,.2f}", border=1, align="R")
        pdf.ln()
    
    if total > 0:
        pdf.set_font("Cyrillic", "B", 9)
        pdf.cell(25 + 100 + 18 + 22, 10, "", border=1)
        pdf.cell(22, 10, "Всего с НДС:", border=1, align="R")
        pdf.cell(25, 10, f"{grand_total:,.2f}", border=1, align="R")
    
    # Save
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    pdf.output(output_path)
    return output_path


def create_akt_report(
    contract_number: str = "",
    date_from: str = "",
    date_to: str = "",
    items: list = None,
    output_path: str = "/tmp/akt.pdf",
):
    """Generate an акт выполненных работ PDF.
    
    Args:
        contract_number: Contract/dogovor number
        date_from: Start date (DD.MM.YYYY)
        date_to: End date (DD.MM.YYYY)
        items: List of dicts with keys: description, quantity, unit, amount
        output_path: Where to save the PDF
    
    Returns:
        Path to generated PDF file
    """
    from fpdf import FPDF

    if items is None:
        items = []

    font_path = _get_font()
    
    class AktPDF(FPDF):
        def __init__(self, contract_num, df, dt):
            super().__init__()
            self._contract_number = contract_num
            self._date_from = df
            self._date_to = dt
            
            FONT_FAMILY = "Cyrillic"
            self.add_font(FONT_FAMILY, "", font_path, uni=True)
            self.add_font(FONT_FAMILY, "B", font_path, uni=True)
            
        def header(self):
            self.set_font("Cyrillic", "B", 16)
            self.cell(0, 12, "АКТ ВЫПОЛНЕННЫХ РАБОТ", new_x="LMARGIN", new_y="NEXT")
            if self._contract_number:
                self.set_font("Cyrillic", "", 11)
                self.cell(0, 8, f"по Договору № {self._contract_number}", new_x="LMARGIN", new_y="NEXT")
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font("Cyrillic", "", 8)
            self.cell(0, 10, f"Страница {self.page_no()}/{{nb}}", align="C")

    pdf = AktPDF(contract_number, date_from, date_to)
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Period info — write directly since header already ran
    period_parts = list(filter(None, [date_from, "по", date_to]))
    if period_parts:
        pdf.set_font("Cyrillic", "", 11)
        pdf.cell(0, 8, f"Период: {' '.join(period_parts)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Table header
    col_widths = [10, 130, 22, 18, 25]
    headers = ["№", "Наименование работ", "Кол-во", "Ед.изм.", "Сумма"]
    
    pdf.set_font("Cyrillic", "B", 9)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 10, h, border=1, align="C")
    pdf.ln()
    
    total = 0
    pdf.set_font("Cyrillic", "", 9)
    for idx, item in enumerate(items, 1):
        row = [
            str(idx),
            item.get("description", ""),
            f"{item.get('quantity', 0):.2f}",
            item.get("unit", ""),
            f"{item.get('amount', 0):,.2f}",
        ]
        for i, val in enumerate(row):
            pdf.cell(col_widths[i], 8, val, border=1, align="R" if i >= 2 else "L")
        total += item.get("amount", 0)
        pdf.ln()
    
    # Total row
    pdf.set_font("Cyrillic", "B", 9)
    pdf.cell(10 + 130 + 22 + 18, 10, "", border=1)
    pdf.cell(25, 10, f"{total:,.2f}", border=1, align="R")
    
    # Signatures section
    pdf.ln(20)
    pdf.set_font("Cyrillic", "B", 11)
    pdf.cell(0, 10, "Подписи:", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Cyrillic", "", 10)
    pdf.cell(90, 8, "Исполнитель: ________________ /______________/", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(90, 8, "Заказчик: ________________ /______________/", align="R")
    
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    pdf.output(output_path)
    return output_path


def create_specification_report(
    title: str = "Спецификация материалов",
    items: list = None,
    output_path: str = "/tmp/spec.pdf",
):
    """Generate a спецификация материалов PDF.
    
    Args:
        title: Document title
        items: List of dicts with keys: code, description, unit, quantity, price, amount
        output_path: Where to save the PDF
    
    Returns:
        Path to generated PDF file
    """
    from fpdf import FPDF

    if items is None:
        items = []

    font_path = _get_font()
    
    class SpecPDF(FPDF):
        def __init__(self, title_text):
            super().__init__()
            self._title = title_text
            
            FONT_FAMILY = "Cyrillic"
            self.add_font(FONT_FAMILY, "", font_path, uni=True)
            self.add_font(FONT_FAMILY, "B", font_path, uni=True)
            
        def header(self):
            self.set_font("Cyrillic", "B", 14)
            self.cell(0, 10, self._title, new_x="LMARGIN", new_y="NEXT")
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font("Cyrillic", "", 8)
            self.cell(0, 10, f"Страница {self.page_no()}/{{nb}}", align="C")

    pdf = SpecPDF(title)
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Table header
    col_widths = [25, 90, 18, 20, 22, 25]
    headers = ["Код\nматериала", "Наименование материала", "Ед.\nизм.", "Кол-во", "Цена\nза ед.", "Сумма,\nруб."]
    
    pdf.set_font("Cyrillic", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 14, h, border=1, align="C")
    pdf.ln()
    
    total = 0
    pdf.set_font("Cyrillic", "", 9)
    for idx, item in enumerate(items, 1):
        row = [
            item.get("code", ""),
            item.get("description", ""),
            item.get("unit", ""),
            f"{item.get('quantity', 0):.2f}",
            f"{item.get('price', 0):,.2f}",
            f"{item.get('amount', 0):,.2f}",
        ]
        for i, val in enumerate(row):
            pdf.cell(col_widths[i], 8, val, border=1, align="R" if i >= 3 else "L")
        total += item.get("amount", 0)
        pdf.ln()
    
    # Total row
    pdf.set_font("Cyrillic", "B", 9)
    pdf.cell(25 + 90 + 18 + 20, 10, "", border=1)
    pdf.cell(22, 10, "ИТОГО:", border=1, align="R")
    pdf.cell(25, 10, f"{total:,.2f}", border=1, align="R")
    
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    pdf.output(output_path)
    return output_path


if __name__ == "__main__":
    import tempfile
    
    tmpdir = tempfile.gettempdir()
    
    demo_items = [
        {"code": "ГЭСН 01.01.001-01", "description": "Земляные работы ручные, плотность грунта I", "unit": "м³", "quantity": 150.0, "rate": 850.50, "amount": 127575.00},
        {"code": "ГЭСН 04.01.003-01", "description": "Устройство бетонной подготовки из бетона В15", "unit": "м³", "quantity": 45.0, "rate": 4200.00, "amount": 189000.00},
        {"code": "ГЭСН 06.03.012-01", "description": "Монтаж стальных колонн массой до 5 т", "unit": "т", "quantity": 12.5, "rate": 8500.00, "amount": 106250.00},
    ]
    
    out = create_smeta_report(
        title="Сметная ведомость на строительные работы",
        project_name="ЖК Северный, очередь I",
        items=demo_items,
        output_path=os.path.join(tmpdir, "demo_smeta.pdf"),
    )
    print(f"✓ Demo сметная ведомость: {out} ({os.path.getsize(out)} bytes)")
