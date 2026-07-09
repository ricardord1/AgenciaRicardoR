from django.db import models, transaction
import datetime

class Cliente(models.Model):
    nombre = models.CharField(max_length=255, verbose_name="Nombre del Cliente")
    email = models.EmailField(verbose_name="Correo Electrónico")
    telefono = models.CharField(max_length=50, verbose_name="Teléfono")
    codigo_cliente = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True, 
        verbose_name="Código de Cliente"
    )

    def save(self, *args, **kwargs):
        # Generar código secuencial automático si no está definido (CLI-0001, CLI-0002, etc.)
        if not self.codigo_cliente:
            last_client = Cliente.objects.filter(codigo_cliente__startswith='CLI-').order_by('-codigo_cliente').first()
            if last_client:
                try:
                    num_part = last_client.codigo_cliente.split('-')[1]
                    next_num = int(num_part) + 1
                except (IndexError, ValueError):
                    next_num = 1
            else:
                next_num = 1
            self.codigo_cliente = f"CLI-{next_num:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo_cliente} - {self.nombre}"


class ComprobanteFiscal(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Tipo de Comprobante")
    prefijo = models.CharField(max_length=10, unique=True, verbose_name="Prefijo (ej: B01)")
    secuencia_actual = models.IntegerField(default=0, verbose_name="Secuencia Actual")
    secuencia_maxima = models.IntegerField(default=99999999, verbose_name="Secuencia Máxima")

    def obtener_proximo_ncf(self):
        """
        Incrementa la secuencia y devuelve el NCF formateado (ej. B0100000005).
        Utiliza una transacción atómica y select_for_update para evitar duplicaciones por concurrencia.
        """
        with transaction.atomic():
            # Bloquear la fila para actualización
            comprobante = ComprobanteFiscal.objects.select_for_update().get(pk=self.pk)
            if comprobante.secuencia_actual >= comprobante.secuencia_maxima:
                raise ValueError(f"Se ha alcanzado el límite de comprobantes fiscales para el prefijo {comprobante.prefijo}")
            comprobante.secuencia_actual += 1
            comprobante.save()
            return f"{comprobante.prefijo}{comprobante.secuencia_actual:08d}"

    def __str__(self):
        return f"{self.nombre} ({self.prefijo})"


class Factura(models.Model):
    ESTADOS = [
        ('PAGADA', 'Pagada'),
        ('PENDIENTE', 'Pendiente'),
        ('ANULADA', 'Anulada'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='facturas')
    comprobante_fiscal = models.ForeignKey(
        ComprobanteFiscal, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='facturas'
    )
    ncf_asignado = models.CharField(
        max_length=30, 
        blank=True, 
        null=True, 
        verbose_name="NCF Asignado"
    )
    numero_factura = models.CharField(
        max_length=30, 
        unique=True, 
        blank=True, 
        verbose_name="Número de Factura"
    )
    fecha_emision = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Emisión")
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    tasa_cambio = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=4120.50, 
        verbose_name="Tasa de Cambio (TRM)"
    )

    def save(self, *args, **kwargs):
        # 1. Generar número de factura secuencial por año (ej: FAC-2026-00001)
        if not self.numero_factura:
            year = datetime.date.today().year
            prefix = f"FAC-{year}-"
            last_fac = Factura.objects.filter(numero_factura__startswith=prefix).order_by('-numero_factura').first()
            if last_fac:
                try:
                    num_part = last_fac.numero_factura.split('-')[2]
                    next_num = int(num_part) + 1
                except (IndexError, ValueError):
                    next_num = 1
            else:
                next_num = 1
            self.numero_factura = f"{prefix}{next_num:05d}"

        # 2. Asignar NCF automático si tiene tipo de comprobante y no ha sido asignado aún
        if self.comprobante_fiscal and not self.ncf_asignado:
            self.ncf_asignado = self.comprobante_fiscal.obtener_proximo_ncf()

        super().save(*args, **kwargs)

    @property
    def total(self):
        """Suma de los subtotales de todos los detalles asociados."""
        return sum(detalle.subtotal for detalle in self.detalles.all())

    def __str__(self):
        return f"{self.numero_factura} - {self.cliente.nombre} (Total: ${self.total})"


class DetalleFactura(models.Model):
    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name='detalles')
    concepto = models.CharField(max_length=255, verbose_name="Concepto de Servicio")
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cantidad")
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Precio Unitario")

    @property
    def subtotal(self):
        """Calcula el subtotal por línea."""
        return self.cantidad * self.precio_unitario

    def __str__(self):
        return f"{self.concepto} ({self.cantidad} x {self.precio_unitario} = {self.subtotal})"
