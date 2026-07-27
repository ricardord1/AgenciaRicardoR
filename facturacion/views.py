import requests
from django.shortcuts import get_object_or_404
from django.http import FileResponse, JsonResponse
from django.core.mail import EmailMessage
from django.conf import settings

from rest_framework import viewsets, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action

from .models import Cliente, ComprobanteFiscal, Factura, DetalleFactura
from .serializers import ClienteSerializer, ComprobanteFiscalSerializer, FacturaSerializer
from .utils import extraer_texto_pdf, estructurar_texto_factura, generar_pdf_factura


# ---------------------------------------------------------
# VIEWSETS CRUD — API REST ESTÁNDAR
# ---------------------------------------------------------

class ClienteViewSet(viewsets.ModelViewSet):
    """
    API CRUD completa para la gestión de clientes.
    Soporta búsqueda por nombre, email y código.
    """
    queryset = Cliente.objects.all().order_by('codigo_cliente')
    serializer_class = ClienteSerializer
    # Habilitar búsqueda y ordenamiento desde query params
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre', 'email', 'codigo_cliente', 'telefono']
    ordering_fields = ['codigo_cliente', 'nombre']
    ordering = ['codigo_cliente']


class ComprobanteFiscalViewSet(viewsets.ModelViewSet):
    """
    API CRUD para la gestión de tipos de comprobantes fiscales (NCF).
    """
    queryset = ComprobanteFiscal.objects.all()
    serializer_class = ComprobanteFiscalSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre', 'prefijo']


class FacturaViewSet(viewsets.ModelViewSet):
    """
    API CRUD completa para la gestión de facturas.
    Soporta filtrado por estado, búsqueda por número/cliente y ordenamiento.
    Incluye select_related para evitar N+1 queries en listados.
    """
    serializer_class = FacturaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['numero_factura', 'cliente__nombre', 'cliente__codigo_cliente', 'ncf_asignado']
    ordering_fields = ['fecha_emision', 'numero_factura', 'estado']
    ordering = ['-fecha_emision']

    def get_queryset(self):
        """
        Optimiza el queryset con select_related para evitar N+1 queries
        en la serialización de cliente y comprobante_fiscal.
        Soporta filtrado por `estado` vía query param: ?estado=PAGADA
        """
        qs = Factura.objects.select_related(
            'cliente', 'comprobante_fiscal'
        ).prefetch_related('detalles')

        # Filtro opcional por estado desde query param
        estado = self.request.query_params.get('estado')
        if estado and estado.upper() in ['PAGADA', 'PENDIENTE', 'ANULADA']:
            qs = qs.filter(estado=estado.upper())

        return qs

    @action(detail=True, methods=['post'], url_path='cambiar-estado')
    def cambiar_estado(self, request, pk=None):
        """
        Endpoint de acción rápida para cambiar el estado de una factura.
        POST /api/facturas/{id}/cambiar-estado/ con body: {"estado": "PAGADA"}
        """
        factura = self.get_object()
        nuevo_estado = request.data.get('estado', '').upper()

        estados_validos = [choice[0] for choice in Factura.ESTADOS]
        if nuevo_estado not in estados_validos:
            return Response(
                {"error": f"Estado inválido. Opciones válidas: {', '.join(estados_validos)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        factura.estado = nuevo_estado
        factura.save(update_fields=['estado'])

        serializer = self.get_serializer(factura)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------
# ENDPOINT: EXTRACCIÓN DE TEXTO PDF (PARSING)
# ---------------------------------------------------------

class ExtractPDFTextView(APIView):
    """
    Recibe un archivo PDF de factura de proveedor, extrae su texto
    y devuelve una estructura JSON con sugerencias de valores detectados
    (totales, números de factura, fechas) para que el usuario seleccione
    qué importar al sistema.
    """
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')

        if not file_obj:
            return Response(
                {"error": "No se proporcionó ningún archivo PDF en la clave 'file'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar extensión
        if not file_obj.name.lower().endswith('.pdf'):
            return Response(
                {"error": "El archivo proporcionado debe ser en formato PDF (.pdf)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar tamaño máximo (10 MB)
        max_size_mb = 10
        if file_obj.size > max_size_mb * 1024 * 1024:
            return Response(
                {"error": f"El archivo no puede superar {max_size_mb} MB."},
                status=status.HTTP_400_BAD_REQUEST
            )

        texto_plano = extraer_texto_pdf(file_obj)
        texto_estructurado = estructurar_texto_factura(texto_plano)

        return Response(texto_estructurado, status=status.HTTP_200_OK)


# ---------------------------------------------------------
# ENDPOINT: IMPRIMIR FACTURA (GENERAR PDF)
# ---------------------------------------------------------

class PrintInvoicePDFView(APIView):
    """
    Genera y descarga la factura en formato PDF.
    GET /api/facturas/{id}/imprimir/
    """
    def get(self, request, pk, *args, **kwargs):
        factura = get_object_or_404(
            Factura.objects.select_related('cliente', 'comprobante_fiscal')
                           .prefetch_related('detalles'),
            pk=pk
        )

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
    Genera el PDF de la factura y lo envía al correo del cliente.
    POST /api/facturas/{id}/enviar-correo/
    """
    def post(self, request, pk, *args, **kwargs):
        factura = get_object_or_404(
            Factura.objects.select_related('cliente').prefetch_related('detalles'),
            pk=pk
        )
        cliente = factura.cliente

        if not cliente.email:
            return Response(
                {"error": "El cliente no tiene un correo electrónico registrado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar que la factura no esté anulada
        if factura.estado == 'ANULADA':
            return Response(
                {"error": "No se puede enviar una factura anulada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            pdf_buffer = generar_pdf_factura(factura)
            pdf_data = pdf_buffer.getvalue()

            subject = f"Factura de Servicios de Aduana — {factura.numero_factura}"
            body = (
                f"Estimado(a) {cliente.nombre},\n\n"
                f"Adjunto a este correo encontrará la factura {factura.numero_factura} "
                f"correspondiente a los servicios aduaneros prestados por un monto de "
                f"${factura.total:,.2f} USD.\n\n"
                f"Estado de pago: {factura.get_estado_display()}\n"
                f"Tasa de cambio aplicada: ${factura.tasa_cambio:,.2f} COP/USD\n\n"
                f"Saludos cordiales,\n"
                f"Agencia de Aduanas S.A.\n"
                f"Tel: +57 (1) 000-0000 | facturacion@aduana.com"
            )

            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[cliente.email]
            )
            email.attach(
                f"Factura_{factura.numero_factura}.pdf",
                pdf_data,
                'application/pdf'
            )
            email.send(fail_silently=False)

            return Response(
                {
                    "success": True,
                    "message": f"Factura enviada exitosamente al correo {cliente.email}",
                    "factura": factura.numero_factura,
                    "destinatario": cliente.email
                },
                status=status.HTTP_200_OK
            )

        except ConnectionRefusedError:
            return Response(
                {"error": "No se pudo conectar al servidor de correo. Verifique la configuración SMTP."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
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
    Envía una notificación de factura por WhatsApp vía API de Twilio.
    Actualmente en modo simulación (mock). Para producción, descomentar
    el bloque `requests.post(...)`.
    POST /api/facturas/{id}/enviar-whatsapp/
    """
    def post(self, request, pk, *args, **kwargs):
        factura = get_object_or_404(
            Factura.objects.select_related('cliente').prefetch_related('detalles'),
            pk=pk
        )
        cliente = factura.cliente

        if not cliente.telefono:
            return Response(
                {"error": "El cliente no tiene un número telefónico registrado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if factura.estado == 'ANULADA':
            return Response(
                {"error": "No se puede notificar una factura anulada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Formatear número de teléfono al estándar E.164
        telefono_raw = cliente.telefono.strip()
        if telefono_raw.startswith('whatsapp:'):
            telefono_destino = telefono_raw
        elif telefono_raw.startswith('+'):
            telefono_destino = f"whatsapp:{telefono_raw}"
        else:
            # Sin código de país: registrar advertencia — el cliente debe
            # actualizar su teléfono con el código de país completo.
            # Este fallback es solo para compatibilidad temporal.
            telefono_destino = f"whatsapp:+{telefono_raw}"

        # Configuración de Twilio desde settings (que a su vez lee del .env)
        twilio_account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        twilio_auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        twilio_from_number = getattr(settings, 'TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')

        # URL pública de descarga del PDF (ajustar al dominio de producción)
        base_url = request.build_absolute_uri(f'/api/facturas/{factura.id}/imprimir/')

        mensaje_texto = (
            f"Hola {cliente.nombre}, tu factura de servicios aduaneros de la *Agencia de Aduanas* "
            f"ha sido emitida.\n\n"
            f"📄 *Factura:* {factura.numero_factura}\n"
            f"💵 *Monto:* ${factura.total:,.2f} USD\n"
            f"📌 *Estado:* {factura.get_estado_display()}\n\n"
            f"Descarga tu PDF aquí: {base_url}"
        )

        payload = {
            'From': twilio_from_number,
            'To': telefono_destino,
            'Body': mensaje_texto
        }

        try:
            # --- MODO PRODUCCIÓN: descomentar el siguiente bloque ---
            # if not twilio_account_sid or not twilio_auth_token:
            #     raise ValueError("Credenciales de Twilio no configuradas en settings.")
            # url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_account_sid}/Messages.json"
            # response = requests.post(
            #     url, data=payload,
            #     auth=(twilio_account_sid, twilio_auth_token),
            #     timeout=10
            # )
            # response.raise_for_status()
            # twilio_data = response.json()
            # --------------------------------------------------------

            # Simulación para desarrollo (mock)
            mock_twilio_response = {
                "sid": "SMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                "status": "queued",
                "to": telefono_destino,
                "from": twilio_from_number,
                "body": mensaje_texto,
                "api_integration_mocked": True
            }

            return Response(
                {
                    "success": True,
                    "message": (
                        f"Mensaje de WhatsApp encolado exitosamente para "
                        f"{cliente.nombre} al número {cliente.telefono}."
                    ),
                    "data": mock_twilio_response
                },
                status=status.HTTP_200_OK
            )

        except requests.exceptions.Timeout:
            return Response(
                {"error": "Tiempo de espera agotado al conectar con Twilio."},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except Exception as e:
            return Response(
                {"error": f"Error al conectar con el servicio de WhatsApp: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
