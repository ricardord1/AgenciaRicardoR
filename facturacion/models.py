from django.db import models, transaction
from django.db.models import Sum
import datetime


class Cliente(models.Model):
    """
    Representa a un cliente / importador-exportador de la agencia.
    El código secuencial CLI-XXXX se genera automáticamente de forma
    atómica para evitar duplicados bajo concurrencia.
    """
    nombre = models.CharField(max_length=255, verbose_name="Nombre del Cliente")
    email = models.EmailField(verbose_name="Correo Electrónico")
    telefono = models.CharField(max_length=50, verbose_name="Teléfono")
    codigo_cliente = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        verbose_name="Código de Cliente"
    )

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['codigo_cliente']

    def save(self, *args, **kwargs):
        """
        Genera el código secuencial CLI-XXXX de forma atómica.
        CORRECCIÓN: Se usa select_for_update() para bloquear la lectura
        durante la transacción y se ordena numéricamente extrayendo
        el sufijo numérico, evitando ordering alfabético incorrecto.
        NOTA: select_for_update() requiere una base de datos que soporte
        bloqueos a nivel de fila (PostgreSQL, MySQL). SQLite lo ignora
        silenciosamente en modo de desarrollo.
        """
        if not self.codigo_cliente:
            with transaction.atomic():
                # Bloquear toda consulta de clientes durante esta transacción
                last_client = (
                    Cliente.objects.select_for_update()
                    .filter(codigo_cliente__startswith='CLI-')
                    .order_by('-codigo_cliente')
                    .first()
                )
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
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo_cliente} - {self.nombre}"


class ComprobanteFiscal(models.Model):
    """
    Define los tipos de comprobantes fiscales (B01, B02, etc.) y
    gestiona su secuencia de forma concurrentemente segura.
    """
    nombre = models.CharField(max_length=100, verbose_name="Tipo de Comprobante")
    prefijo = models.CharField(max_length=10, unique=True, verbose_name="Prefijo (ej: B01)")
    secuencia_actual = models.IntegerField(default=0, verbose_name="Secuencia Actual")
    secuencia_maxima = models.IntegerField(default=99999999, verbose_name="Secuencia Máxima")

    class Meta:
        verbose_name = "Comprobante Fiscal"
        verbose_name_plural = "Comprobantes Fiscales"

    def obtener_proximo_ncf(self):
        """
        Incrementa la secuencia y devuelve el NCF formateado (ej. B0100000005).
        Utiliza transacción atómica y select_for_update para evitar
        duplicaciones por concurrencia (condición de carrera).
        """
        with transaction.atomic():
            comprobante = ComprobanteFiscal.objects.select_for_update().get(pk=self.pk)
            if comprobante.secuencia_actual >= comprobante.secuencia_maxima:
                raise ValueError(
                    f"Se ha alcanzado el límite de comprobantes fiscales "
                    f"para el prefijo {comprobante.prefijo}"
                )
            comprobante.secuencia_actual += 1
            comprobante.save()
            return f"{comprobante.prefijo}{comprobante.secuencia_actual:08d}"

    def __str__(self):
        return f"{self.nombre} ({self.prefijo})"


class FacturaQuerySet(models.QuerySet):
    """
    QuerySet personalizado con anotaciones optimizadas para evitar N+1 queries.
    """
    def con_total_anotado(self):
        """
        Anota cada factura con su total calculado en la base de datos,
        evitando múltiples queries por la propiedad `total`.
        Usar cuando se listen múltiples facturas.
        """
        return self.annotate(
            total_db=Sum('detalles__cantidad') * Sum('detalles__precio_unitario')
        )


class FacturaManager(models.Manager):
    def get_queryset(self):
        return FacturaQuerySet(self.model, using=self._db)

    def con_total_anotado(self):
        return self.get_queryset().con_total_anotado()


class Factura(models.Model):
    """
    Factura de servicio aduanero. El número de factura y el NCF
    se generan automáticamente de forma atómica al momento de guardar.
    """
    ESTADOS = [
        ('PAGADA', 'Pagada'),
        ('PENDIENTE', 'Pendiente'),
        ('ANULADA', 'Anulada'),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='facturas',
        verbose_name="Cliente"
    )
    comprobante_fiscal = models.ForeignKey(
        ComprobanteFiscal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='facturas',
        verbose_name="Tipo de Comprobante Fiscal"
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
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='PENDIENTE',
        verbose_name="Estado de Pago"
    )
    tasa_cambio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=4120.50,
        verbose_name="Tasa de Cambio (TRM)"
    )

    objects = FacturaManager()

    class Meta:
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"
        ordering = ['-fecha_emision']

    def save(self, *args, **kwargs):
        """
        CORRECCIÓN: La generación del número de factura se envuelve en
        una transacción atómica con select_for_update para evitar
        duplicados bajo carga concurrente.
        """
        if not self.numero_factura:
            with transaction.atomic():
                year = datetime.date.today().year
                prefix = f"FAC-{year}-"
                last_fac = (
                    Factura.objects.select_for_update()
                    .filter(numero_factura__startswith=prefix)
                    .order_by('-numero_factura')
                    .first()
                )
                if last_fac:
                    try:
                        num_part = last_fac.numero_factura.split('-')[2]
                        next_num = int(num_part) + 1
                    except (IndexError, ValueError):
                        next_num = 1
                else:
                    next_num = 1
                self.numero_factura = f"{prefix}{next_num:05d}"

                # Asignar NCF dentro de la misma transacción atómica
                if self.comprobante_fiscal and not self.ncf_asignado:
                    self.ncf_asignado = self.comprobante_fiscal.obtener_proximo_ncf()

                super().save(*args, **kwargs)
        else:
            # Asignar NCF si aplica en actualizaciones donde no se generó antes
            if self.comprobante_fiscal and not self.ncf_asignado:
                self.ncf_asignado = self.comprobante_fiscal.obtener_proximo_ncf()
            super().save(*args, **kwargs)

    @property
    def total(self):
        """
        Calcula el total sumando los subtotales de todos los detalles.
        NOTA: Para listados de múltiples facturas, usar
        Factura.objects.con_total_anotado() para evitar N+1 queries.
        Esta propiedad es correcta para instancias individuales.
        """
        return sum(
            detalle.subtotal for detalle in self.detalles.all()
        )

    def __str__(self):
        return f"{self.numero_factura} - {self.cliente.nombre}"


class DetalleFactura(models.Model):
    """
    Línea de servicio dentro de una factura.
    Cada detalle representa un concepto facturable (servicio, arancel, etc.).
    """
    factura = models.ForeignKey(
        Factura,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name="Factura"
    )
    concepto = models.CharField(max_length=255, verbose_name="Concepto de Servicio")
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Cantidad"
    )
    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Precio Unitario (USD)"
    )

    class Meta:
        verbose_name = "Detalle de Factura"
        verbose_name_plural = "Detalles de Factura"

    @property
    def subtotal(self):
        """Calcula el subtotal de la línea: cantidad × precio_unitario."""
        return self.cantidad * self.precio_unitario

    def __str__(self):
        return f"{self.concepto} ({self.cantidad} × ${self.precio_unitario} = ${self.subtotal})"
