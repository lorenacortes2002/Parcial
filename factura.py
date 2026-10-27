"""Comprobante PDF del prototipo; no realiza cobros ni envia correo."""
from io import BytesIO
from decimal import Decimal
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import A4


def generar_factura_pdf(pedido, pago):
    if str(pedido['id']) != str(pago['pedido_id']):
        raise ValueError('El pago no corresponde al pedido.')
    if pago.get('estado') != 'CONFIRMADO':
        raise ValueError('El comprobante requiere un pago confirmado.')
    def money(value):
        return '${:,.2f}'.format(Decimal(str(value or 0)))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('Marca', fontName='Helvetica-Bold', fontSize=24, leading=29, textColor=colors.HexColor('#193a2b')))
    styles.add(ParagraphStyle('Nota', fontSize=9, leading=13, textColor=colors.HexColor('#52645c')))
    styles.add(ParagraphStyle('Derecha', parent=styles['Normal'], alignment=TA_RIGHT))
    def text(value, style='Normal'):
        return Paragraph(escape(str(value or '')).replace('\n','<br/>'), styles[style])
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=40, bottomMargin=46,
                            title=f"Comprobante del pedido {pedido['id']}", author='Chinos Cafe')
    story = [text('CHINOS CAFÉ', 'Marca'), Spacer(1, 10), text(f"COMPROBANTE DE PEDIDO #{pedido['id']}", 'Heading2'),
             text('Prototipo académico - Pago simulado - Sin validez fiscal', 'Nota'), Spacer(1,18)]
    for label, value in [('Fecha del pago',pago.get('fecha')), ('Cliente',pedido.get('cliente')),
                         ('Correo',pedido.get('correo_cliente')), ('Entrega',pedido.get('retiro_o_flete')),
                         ('Dirección',pedido.get('direccion'))]:
        if value:
            story.append(text(f'{label}: {value}'))
            story.append(Spacer(1,5))
    story.append(Spacer(1,14))
    rows = [[text('Producto / detalle'), text('Cant.'), text('Precio base'), text('Importe')]]
    items = pedido.get('items') or []
    for item in items:
        detail = str(item.get('producto','Producto'))
        if item.get('borde'):
            detail += '\nBorde: ' + str(item['borde'])
        if item.get('precio_borde'):
            detail += ' (adicional unitario ' + money(item['precio_borde']) + ')'
        if item.get('sodas'):
            detail += '\nSodas: ' + str(item['sodas'])
        if item.get('precio_sodas'):
            detail += ' (adicional ' + money(item['precio_sodas']) + ')'
        rows.append([text(detail),text(item.get('cantidad',1)),text(money(item.get('precio_unitario'))),text(money(item.get('subtotal')))])
    if not items:
        rows.append([text(str(pedido.get('pizza','Pedido'))+'\nSodas: '+str(pedido.get('refresco','Ninguna'))),text(pedido.get('cantidad',1)),text('-'),text(money(pedido.get('total')))])
    table = Table(rows, colWidths=[285,42,85,99], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eee9')),('VALIGN',(0,0),(-1,-1),'TOP'),
                              ('LINEBELOW',(0,0),(-1,0),1,colors.HexColor('#193a2b')),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#d8dfda')),
                              ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story += [table,Spacer(1,16)]
    if pedido.get('subtotal') is not None:
        story.append(text('Subtotal: '+money(pedido['subtotal']),'Derecha'))
        story.append(text('Flete: '+money(pedido.get('flete',0)),'Derecha'))
    story += [text('TOTAL PAGADO: '+money(pago['monto']),'Heading2'), Spacer(1,8),text('Método / referencia: '+str(pago.get('metodo',''))),
              Spacer(1,16),text('Gracias por tu pedido. Conserva este comprobante y los archivos JSON adjuntos.', 'Nota')]
    def footer(canvas, document):
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#52645c'))
        canvas.drawString(42,26,'CHINOS CAFÉ | Comprobante del prototipo')
        canvas.drawRightString(A4[0]-42,26,f'Página {document.page}');canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()


def adjuntar_factura(msg, documentos):
    """Usar los JSON persistidos, sin volver a consultar ni alterar la base."""
    import json
    datos = [json.loads(body) for name, body in documentos if name.endswith('.json')]
    pedido = next((d for d in datos if d.get('tipo') == 'CONFIRMACION_PEDIDO'), None)
    pago = next((d for d in datos if d.get('tipo') == 'CONFIRMACION_PAGO'), None)
    if pedido is None or pago is None:
        raise ValueError('Faltan los JSON del pedido y del pago para generar el comprobante.')
    pdf = generar_factura_pdf(pedido, pago)
    msg.add_attachment(pdf, maintype='application', subtype='pdf', filename=f"factura_pedido_{pedido['id']}.pdf")
    msg.replace_header('Subject', f"Factura de tu pedido #{pedido['id']} - Chinos Café")
