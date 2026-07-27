from decimal import Decimal
from rest_framework import serializers
from django.db import transaction
from .models import Cliente, ComprobanteFiscal, Factura, DetalleFactura


class ClienteSerializer(serializers.ModelSerializer):
    """Serializer completo para el modelo Cliente."""
    # Campo calculado: cantidad de facturas asociadas (útil para listados)
    total_facturas = serializers.IntegerField(
        source='facturas.count',
        read_only=True
    )

    class Meta:
        model = Cliente
        fields = ['id', 'nombre', 'email', 'telefono', 'codigo_cliente', 'total_facturas']
        read_only_fields = ['codigo_cliente']

    def validate_email(self, value):
        """Normaliza el email a minúsculas."""
        return value.lower().strip()

    def validate_nombre(self, value):
        """Asegura que el nombre no esté vacío después de strip."""
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("El nombre del cliente no puede estar vacío.")
        return stripped


class ComprobanteFiscalSerializer(serializers.ModelSerializer):
    """Serializer para ComprobanteFiscal con campo de disponibilidad."""
    secuencias_disponibles = serializers.SerializerMethodField()

    class Meta:
        model = ComprobanteFiscal
        fields = [
            'id', 'nombre', 'prefijo',
            'secuencia_actual', 'secuencia_maxima',
            'secuencias_disponibles'
        ]
        # La secuencia actual es manejada internamente — no editable por API
        read_only_fields = ['secuencia_actual']

    def get_secuencias_disponibles(self, obj):
        """Calcula cuántos NCFs quedan disponibles."""
        return obj.secuencia_maxima - obj.secuencia_actual


class DetalleFacturaSerializer(serializers.ModelSerializer):
    """
    Serializer para las líneas de detalle de una factura.
    Incluye validaciones de negocio para cantidad y precio.
    """
    subtotal = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = DetalleFactura
        fields = ['id', 'concepto', 'cantidad', 'precio_unitario', 'subtotal']

    def validate_cantidad(self, value):
        """La cantidad debe ser un número positivo mayor a cero."""
        if value <= Decimal('0'):
            raise serializers.ValidationError(
                "La cantidad debe ser mayor a cero."
            )
        return value

    def validate_precio_unitario(self, value):
        """El precio unitario debe ser un número positivo."""
        if value < Decimal('0'):
            raise serializers.ValidationError(
                "El precio unitario no puede ser negativo."
            )
        return value

    def validate_concepto(self, value):
        """El concepto no puede estar vacío."""
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError(
                "El concepto del servicio no puede estar vacío."
            )
        return stripped


class FacturaSerializer(serializers.ModelSerializer):
    """
    Serializer principal de Factura.
    Soporta creación anidada de detalles en una transacción atómica.
    CORRECCIÓN: Los detalles se leen y validan desde validated_data,
    no desde self.initial_data (que no pasa por validación).
    """
    # Escritura y lectura de detalles anidados
    detalles = DetalleFacturaSerializer(many=True, required=False)

    # Campos de solo lectura calculados
    total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    cliente_nombre = serializers.CharField(
        source='cliente.nombre',
        read_only=True
    )
    cliente_codigo = serializers.CharField(
        source='cliente.codigo_cliente',
        read_only=True
    )
    comprobante_nombre = serializers.CharField(
        source='comprobante_fiscal.nombre',
        read_only=True,
        allow_null=True
    )
    estado_display = serializers.CharField(
        source='get_estado_display',
        read_only=True
    )

    class Meta:
        model = Factura
        fields = [
            'id',
            'cliente', 'cliente_nombre', 'cliente_codigo',
            'comprobante_fiscal', 'comprobante_nombre',
            'ncf_asignado', 'numero_factura',
            'fecha_emision', 'estado', 'estado_display',
            'tasa_cambio', 'detalles', 'total'
        ]
        read_only_fields = ['numero_factura', 'ncf_asignado', 'fecha_emision']

    def validate_detalles(self, value):
        """
        Valida que la factura tenga al menos un detalle de servicio.
        Esta validación aplica solo en creación (cuando se envían detalles).
        """
        if self.instance is None and len(value) == 0:
            raise serializers.ValidationError(
                "La factura debe contener al menos un detalle de servicio."
            )
        return value

    def validate_tasa_cambio(self, value):
        """La tasa de cambio debe ser positiva."""
        if value <= Decimal('0'):
            raise serializers.ValidationError(
                "La tasa de cambio debe ser un valor positivo."
            )
        return value

    def create(self, validated_data):
        """
        Crea la factura con sus detalles en una transacción atómica.
        CORRECCIÓN: Los detalles se extraen de validated_data (ya validados),
        no de self.initial_data (datos crudos sin validar).
        """
        # Extraer los detalles del validated_data (ya validados y limpios)
        detalles_data = validated_data.pop('detalles', [])

        with transaction.atomic():
            # Crear la factura (dispara la lógica de save() para número y NCF)
            factura = Factura.objects.create(**validated_data)

            # Crear los detalles asociados
            detalles_objs = [
                DetalleFactura(
                    factura=factura,
                    concepto=det['concepto'],
                    cantidad=det['cantidad'],
                    precio_unitario=det['precio_unitario']
                )
                for det in detalles_data
            ]
            if detalles_objs:
                DetalleFactura.objects.bulk_create(detalles_objs)

            # Recargar para obtener los detalles recién creados
            factura.refresh_from_db()

        return factura

    def update(self, instance, validated_data):
        """
        Actualización de factura. Si se envían detalles, reemplaza todos los
        existentes (comportamiento de reemplazo completo).
        """
        detalles_data = validated_data.pop('detalles', None)

        with transaction.atomic():
            # Actualizar campos de la factura
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            # Si se enviaron detalles, reemplazar completamente
            if detalles_data is not None:
                instance.detalles.all().delete()
                detalles_objs = [
                    DetalleFactura(
                        factura=instance,
                        concepto=det['concepto'],
                        cantidad=det['cantidad'],
                        precio_unitario=det['precio_unitario']
                    )
                    for det in detalles_data
                ]
                if detalles_objs:
                    DetalleFactura.objects.bulk_create(detalles_objs)

        instance.refresh_from_db()
        return instance
