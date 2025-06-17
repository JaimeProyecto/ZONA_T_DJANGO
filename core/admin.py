from django.contrib import admin
from .models import Cliente, Product, Venta, VentaItem, Abono


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "correo", "telefono")
    search_fields = ("nombre", "correo", "telefono")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):  # ✅ Nombre correcto
    list_display = ("reference", "description", "sale_price", "stock")
    search_fields = ("reference", "description")


class ItemVentaInline(admin.TabularInline):
    model = VentaItem
    extra = 0


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = (
        "numero_factura",
        "cliente",
        "fecha",
        "total",
        "estado",
        "tipo_pago",
        "usuario",
    )
    list_filter = ("estado", "tipo_pago", "fecha")
    search_fields = ("numero_factura", "cliente__nombre")
    inlines = [ItemVentaInline]


@admin.register(Abono)
class AbonoAdmin(admin.ModelAdmin):
    list_display = ("venta", "fecha", "monto")
    list_filter = ("fecha",)
    search_fields = ("venta__numero_factura",)
