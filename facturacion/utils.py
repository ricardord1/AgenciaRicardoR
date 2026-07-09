import re
import io
import pypdf
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# ---------------------------------------------------------
# LÓGICA DE EXTRACCIÓN DE PDF (OCR CONCEPTUAL)
# ---------------------------------------------------------
def extraer_texto_pdf(file_obj):
    """
    Lee un archivo PDF en memoria y extrae su contenido de texto.
    """
    try:
        reader = pypdf.PdfReader(file_obj)
        full_text = []
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                full_text.append(text)
        return "\n".join(full_text)
    except Exception as e:
        return f"Error leyendo PDF: {str(e)}"

def estructurar_texto_factura(text):
    """
    Analiza el texto plano de un PDF y busca patrones comunes (Totales, Números de factura, Fechas)
    para devolver una estructura JSON que el frontend pueda consumir.
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Expresión regular para montos numéricos comunes ($1,250.00, 420.50, etc.)
    regex_amounts = r'\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b'
    all_amounts = re.findall(regex_amounts, text)
    
    potential_totals = []
    potential_invoice_nums = []
    potential_dates = []
    
    for line in lines:
        lower_line = line.lower()
        
        # 1. Identificar posibles líneas de totales/subtotales
        if any(term in lower_line for term in ['total', 'monto', 'subtotal', 'neto', 'pagar', 'sum', 'balance']):
            amounts = re.findall(regex_amounts, line)
            if amounts:
                potential_totals.append({
                    "linea_completa": line,
                    "valores_detectados": amounts
                })
        
        # 2. Identificar posibles números de factura / DUA
        if any(term in lower_line for term in ['factura', 'invoice', 'no.', 'num', 'doc', 'n°', 'dua', 'referencia']):
            # Busca códigos alfanuméricos sospechosos
            codes = re.findall(r'\b[A-Za-z0-9-]{4,15}\b', line)
            # Descartar términos comunes que no son códigos
            filtered_codes = [c for c in codes if c.lower() not in ['factura', 'invoice', 'fecha', 'monto', 'total']]
            if filtered_codes:
                potential_invoice_nums.append({
                    "linea_completa": line,
                    "codigos_detectados": filtered_codes
                })
                
        # 3. Identificar posibles fechas
        # Formatos DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, etc.
        dates = re.findall(r'\b\d{2}[-/]\d{2}[-/]\d{2,4}\b|\b\d{4}[-/]\d{2}[-/]\d{2}\b', line)
        if dates:
            potential_dates.append({
                "linea_completa": line,
                "fechas_detectadas": dates
            })
            
    return {
        "raw_text": text,
        "lineas": lines,
        "sugerencias": {
            "totales": potential_totals[:6],
            "numeros_factura_o_dua": potential_invoice_nums[:6],
            "fechas": potential_dates[:6],
            "todos_los_montos": list(set(all_amounts))[:15]
        }
    }


# ---------------------------------------------------------
# GENERACIÓN DE PDF PROFESIONAL CON REPORTLAB
# ---------------------------------------------------------
def generar_pdf_factura(factura):
    """
    Genera un archivo PDF para la factura provista utilizando ReportLab.
    Retorna un buffer de Bytes (io.BytesIO) listo para descarga.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        rightMargin=40, 
        leftMargin=40, 
        topMargin=40, 
        bottomMargin=40
    )
    
    story = []
    
    # Paleta de colores corporativos
    navy_dark = colors.HexColor("#0f172a") # Slate 900
    navy_light = colors.HexColor("#1e293b") # Slate 800
    grey_bg = colors.HexColor("#f8fafc") # Slate 50
    blue_accent = colors.HexColor("#2563eb") # Blue 600
    text_dark = colors.HexColor("#334155")
    
    styles = getSampleStyleSheet()
    
    # Estilos de Párrafo Personalizados
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        textColor=navy_dark,
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=blue_accent,
        spaceAfter=15,
        textTransform='uppercase'
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=text_dark,
        leading=13
    )

    bold_body_style = ParagraphStyle(
        'DocBodyBold',
        parent=body_style,
        fontName='Helvetica-Bold'
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white,
        alignment=0
    )

    # 1. CABECERA CON GRID
    header_data = [
        [
            Paragraph("<b>AGENCIA DE ADUANAS S.A.</b><br/>Servicios de Desaduanamiento y Logística<br/>Calle 100 #15-32, Bogotá, Colombia<br/>NIT: 800.192.482-1", body_style),
            Paragraph(f"<font color='{blue_accent.hexval()}'><b>FACTURA DE SERVICIO</b></font><br/><b>N°:</b> {factura.numero_factura}<br/><b>NCF:</b> {factura.ncf_asignado or 'N/A'}<br/><b>Fecha:</b> {factura.fecha_emision.strftime('%d/%m/%Y %H:%M')}", body_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[3.25 * inch, 4.0 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 20))
    
    # 2. SECCIÓN CLIENTE
    cliente = factura.cliente
    cliente_data = [
        [
            Paragraph(f"<b>CLIENTE / IMPORTADOR:</b><br/><b>Nombre:</b> {cliente.nombre}<br/><b>Código:</b> {cliente.codigo_cliente}<br/><b>Teléfono:</b> {cliente.telefono}<br/><b>Email:</b> {cliente.email}", body_style),
            Paragraph(f"<b>DETALLE DE FACTURACIÓN:</b><br/><b>Estado:</b> {factura.estado}<br/><b>Tasa de Cambio (TRM):</b> ${factura.tasa_cambio:,.2f} COP<br/><b>Moneda:</b> USD", body_style)
        ]
    ]
    cliente_table = Table(cliente_data, colWidths=[3.62 * inch, 3.62 * inch])
    cliente_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), grey_bg),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 12),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#e2e8f0")),
    ]))
    story.append(cliente_table)
    story.append(Spacer(1, 20))
    
    # 3. TABLA DE DETALLES
    table_data = [
        [
            Paragraph("Concepto / Servicio Aduanero", table_header_style),
            Paragraph("Cant.", table_header_style),
            Paragraph("Precio Unitario (USD)", table_header_style),
            Paragraph("Subtotal (USD)", table_header_style)
        ]
    ]
    
    for det in factura.detalles.all():
        table_data.append([
            Paragraph(det.concepto, body_style),
            Paragraph(f"{det.cantidad:,.2f}", body_style),
            Paragraph(f"${det.precio_unitario:,.2f}", body_style),
            Paragraph(f"${det.subtotal:,.2f}", bold_body_style)
        ])
        
    detalles_table = Table(table_data, colWidths=[3.5 * inch, 0.8 * inch, 1.4 * inch, 1.5 * inch])
    
    # Estilizado de la tabla de detalles
    ts = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), navy_dark),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('TOPPADDING', (0,0), (-1,0), 8),
        ('PADDING', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
    ])
    
    # Alternar color de fondo en filas
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            ts.add('BACKGROUND', (0, i), (-1, i), grey_bg)
            
    detalles_table.setStyle(ts)
    story.append(detalles_table)
    story.append(Spacer(1, 15))
    
    # 4. TOTALES
    total_usd = factura.total
    total_cop = total_usd * factura.tasa_cambio
    
    totales_data = [
        ["", Paragraph("<b>Total USD:</b>", body_style), Paragraph(f"<b>${total_usd:,.2f} USD</b>", bold_body_style)],
        ["", Paragraph("<b>Total COP (Equivalente):</b>", body_style), Paragraph(f"<b>${total_cop:,.2f} COP</b>", bold_body_style)]
    ]
    totales_table = Table(totales_data, colWidths=[4.25 * inch, 1.5 * inch, 1.5 * inch])
    totales_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('LINEABOVE', (1,0), (2,0), 1.5, navy_dark),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(totales_table)
    story.append(Spacer(1, 40))
    
    # 5. PIE DE PÁGINA / NOTAS LEGALES
    nota_style = ParagraphStyle(
        'DocNota',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        textColor=colors.HexColor("#64748b"),
        alignment=1
    )
    story.append(Paragraph("Esta factura constituye un título valor según las leyes vigentes. Los servicios aduaneros prestados se rigen por el estatuto aduanero y arancelario aplicable.", nota_style))
    story.append(Spacer(1, 5))
    story.append(Paragraph("<b>¡Gracias por confiar en nuestros servicios de aduanaje!</b>", nota_style))
    
    # Construir el PDF
    doc.build(story)
    buffer.seek(0)
    return buffer
