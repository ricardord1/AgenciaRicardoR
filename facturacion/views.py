import requests
import json
from django.shortcuts import get_object_or_404
from django.http import FileResponse, JsonResponse
from django.core.mail import EmailMessage
from django.conf import settings

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from .models import Cliente, ComprobanteFiscal, Factura, DetalleFactura
from .serializers import ClienteSerializer, ComprobanteFiscalSerializer, FacturaSerializer
from .utils import extraer_texto_pdf, estructurar_texto_factura, generar_pdf_factura

# ---------------------------------------------------------
# VIEWSETS CRUD (APIS REST STANDARD)
# ---------------------------------------------------------
class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all().order_by('codigo_cliente')
    serializer_class = ClienteSerializer


class ComprobanteFiscalViewSet(viewsets.ModelViewSet):
    queryset = ComprobanteFiscal.objects.all()
    serializer_class = ComprobanteFiscalSerializer


class FacturaViewSet(viewsets.ModelViewSet):
    queryset = Factura.objects.all().order_by('-fecha_emision')
    serializer_class = FacturaSerializer


# ---------------------------------------------------------
# ENDPOINT: EXTRACCIÓN DE TEXTO PDF (OCR / PARSING)
# ---------------------------------------------------------
class ExtractPDFTextView(APIView):
    """
    Endpoint que recibe un archivo PDF (factura grande del proveedor),
    extrae su texto y lo devuelve estructurado en JSON para que el
    frontend le permita al usuario hacer clic o seleccionar qué guardar.
    """
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        # Integración con el Botón del Frontend:
        # Se activa cuando el usuario hace clic en un botón como "Subir Factura de Proveedor"
        # y sube un archivo adjunto.
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response(
                {"error": "No se proporcionó ningún archivo PDF en la clave 'file'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if not file_obj.name.endswith('.pdf'):
            return Response(
                {"error": "El archivo proporcionado debe ser en formato PDF."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extraer texto usando la utilidad pypdf
        texto_plano = extraer_texto_pdf(file_obj)
        
        # Estructurar texto buscando patrones de facturación
        texto_estructurado = estructurar_texto_factura(texto_plano)
        
        return Response(texto_estructurado, status=status.HTTP_200_OK)


# ---------------------------------------------------------
# ENDPOINT: IMPRIMIR FACTURA (GENERAR PDF)
# ---------------------------------------------------------
class PrintInvoicePDFView(APIView):
    """
    Genera y devuelve la factura en formato PDF listo para descargar.
    """
    def get(self, request, pk, *args, **kwargs):
        # Integración con el Botón del Frontend:
        # Vinculado al icono de PDF en la tabla de facturas (ej: <button title="Descargar PDF">)
        # redirigiendo al usuario a: `/api/facturas/{id}/imprimir/`
        factura = get_object_or_404(Factura, pk=pk)
        
        # Generar el PDF en memoria con ReportLab
        pdf_buffer = generar_pdf_factura(factura)
        
        filename = f"Factura_{factura.numero_factura}.pdf"
        return FileResponse(
            pdf_buffer, 
            as_attachment=True, 
            filename=filename, 
            content_type='application/pdf'
        )


# ---------------------------------------------------------
# ENDPOINT: ENVIAR FACTURA POR CORREO ELECTRÓNICO
# ---------------------------------------------------------
class SendInvoiceEmailView(APIView):
    """
    Envía la factura generada por PDF al correo electrónico registrado del cliente.
    """
    def post(self, request, pk, *args, **kwargs):
        # Integración con el Botón del Frontend:
        # Vinculado a una opción de acción rápida como "Enviar por Correo".
        # Realiza un POST a `/api/facturas/{id}/enviar-correo/`
        factura = get_object_or_404(Factura, pk=pk)
        cliente = factura.cliente
        
        if not cliente.email:
            return Response(
                {"error": "El cliente no tiene un correo electrónico registrado."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 1. Generar el PDF en memoria
            pdf_buffer = generar_pdf_factura(factura)
            pdf_data = pdf_buffer.getvalue()
            
            # 2. Construir el correo electrónico
            subject = f"Factura de Servicios de Aduana - {factura.numero_factura}"
            body = (
                f"Estimado cliente {cliente.nombre},\n\n"
                f"Adjunto a este correo encontrará la factura {factura.numero_factura} "
                f"correspondiente a los servicios aduaneros prestados por un monto de "
                f"${factura.total:,.2f} USD.\n\n"
                f"Estado del pago: {factura.estado}\n\n"
                f"Saludos cordiales,\n"
                f"Agencia de Aduanas S.A."
            )
            
            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[cliente.email]
            )
            
            # Adjuntar el archivo PDF
            filename = f"Factura_{factura.numero_factura}.pdf"
            email.attach(filename, pdf_data, 'application/pdf')
            
            # Enviar el correo
            email.send(fail_silently=False)
            
            return Response(
                {"success": f"Factura enviada exitosamente al correo {cliente.email}"}, 
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": f"Error al enviar el correo electrónico: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ---------------------------------------------------------
# ENDPOINT: ENVIAR NOTIFICACIÓN POR WHATSAPP
# ---------------------------------------------------------
class SendInvoiceWhatsAppView(APIView):
    """
    Estructura y simula el envío de una notificación de factura por WhatsApp.
    Ejemplo de integración real con Twilio y la API Cloud Oficial de WhatsApp.
    """
    def post(self, request, pk, *args, **kwargs):
        # Integración con el Botón del Frontend:
        # Vinculado a un botón como "Enviar por WhatsApp" que ejecuta un POST
        # a `/api/facturas/{id}/enviar-whatsapp/`
        factura = get_object_or_404(Factura, pk=pk)
        cliente = factura.cliente
        
        if not cliente.telefono:
            return Response(
                {"error": "El cliente no tiene un número telefónico registrado."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Configuración de variables (generalmente en settings.py o variables de entorno)
        # Ejemplo con Twilio:
        twilio_account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', 'ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')
        twilio_auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', 'your_auth_token_here')
        twilio_from_number = getattr(settings, 'TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886') # Número sandbox Twilio
        
        # Teléfono destino en formato E.164 (debe comenzar con el código de país, ej: whatsapp:+573001234567)
        telefono_destino = f"whatsapp:{cliente.telefono}"
        if not cliente.telefono.startswith('+'):
            # Formateador básico de ejemplo (asumiendo Colombia +57 si no tiene prefijo)
            telefono_destino = f"whatsapp:+57{cliente.telefono}"

        # Cuerpo del mensaje (Plantilla aprobada si es API oficial)
        mensaje_texto = (
            f"Hola {cliente.nombre}, tu factura de servicios aduaneros de la Agencia de Aduanas "
            f"ha sido emitida. *Factura:* {factura.numero_factura}. *Monto:* ${factura.total:,.2f} USD. "
            f"Puedes descargar el PDF aquí: http://mi-agencia-aduanas.com/api/facturas/{factura.id}/imprimir/"
        )

        payload = {
            'From': twilio_from_number,
            'To': telefono_destino,
            'Body': mensaje_texto
        }

        # URL de Twilio para mensajes
        url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_account_sid}/Messages.json"

        # Simular petición HTTP a Twilio (con control de fallback para pruebas locales)
        try:
            # En producción se descontentaría este bloque:
            # response = requests.post(url, data=payload, auth=(twilio_account_sid, twilio_auth_token), timeout=10)
            # if response.status_code not in [200, 201]:
            #     raise Exception(response.text)
            
            # Simulación de respuesta exitosa para el frontend
            mock_twilio_response = {
                "sid": "SMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                "status": "queued",
                "to": telefono_destino,
                "from": twilio_from_number,
                "body": mensaje_texto,
                "api_integration_mocked": True
            }
            
            return Response({
                "success": f"Mensaje de WhatsApp encolado exitosamente para {cliente.nombre} al número {cliente.telefono}.",
                "data": mock_twilio_response
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": f"Error al conectar con el servicio de WhatsApp: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
