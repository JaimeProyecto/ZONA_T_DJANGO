from django.db import models
from django.utils import timezone
from typing import TYPE_CHECKING
from django.contrib.auth.models import User
from decimal import Decimal
from django.db.models import DecimalField

if TYPE_CHECKING:
    from core.models import Abono


class Cliente(models.Model):
    nombre = models.CharField(max_length=100)
    cedula = models.CharField(max_length=20)
    direccion = models.TextField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    correo = models.EmailField(blank=True, null=True)

    creado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return self.nombre


class Product(models.Model):
    reference = models.CharField(max_length=100, unique=True, verbose_name="Referencia")
    description = models.TextField(verbose_name="Descripción del Producto")
    purchase_price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Valor de Compra"
    )
    stock = models.PositiveIntegerField(
        default=0, verbose_name="Unidades en Existencia"
    )

    def __str__(self) -> str:
        return f"{self.reference} - {self.description}"


class Venta(models.Model):
    TIPO_PAGO_CHOICES = [
        ("contado", "Contado"),
        ("credito", "Crédito"),
        ("transferencia", "Transferencia"),
        ("garantia", "Garantía"),
    ]

    cliente = models.ForeignKey("Cliente", on_delete=models.CASCADE)
    fecha = models.DateTimeField(auto_now_add=True)
    numero_factura = models.CharField(max_length=20, unique=True, blank=True, null=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(
        max_length=10,
        choices=[("activa", "Activa"), ("anulada", "Anulada")],
        default="activa",
    )
    tipo_pago = models.CharField(
        max_length=15,
        choices=TIPO_PAGO_CHOICES,
        default="contado",
    )
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def calcular_total(self):
        return sum(item.subtotal() for item in self.items.all())

    def calcular_abonos(self):
        return sum(abono.monto for abono in self.abonos.all())

    def calcular_saldo_pendiente(self):
        return self.total - self.calcular_abonos()

    def save(self, *args, **kwargs):
        # Asigna número de factura solo la primera vez
        if not self.numero_factura:
            # Determina prefijo según tipo de pago
            if self.tipo_pago == "credito":
                prefijo = "FC1-"
            elif self.tipo_pago == "transferencia":
                prefijo = "FT1-"
            elif self.tipo_pago == "garantia":
                prefijo = "FG1-"
            else:
                prefijo = "FV1-"
            # Cuenta ventas previas del mismo tipo y genera el secuencial
            contador = Venta.objects.filter(tipo_pago=self.tipo_pago).count() + 1
            self.numero_factura = f"{prefijo}{contador}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero_factura} – {self.cliente.nombre}"


# models.py
class VentaItem(models.Model):
    venta = models.ForeignKey(Venta, related_name="items", on_delete=models.CASCADE)
    producto = models.ForeignKey(Product, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    def subtotal(self) -> Decimal:
        return self.cantidad * self.precio

    def __str__(self) -> str:
        return f"{self.producto.description} x {self.cantidad} = {self.subtotal():,.2f}"


class Abono(models.Model):
    venta = models.ForeignKey(Venta, related_name="abonos", on_delete=models.CASCADE)
    monto = models.DecimalField(max_digits=10, decimal_places=2)  # ← CORREGIDO
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self) -> str:
        return f"Abono de ${self.monto} para venta #{self.venta.numero_factura}"
