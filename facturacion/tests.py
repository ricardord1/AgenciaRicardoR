from django.test import TestCase
from .models import Cliente, ComprobanteFiscal, Factura, DetalleFactura

class FacturacionBackendTests(TestCase):

    def setUp(self):
        # Configurar un cliente de prueba
        self.cliente = Cliente.objects.create(
            nombre="Importadora Andina S.A.S",
            email="andina@correo.com",
            telefono="3125551234"
        )
        
        # Configurar un tipo de comprobante de prueba
        self.comprobante = ComprobanteFiscal.objects.create(
            nombre="Crédito Fiscal",
            prefijo="B01",
            secuencia_actual=0,
            secuencia_maxima=100
        )

    def test_cliente_codigo_autogenerado(self):
        """
        Verifica que al guardar un cliente sin código, se le asigne CLI-0001
        y al segundo CLI-0002.
        """
        self.assertEqual(self.cliente.codigo_cliente, "CLI-0001")
        
        cliente2 = Cliente.objects.create(
            nombre="Logística del Atlántico",
            email="atlantico@correo.com",
            telefono="3004449876"
        )
        self.assertEqual(cliente2.codigo_cliente, "CLI-0002")

    def test_comprobante_fiscal_secuencia_ncf(self):
        """
        Verifica la correcta obtención secuencial de NCFs y el bloqueo por límite.
        """
        ncf1 = self.comprobante.obtener_proximo_ncf()
        self.assertEqual(ncf1, "B0100000001")
        
        # El objeto en la DB debe haber subido su secuencia a 1
        self.comprobante.refresh_from_db()
        self.assertEqual(self.comprobante.secuencia_actual, 1)

        ncf2 = self.comprobante.obtener_proximo_ncf()
        self.assertEqual(ncf2, "B0100000002")

    def test_factura_autogeneracion_y_totales(self):
        """
        Valida que al crear una factura se autogenere su número, se asigne el NCF
        y que calcule correctamente el total sumado de los detalles.
        """
        # Crear factura asociada al comprobante fiscal
        factura = Factura.objects.create(
            cliente=self.cliente,
            comprobante_fiscal=self.comprobante,
            tasa_cambio=4100.00
        )
        
        # Validar generación del número de factura (FAC-YYYY-00001)
        import datetime
        year = datetime.date.today().year
        self.assertTrue(factura.numero_factura.startswith(f"FAC-{year}-"))
        self.assertEqual(factura.ncf_asignado, "B0100000001")
        
        # Validar total inicial en 0
        self.assertEqual(factura.total, 0)

        # Agregar detalles
        DetalleFactura.objects.create(
            factura=factura,
            concepto="Honorarios por Desaduanamiento de Contenedor",
            cantidad=1.00,
            precio_unitario=350.00
        )
        
        DetalleFactura.objects.create(
            factura=factura,
            concepto="Almacenaje en Puerto (Días Extra)",
            cantidad=3.00,
            precio_unitario=120.00
        )

        # Volver a cargar e inspeccionar totales
        # Honorarios: 1 * 350 = 350
        # Almacenaje: 3 * 120 = 360
        # Total esperado: 710.00
        self.assertEqual(factura.total, 710.00)
