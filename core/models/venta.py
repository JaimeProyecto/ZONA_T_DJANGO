from django.db import models
from core.models.cliente import Cliente
from core.models.producto import Product


class Factura(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    fecha = models.DateField(auto_now_add=True)
    estado = models.CharField(max_length=20, default="Activa")  # o Anulada

    def total(self):
        return sum([detalle.subtotal() for detalle in self.detallefactura_set.all()])

    def __str__(self):
        return f"Factura #{self.id} - {self.cliente.nombre}"


class DetalleFactura(models.Model):
    factura = models.ForeignKey(Factura, on_delete=models.CASCADE)
    producto = models.ForeignKey(Product, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    def subtotal(self):
        return self.cantidad * self.precio_unitario
