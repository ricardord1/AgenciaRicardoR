from rest_framework import serializers
from django.db import transaction
from .models import Cliente, ComprobanteFiscal, Factura, DetalleFactura

class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ['id', 'nombre', 'email', 'telefono', 'codigo_cliente']
        read_only_fields = ['codigo_cliente']


class ComprobanteFiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComprobanteFiscal
        fields = ['id', 'nombre', 'prefijo', 'secuencia_actual', 'secuencia_maxima']


class DetalleFacturaSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = DetalleFactura
        fields = ['id', 'concepto', 'cantidad', 'precio_unitario', 'subtotal']


class FacturaSerializer(serializers.ModelSerializer):
    detalles = DetalleFacturaSerializer(many=True, required=False)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)

    class Meta:
        model = Factura
        fields = [
            'id', 'cliente', 'cliente_nombre', 'comprobante_fiscal', 
            'ncf_asignado', 'numero_factura', 'fecha_emision', 
            'estado', 'tasa_cambio', 'detalles', 'total'
        ]
        read_only_fields = ['numero_factura', 'ncf_asignado', 'fecha_emision']

    def create(self, validated_data):
        """
        Permite la creación de facturas junto con su listado de detalles en una transacción atómica.
        """
        # Extraer los detalles de los datos de la petición
        detalles_data = self.initial_data.get('detalles', [])
        
        # Eliminar 'detalles' de validated_data si está presente para evitar error de relación inversa
        validated_data.pop('detalles', None)
        
        with transaction.atomic():
            factura = Factura.objects.create(**validated_data)
            for det in detalles_data:
                DetalleFactura.objects.create(
                    factura=factura,
                    concepto=det.get('concepto'),
                    cantidad=det.get('cantidad'),
                    precio_unitario=det.get('precio_unitario')
                )
            # Volver a cargar la factura con los detalles guardados
            factura.refresh_from_db()
        return factura
