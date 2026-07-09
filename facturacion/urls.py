from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClienteViewSet, 
    ComprobanteFiscalViewSet, 
    FacturaViewSet,
    ExtractPDFTextView,
    PrintInvoicePDFView,
    SendInvoiceEmailView,
    SendInvoiceWhatsAppView
)

app_name = 'facturacion'

router = DefaultRouter()
router.register('clientes', ClienteViewSet, basename='cliente')
router.register('comprobantes-fiscales', ComprobanteFiscalViewSet, basename='comprobante-fiscal')
router.register('facturas', FacturaViewSet, basename='factura')

urlpatterns = [
    # Rutas CRUD estándar de DRF
    path('', include(router.urls)),
    
    # Endpoints de Acción Personalizados
    path('extraer-pdf/', ExtractPDFTextView.as_view(), name='extraer-pdf'),
    path('facturas/<int:pk>/imprimir/', PrintInvoicePDFView.as_view(), name='factura-imprimir'),
    path('facturas/<int:pk>/enviar-correo/', SendInvoiceEmailView.as_view(), name='factura-enviar-correo'),
    path('facturas/<int:pk>/enviar-whatsapp/', SendInvoiceWhatsAppView.as_view(), name='factura-enviar-whatsapp'),
]
