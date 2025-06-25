import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from django.db.models.functions import TruncDate
import openpyxl

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.db.models import (
    Sum,
    F,
    Q,
    Value,
    ExpressionWrapper,
    DecimalField,
    Count,
    FloatField,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from escpos.printer import Usb as EscposUsb

from .decorators import es_vendedor, es_admin

from .forms import ProductForm, ClienteForm, AbonoForm
from .models import Cliente, Product, Venta, VentaItem, Abono


# --- Login y redirección por rol ---
def login_view(request):
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        auth_login(request, user)
        return redirect("redirect_by_role")
    return render(request, "core/login.html", {"form": form})


@login_required
def redirect_by_role(request):
    if request.user.is_superuser:
        return redirect("admin_dashboard")
    return redirect("vendedor_dashboard")


# core/views.py
@login_required
@user_passes_test(es_admin, login_url="login")
def admin_dashboard(request):
    hoy = date.today()

    # Clientes por vendedor (ya lo tienes)
    clientes_por_vendedor = Cliente.objects.values("creado_por__username").annotate(
        total=Count("id")
    )

    # 1️⃣ Ventas últimos 7 días
    fechas = [hoy - timedelta(days=i) for i in range(6, -1, -1)]
    qs_semana = (
        Venta.objects.filter(fecha__date__gte=hoy - timedelta(days=6), estado="activa")
        .annotate(dia=TruncDate("fecha"))
        .values("dia")
        .annotate(total_dia=Sum("total"))
        .order_by("dia")
    )
    mapa = {v["dia"].strftime("%d/%m"): v["total_dia"] for v in qs_semana}
    serie_ventas = [mapa.get(d.strftime("%d/%m"), 0) for d in fechas]
    fechas_semana = [d.strftime("%d/%m") for d in fechas]

    # 2️⃣ Tipos de pago últimos 30 días
    qs_pagos = (
        Venta.objects.filter(fecha__date__gte=hoy - timedelta(days=30))
        .values("tipo_pago")
        .annotate(cantidad=Count("id"))
    )
    labels_pagos = [p["tipo_pago"].capitalize() for p in qs_pagos]
    datos_pagos = [p["cantidad"] for p in qs_pagos]

    # 3️⃣ Ingresos mes actual
    ingresos_mes = (
        Venta.objects.filter(
            fecha__year=hoy.year, fecha__month=hoy.month, estado="activa"
        ).aggregate(total=Sum("total"))["total"]
        or 0
    )

    # 4️⃣ Stock bajo
    bajo_stock = Product.objects.filter(stock__lte=5).count()

    return render(
        request,
        "core/admin/admin_dashboard.html",
        {
            "clientes_por_vendedor": clientes_por_vendedor,
            "fechas_semana": fechas_semana,
            "serie_ventas": serie_ventas,
            "labels_pagos": labels_pagos,
            "datos_pagos": datos_pagos,
            "ingresos_mes": ingresos_mes,
            "bajo_stock": bajo_stock,
        },
    )


@login_required
@user_passes_test(es_vendedor, login_url="login")
def vendedor_dashboard(request):
    """
    Panel de vendedor con KPIs, mini–charts y listados.
    """
    hoy = date.today()

    # 1️⃣ Ventas diarias últimos 7 días (solo propias y activas)
    fechas_semana = [hoy - timedelta(days=i) for i in range(6, -1, -1)]
    ventas_semana_qs = (
        Venta.objects.filter(
            usuario=request.user,
            estado="activa",
            fecha__date__gte=hoy - timedelta(days=6),
        )
        .annotate(dia=TruncDate("fecha"))
        .values("dia")
        .annotate(total_dia=Sum("total"))
        .order_by("dia")
    )
    mapa = {v["dia"].strftime("%Y-%m-%d"): v["total_dia"] for v in ventas_semana_qs}
    serie_ventas = [mapa.get(d.strftime("%Y-%m-%d"), 0) for d in fechas_semana]

    # 2️⃣ Proporción por tipo de pago en últimos 30 días
    pagos_qs = (
        Venta.objects.filter(
            usuario=request.user, fecha__date__gte=hoy - timedelta(days=30)
        )
        .values("tipo_pago")
        .annotate(cantidad=Count("id"))
    )
    labels_pagos = [p["tipo_pago"].capitalize() for p in pagos_qs]
    datos_pagos = [p["cantidad"] for p in pagos_qs]

    # 3️⃣ KPI: Ventas Hoy
    ventas_hoy = Venta.objects.filter(
        usuario=request.user, fecha__date=hoy, estado="activa"
    )
    ventas_hoy_count = ventas_hoy.count()
    ventas_hoy_total = ventas_hoy.aggregate(total=Sum("total"))["total"] or 0

    # 4️⃣ KPI: Ingresos Mes
    ingresos_mes = (
        Venta.objects.filter(
            usuario=request.user,
            fecha__year=hoy.year,
            fecha__month=hoy.month,
            estado="activa",
        ).aggregate(total=Sum("total"))["total"]
        or 0
    )

    # 5️⃣ KPI: Abonos Pendientes (crédito con saldo > 0)
    creditos = Venta.objects.filter(
        usuario=request.user, tipo_pago="credito", estado="activa"
    )
    abonos_pendientes = sum(1 for v in creditos if v.calcular_saldo_pendiente() > 0)

    # 6️⃣ KPI: Productos Agotándose (top 5 vendidos con stock ≤ 5)
    top_productos = (
        VentaItem.objects.filter(venta__usuario=request.user)
        .values("producto")
        .annotate(total_vend=Sum("cantidad"))
        .order_by("-total_vend")[:5]
    )
    prod_ids = [p["producto"] for p in top_productos]
    mis_bajo_stock_count = Product.objects.filter(id__in=prod_ids, stock__lte=5).count()

    # 7️⃣ Últimas 5 ventas
    ventas_recientes = Venta.objects.filter(usuario=request.user).order_by("-fecha")[:5]

    return render(
        request,
        "core/vendedor/vendedor_dashboard.html",
        {
            "fechas_semana": [d.strftime("%d/%m") for d in fechas_semana],
            "serie_ventas": serie_ventas,
            "labels_pagos": labels_pagos,
            "datos_pagos": datos_pagos,
            "ventas_hoy_count": ventas_hoy_count,
            "ventas_hoy_total": ventas_hoy_total,
            "ingresos_mes": ingresos_mes,
            "abonos_pendientes": abonos_pendientes,
            "mis_bajo_stock_count": mis_bajo_stock_count,
            "ventas_recientes": ventas_recientes,
        },
    )


# --- CRUD Productos ---
@login_required
@user_passes_test(es_admin, login_url="login")
def admin_product_list(request):
    """
    Muestra el listado de productos con filtros, totales de stock y valor de inventario.
    """
    query = request.GET.get("buscar", "").strip()
    qs = Product.objects.all()
    if query:
        qs = qs.filter(Q(reference__icontains=query) | Q(description__icontains=query))
    products = qs.order_by("reference")

    # Total de stock
    total_stock = products.aggregate(total_stock=Sum("stock"))["total_stock"] or 0

    # Total valor de inventario = sum(purchase_price * stock)
    total_valor_inventario = (
        products.aggregate(
            total_valor=Sum(F("purchase_price") * F("stock"), output_field=FloatField())
        )["total_valor"]
        or 0
    )

    return render(
        request,
        "core/admin/products/list.html",
        {
            "products": products,
            "query": query,
            "total_stock": total_stock,
            "total_valor_inventario": total_valor_inventario,
        },
    )


def vendedor_product_list(request):
    query = request.GET.get("buscar", "").strip()
    products = (
        Product.objects.filter(
            Q(reference__icontains=query) | Q(description__icontains=query)
        )
        if query
        else Product.objects.all()
    )

    return render(
        request,
        "core/vendedor/products/list.html",  # plantilla específica para vendedor
        {
            "products": products,
        },
    )


def product_create(request):
    form = ProductForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("admin_product_list")  # Asegúrate de que esta URL exista
    return render(request, "core/admin/products/create.html", {"form": form})


def product_edit(request, producto_id):
    producto = get_object_or_404(Product, id=producto_id)

    if request.method == "POST":
        reference = request.POST.get("reference", "").strip()
        description = request.POST.get("description", "").strip()
        purchase_price = request.POST.get("purchase_price")
        stock_add = request.POST.get("stock_add")

        if not reference or not description:
            messages.error(request, "Todos los campos son obligatorios.")
        else:
            try:
                producto.reference = reference
                producto.description = description
                producto.purchase_price = float(purchase_price)
                producto.stock += int(stock_add)
                producto.save()

                messages.success(request, "✅ Producto actualizado correctamente.")
                return redirect(
                    "admin_products_list"
                )  # Cambia esto si el nombre de la URL es diferente
            except Exception as e:
                messages.error(request, f"Error al actualizar el producto: {str(e)}")

    return render(request, "core/admin/products/edit.html", {"producto": producto})


def product_delete(request, pk):
    prod = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        prod.delete()
        return redirect("admin_product_list")
    return render(request, "core/admin/products/delete.html", {"product": prod})


# utils para validar roles
def es_admin(user):
    return user.is_authenticated and user.is_superuser


def es_vendedor(user):
    return user.is_authenticated and not user.is_superuser


@login_required
@user_passes_test(es_vendedor, login_url="login")
def vendedor_cliente_list(request):
    query = request.GET.get("q", "").strip()
    clientes = (
        Cliente.objects.filter(Q(nombre__icontains=query) | Q(cedula__icontains=query))
        if query
        else Cliente.objects.all()
    )

    return render(
        request,
        "core/vendedor/clientes/list.html",
        {"clientes": clientes, "query": query},
    )


@login_required
@user_passes_test(es_admin, login_url="login")
def admin_cliente_list(request):
    query = request.GET.get("q", "").strip()
    clientes = (
        Cliente.objects.filter(Q(nombre__icontains=query) | Q(cedula__icontains=query))
        if query
        else Cliente.objects.all()
    )

    return render(
        request,
        "core/admin/clientes/list.html",
        {"clientes": clientes, "query": query},
    )


# core/views.py
@login_required
def cliente_create(request):
    # Inicializamos el formulario con POST o en blanco
    form = ClienteForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.creado_por = request.user
            cliente.save()
            # Redirige según rol
            if request.user.is_superuser:
                return redirect("admin_cliente_list")
            return redirect("vendedor_cliente_list")
        # Si POST pero inválido, caerá al render de abajo mostrando errores

    # Para GET o POST inválido, renderizamos el formulario
    template = (
        "core/admin/clientes/create.html"
        if request.user.is_superuser
        else "core/vendedor/clientes/create.html"
    )
    return render(request, template, {"form": form})


def cliente_historial(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    ventas = Venta.objects.filter(cliente=cliente)
    return render(
        request,
        "core/admin/clientes/historial.html",
        {"cliente": cliente, "ventas": ventas},
    )


@login_required
def cliente_edit(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            if request.user.is_superuser:
                return redirect("admin_cliente_list")
            return redirect("vendedor_cliente_list")
    else:
        form = ClienteForm(instance=cliente)

    return render(
        request, "core/admin/clientes/edit.html", {"form": form, "cliente": cliente}
    )


@login_required
def cliente_delete(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if request.method == "POST":
        cliente.delete()
        if request.user.is_superuser:
            return redirect("admin_cliente_list")
        return redirect("vendedor_cliente_list")
    return render(request, "core/admin/clientes/delete.html", {"cliente": cliente})


# --- Ventas ---
@login_required
def buscar_clientes(request):
    term = request.GET.get("q") or request.GET.get("term") or ""
    clientes = Cliente.objects.filter(nombre__icontains=term)
    return JsonResponse(
        [{"id": c.id, "nombre": c.nombre, "cedula": c.cedula} for c in clientes],
        safe=False,
    )


def buscar_productos(request):
    term = request.GET.get("q") or request.GET.get("term") or ""
    productos = Product.objects.filter(
        Q(reference__icontains=term) | Q(description__icontains=term)
    )
    return JsonResponse(
        [
            {
                "id": p.id,
                "reference": p.reference,
                "description": p.description,
                "stock": p.stock,  # Agregado aquí
            }
            for p in productos
        ],
        safe=False,
    )


# ventas
# core/views.py
def _abrir_impresora_usb():
    """
    Intenta detectar cualquier impresora USB de clase impresora (bDeviceClass == 7).
    Si no hay PyUSB o no encuentra ninguna, cae al fallback definido en settings.
    """
    try:
        import usb.core
    except ImportError:
        usb = None

    if usb:
        for dev in usb.core.find(
            find_all=True, custom_match=lambda d: d.bDeviceClass == 7
        ):
            try:
                return EscposUsb(
                    dev.idVendor, dev.idProduct, timeout=settings.ESC_POS_USB_TIMEOUT
                )
            except Exception:
                continue

    # Fallback a los IDs en settings
    return EscposUsb(
        settings.ESC_POS_USB_VENDOR,
        settings.ESC_POS_USB_PRODUCT,
        timeout=settings.ESC_POS_USB_TIMEOUT,
    )


@login_required
@user_passes_test(es_vendedor, login_url="login")
def crear_venta(request):
    if request.method == "GET":
        return render(
            request,
            "core/vendedor/ventas/create.html",
            {
                "clientes": Cliente.objects.all(),
                "productos": Product.objects.values("id", "reference", "description"),
            },
        )

    data = request.POST
    cliente_id = data.get("cliente")
    productos_json = json.loads(data.get("productos_data", "[]"))
    descuento = Decimal(data.get("descuento", "0").replace(".", ""))
    tipo_pago = data.get("tipo_pago", "contado")

    if not cliente_id or not productos_json:
        messages.error(request, "Debes seleccionar un cliente y al menos un producto.")
        return redirect("venta_create")

    try:
        with transaction.atomic():
            pref = {"credito": "FC1-", "transferencia": "FT1-", "garantia": "FG1-"}.get(
                tipo_pago, "FV1-"
            )
            nro = Venta.objects.filter(tipo_pago=tipo_pago).count() + 1
            venta = Venta.objects.create(
                cliente_id=cliente_id,
                numero_factura=f"{pref}{nro}",
                tipo_pago=tipo_pago,
                usuario=request.user,
            )

            bruto = Decimal(0)
            for itm in productos_json:
                prod = Product.objects.get(pk=itm["producto_id"])
                cant = int(itm["cantidad"])
                precio = Decimal(str(itm.get("precio", "0")))

                if prod.stock < cant:
                    raise ValueError(f"Stock insuficiente {prod.reference}")

                sub = precio * cant
                VentaItem.objects.create(
                    venta=venta, producto=prod, cantidad=cant, precio=precio
                )
                prod.stock -= cant
                prod.save()
                bruto += sub

            venta.total = max(bruto - descuento, Decimal(0))
            venta.save()

        messages.success(request, f"✅ Venta #{venta.numero_factura} registrada.")
        return redirect("venta_vendedor_list")

    except Exception as e:
        messages.error(request, f"❌ Error al registrar la venta: {e}")
        return redirect("venta_create")


@login_required
@user_passes_test(es_vendedor, login_url="login")
def imprimir_venta(request, venta_id):
    """
    Vista legacy de impresión directa via USB.
    La dejamos por compatibilidad, pero recomendamos usar `ticket_venta`.
    """
    venta = get_object_or_404(Venta, pk=venta_id)
    try:
        p = _abrir_impresora_usb()
        p.set(align="center")
        p.text("ZONA T\n")
        p.set(align="left")
        p.text(
            f"{venta.cliente.nombre}\n{venta.cliente.direccion}\n{venta.cliente.telefono}\n"
        )
        p.text(
            f"Venta N° {venta.numero_factura}\nMétodo: {venta.tipo_pago.capitalize()}\n"
        )
        p.text(f"Fecha: {timezone.localtime(venta.created_at):%d/%m/%Y %H:%M}\n")
        p.text("-" * 32 + "\n")
        p.text("REF   DESC       CANT  VALOR\n")
        p.text("-" * 32 + "\n")
        for item in venta.items.all():
            ref = item.producto.reference[:10]
            desc = item.producto.description[:10]
            p.text(f"{ref:10s} {desc:10s} {item.cantidad:3d} {item.precio:7.2f}\n")
        p.text("-" * 32 + "\n")
        p.text(f"TOTAL: {venta.total:.2f}\n")
        p.cut()
        messages.success(request, "🖨️ Tirilla enviada a la impresora.")
    except Exception as e:
        messages.warning(request, f"❗ Venta registrada, pero NO se imprimió: {e}")
    return redirect("venta_vendedor_list")


@login_required
@user_passes_test(
    lambda u: u.is_authenticated and (es_vendedor(u) or es_admin(u)), login_url="login"
)
def ticket_venta(request, venta_id):
    """
    Genera un ticket HTML con @page size:80mm y window.print(),
    reutilizable por vendedor y administrador.
    """
    venta = get_object_or_404(Venta, pk=venta_id)
    return render(request, "core/print.html", {"venta": venta})


# core/views.py
@login_required
@user_passes_test(es_admin, login_url="login")
def venta_admin_list(request):
    query = request.GET.get("q", "").strip()
    tipo_pago = request.GET.get("tipo_pago", "")
    fecha_inicio = parse_date(request.GET.get("fecha_inicio", ""))
    fecha_fin = parse_date(request.GET.get("fecha_fin", ""))

    qs = (
        Venta.objects.select_related("cliente", "usuario")
        .prefetch_related("items__producto", "abonos__usuario")
        .order_by("-fecha")
    )

    if query:
        qs = qs.filter(
            Q(cliente__nombre__icontains=query) | Q(numero_factura__icontains=query)
        )
    if tipo_pago:
        qs = qs.filter(tipo_pago=tipo_pago)
    if fecha_inicio:
        qs = qs.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha__date__lte=fecha_fin)

    ventas = []
    for v in qs:
        # Cálculo de ganancia
        v.ganancia = sum(
            (item.precio - item.producto.purchase_price) * item.cantidad
            for item in v.items.all()
        )
        # Último abono
        ultimo = v.abonos.order_by("-fecha").first()
        v.ultimo_abono_monto = ultimo.monto if ultimo else None
        v.ultimo_abono_por = (
            ultimo.usuario.username if (ultimo and ultimo.usuario) else None
        )
        ventas.append(v)

    total_ventas = sum(v.total for v in ventas)
    total_ganancias = sum(v.ganancia for v in ventas)

    # Opciones para el filtro de tipo de pago, tomadas del propio campo
    tipo_pago = [("", "Todos")] + list(Venta._meta.get_field("tipo_pago").choices)

    return render(
        request,
        "core/admin/ventas/list.html",
        {
            "ventas": ventas,
            "query": query,
            "tipo_pago": tipo_pago,
            "fecha_inicio": fecha_inicio and fecha_inicio.strftime("%Y-%m-%d"),
            "fecha_fin": fecha_fin and fecha_fin.strftime("%Y-%m-%d"),
            "total_ventas": total_ventas,
            "total_ganancias": total_ganancias,
        },
    )


# core/views.py
@login_required
@user_passes_test(es_vendedor, login_url="login")
def venta_vendedor_list(request):
    # 1. Parámetros de búsqueda y fecha
    query = request.GET.get("q", "").strip()
    fecha_inicio = parse_date(request.GET.get("fecha_inicio", ""))
    fecha_fin = parse_date(request.GET.get("fecha_fin", ""))

    # 2. Queryset base
    qs = (
        Venta.objects.filter(usuario=request.user)
        .select_related("cliente")
        .prefetch_related("items__producto", "abonos__usuario")
        .order_by("-fecha")
    )

    # 3. Filtros
    if query:
        qs = qs.filter(
            Q(cliente__nombre__icontains=query) | Q(numero_factura__icontains=query)
        )
    if fecha_inicio:
        qs = qs.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha__date__lte=fecha_fin)

    # 4. Construcción de la lista con ganancia y último abono
    ventas = []
    for v in qs:
        # Ganancia = suma de (precio_venta – precio_compra) * cantidad
        v.ganancia = sum(
            (item.precio - item.producto.purchase_price) * item.cantidad
            for item in v.items.all()
        )
        # Último abono
        ultimo = v.abonos.order_by("-fecha").first()
        v.ultimo_abono_monto = ultimo.monto if ultimo else None
        v.ultimo_abono_por = (
            ultimo.usuario.username if (ultimo and ultimo.usuario) else None
        )
        ventas.append(v)

    # 5. Totales acumulados
    total_ventas = sum(v.total for v in ventas)
    total_ganancias = sum(v.ganancia for v in ventas)

    # 6. Render
    return render(
        request,
        "core/vendedor/ventas/list.html",
        {
            "ventas": ventas,
            "query": query,
            "fecha_inicio": fecha_inicio and fecha_inicio.strftime("%Y-%m-%d"),
            "fecha_fin": fecha_fin and fecha_fin.strftime("%Y-%m-%d"),
            "total_ventas": total_ventas,
            "total_ganancias": total_ganancias,
        },
    )


def detalle_venta(request, venta_id):
    venta = get_object_or_404(Venta, id=venta_id)
    items = VentaItem.objects.filter(venta=venta)
    return render(
        request,
        "core/admin/ventas/detail.html",
        {
            "venta": venta,
            "items": items,
        },
    )


@login_required
def venta_delete(request, venta_id):
    venta = get_object_or_404(Venta, id=venta_id)

    if venta.estado == "anulada":
        messages.warning(request, "Esta venta ya está anulada.")
        return redirect(
            "venta_admin_list" if request.user.is_superuser else "venta_vendedor_list"
        )

    try:
        with transaction.atomic():
            for item in venta.items.all():
                producto = item.producto
                producto.stock += item.cantidad
                producto.save()

            venta.estado = "anulada"
            venta.save()

            messages.success(
                request, "✅ Venta anulada correctamente. El stock fue restaurado."
            )
    except Exception as e:
        messages.error(request, f"❌ Error al anular la venta: {str(e)}")

    return redirect(
        "venta_admin_list" if request.user.is_superuser else "venta_vendedor_list"
    )


# --- Pagos ---
@login_required
def registrar_abono(request):
    venta = None
    venta_id = request.GET.get("venta_id")
    if venta_id:
        venta = get_object_or_404(Venta, pk=venta_id)

    if request.method == "POST":
        form = AbonoForm(request.POST)
        if form.is_valid():
            abono = form.save(commit=False)
            abono.usuario = request.user
            abono.save()
            if request.user.is_superuser:
                return redirect("saldo_pendiente_admin")
            return redirect("saldo_pendiente")
    else:
        form = AbonoForm(initial={"venta": venta_id}) if venta_id else AbonoForm()

    return render(
        request, "core/admin/pagos/registrar_abono.html", {"form": form, "venta": venta}
    )


# core/views.py
@login_required
@user_passes_test(es_admin, login_url="login")
def saldo_pendiente_admin(request):
    query = request.GET.get("q", "").strip()
    fecha_inicio = parse_date(request.GET.get("fecha_inicio", ""))  # convierte ISO-date
    fecha_fin = parse_date(request.GET.get("fecha_fin", ""))

    qs = (
        Venta.objects.filter(tipo_pago="credito", estado="activa")
        .select_related("cliente")
        .prefetch_related("abonos__usuario")
        .order_by("-fecha")
    )

    # filtros
    if query:
        qs = qs.filter(
            Q(cliente__nombre__icontains=query) | Q(numero_factura__icontains=query)
        )
    if fecha_inicio:
        qs = qs.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha__date__lte=fecha_fin)

    ventas = []
    for v in qs:
        saldo = v.calcular_saldo_pendiente()
        if saldo > 0:
            v.total_compra = v.total
            v.saldo_pendiente = saldo
            ultimo = v.abonos.order_by("-fecha").first()
            v.ultimo_abono_monto = ultimo.monto if ultimo else None
            v.ultimo_abono_por = (
                ultimo.usuario.username if (ultimo and ultimo.usuario) else None
            )
            v.ultimo_abono_fecha = ultimo.fecha if ultimo else None
            ventas.append(v)

    total_deuda = sum(v.saldo_pendiente for v in ventas)

    return render(
        request,
        "core/admin/pagos/saldo_pendiente.html",
        {
            "ventas": ventas,
            "query": query,
            "fecha_inicio": fecha_inicio and fecha_inicio.strftime("%Y-%m-%d"),
            "fecha_fin": fecha_fin and fecha_fin.strftime("%Y-%m-%d"),
            "total_deuda": total_deuda,
        },
    )


@login_required
@user_passes_test(es_vendedor, login_url="login")
def saldo_pendiente(request):
    query = request.GET.get("q", "").strip()

    qs = (
        Venta.objects.filter(usuario=request.user, tipo_pago="credito")
        .select_related("cliente")
        .order_by("-fecha")
    )
    if query:
        qs = qs.filter(
            Q(cliente__nombre__icontains=query) | Q(numero_factura__icontains=query)
        )

    ventas = []
    for v in qs:
        saldo = v.calcular_saldo_pendiente()
        if saldo > 0:
            v.total_compra = v.total
            v.saldo_pendiente = saldo

            ultimo = v.abonos.order_by("-fecha").first()
            if ultimo:
                v.ultimo_abono_monto = ultimo.monto
                v.ultimo_abono_por = ultimo.usuario.username if ultimo.usuario else None
                v.ultimo_abono_fecha = ultimo.fecha
            else:
                v.ultimo_abono_monto = None
                v.ultimo_abono_por = None
                v.ultimo_abono_fecha = None

            ventas.append(v)

    total_deuda = sum(v.saldo_pendiente for v in ventas)

    return render(
        request,
        "core/vendedor/pagos/saldo_pendiente.html",
        {
            "ventas": ventas,
            "query": query,
            "total_deuda": total_deuda,
        },
    )


# --- Reportes ---
# Reporte 1: Reporte de ventas diarias
@login_required
def reporte_ventas_diarias(request):
    fecha_str = request.GET.get("fecha")
    if fecha_str:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    else:
        fecha = timezone.now().date()

    ventas = (
        Venta.objects.filter(fecha__date=fecha, estado="activa")
        .select_related("cliente", "usuario")
        .prefetch_related("items__producto")
    )

    total_dia = sum(venta.total for venta in ventas)

    return render(
        request,
        "core/admin/reportes/reporte_ventas_diarias.html",
        {
            "ventas": ventas,
            "fecha": fecha.strftime("%Y-%m-%d"),
            "total_dia": total_dia,
        },
    )


# Reporte 2: Clientes con deuda
@login_required
@user_passes_test(es_admin, login_url="login")
def reporte_clientes_con_deuda(request):
    query = request.GET.get("q", "").strip()

    # 1) Partimos de ventas a crédito activas
    qs = (
        Venta.objects.filter(estado="activa", tipo_pago="credito")
        .select_related("cliente", "usuario")
        .prefetch_related("abonos__usuario")
        .order_by("-fecha")
    )

    # 2) Filtramos por nombre de cliente o número de factura
    if query:
        qs = qs.filter(
            Q(cliente__nombre__icontains=query) | Q(numero_factura__icontains=query)
        )

    # 3) Construimos la lista de "rep" con todos los atributos que usa tu template
    ventas_con_deuda = []
    for v in qs:
        saldo = v.calcular_saldo_pendiente()
        if saldo > 0:
            # último abono
            ultimo = v.abonos.order_by("-fecha").first()

            # Creamos un objeto dinámico (podrías usar SimpleNamespace o hasta dict)
            v.factura_id = v.id
            v.factura_numero = v.numero_factura
            v.cliente_nombre = v.cliente.nombre
            v.total_compra = v.total
            v.saldo_pendiente = saldo
            v.monto_ultimo_abono = ultimo.monto if ultimo else None
            v.registrado_por = (
                ultimo.usuario.username if (ultimo and ultimo.usuario) else None
            )
            v.fecha_hora_abono = ultimo.fecha if ultimo else None

            ventas_con_deuda.append(v)

    return render(
        request,
        "core/admin/reportes/clientes_con_deuda.html",
        {
            "clientes": ventas_con_deuda,
            "query": query,
        },
    )


# Reporte 3: Productos más vendidos
def reporte_productos_mas_vendidos(request):
    fecha_inicio = request.GET.get("fecha_inicio")
    fecha_fin = request.GET.get("fecha_fin")

    ventas = VentaItem.objects.filter(venta__estado="activa")

    if fecha_inicio:
        ventas = ventas.filter(venta__fecha__gte=fecha_inicio)
    if fecha_fin:
        ventas = ventas.filter(venta__fecha__lte=fecha_fin)

    productos = (
        ventas.values("producto__description")
        .annotate(total_vendido=Sum("cantidad"))
        .order_by("-total_vendido")
    )

    for p in productos:
        p["nombre"] = p.pop("producto__description")

    return render(
        request,
        "core/admin/reportes/productos_mas_vendidos.html",
        {"productos": productos},
    )


# Exportar
def exportar_ventas_excel(request, fecha):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    ventas = Venta.objects.filter(fecha__date=fecha_obj)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas Diarias"

    ws.append(["Cliente", "Fecha", "Total"])
    for venta in ventas:
        ws.append(
            [
                venta.cliente.nombre,
                venta.fecha.strftime("%Y-%m-%d"),
                float(venta.total),
            ]
        )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f"attachment; filename=ventas_{fecha}.xlsx"
    wb.save(response)
    return response


# core/views.py
@login_required
@user_passes_test(es_admin, login_url="login")
def exportar_ventas_excel_admin(request):
    """
    Exporta a Excel las ventas del administrador, respetando los mismos filtros
    de búsqueda y rango de fechas que en la lista de ventas.
    """
    # 1) Parámetros de filtro GET
    q = request.GET.get("q", "").strip()
    fecha_inicio = parse_date(request.GET.get("fecha_inicio", ""))
    fecha_fin = parse_date(request.GET.get("fecha_fin", ""))

    # 2) Queryset base
    qs = Venta.objects.select_related("cliente", "usuario").order_by("-fecha")

    # 3) Aplicar filtros idénticos a los de la vista de listado
    if q:
        qs = qs.filter(Q(cliente__nombre__icontains=q) | Q(numero_factura__icontains=q))
    if fecha_inicio:
        qs = qs.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha__date__lte=fecha_fin)

    # 4) Preparar el workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas Administrador"

    # 5) Cabecera
    ws.append(
        ["Factura", "Cliente", "Tipo de Pago", "Total", "Fecha", "Estado", "Usuario"]
    )

    # 6) Filas de datos
    for v in qs:
        ws.append(
            [
                v.numero_factura,
                v.cliente.nombre,
                v.tipo_pago.capitalize(),
                float(v.total),
                v.fecha.strftime("%Y-%m-%d %H:%M"),
                v.estado.capitalize(),
                v.usuario.username if v.usuario else "—",
            ]
        )

    # 7) Streaming de la respuesta
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="ventas_admin.xlsx"'
    wb.save(response)
    return response


@login_required
@user_passes_test(es_admin, login_url="login")
def exportar_clientes_deuda_excel(request):
    # 1. Creamos el libro y hoja
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clientes con Deuda"

    # 2. Cabeceras
    ws.append(["Nombre", "Teléfono", "Dirección", "Deuda ($)"])

    # 3. Recorremos clientes y calculamos deuda
    for cliente in Cliente.objects.all():
        ventas = cliente.venta_set.filter(estado="activa", tipo_pago="credito")
        saldo_total = sum(venta.calcular_saldo_pendiente() for venta in ventas)
        if saldo_total > 0:
            ws.append(
                [
                    cliente.nombre,
                    cliente.telefono,
                    cliente.direccion,  # <— ahora usamos 'direccion'
                    float(saldo_total),
                ]
            )

    # 4. Devolvemos el Excel al cliente
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="clientes_con_deuda.xlsx"'
    wb.save(response)
    return response


# core/views.py
def exportar_productos_mas_vendidos_excel(request):
    fecha_inicio = request.GET.get("fecha_inicio")
    fecha_fin = request.GET.get("fecha_fin")

    # 1. Filtra los items de venta según fechas (si las proporcionas)
    items = VentaItem.objects.select_related("producto", "venta")
    if fecha_inicio:
        items = items.filter(venta__fecha__date__gte=fecha_inicio)
    if fecha_fin:
        items = items.filter(venta__fecha__date__lte=fecha_fin)

    # 2. Agrupa por producto__description (campo correcto) y suma cantidades
    productos = (
        items.values("producto__description")
        .annotate(total_vendido=Sum("cantidad"))
        .order_by("-total_vendido")
    )

    # 3. Crea el Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Productos Más Vendidos"

    # Cabecera
    ws.append(["Producto", "Unidades Vendidas"])
    for p in productos:
        ws.append([p["producto__description"], p["total_vendido"]])

    # 4. Envía el archivo al cliente
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=productos_mas_vendidos.xlsx"
    wb.save(response)
    return response


def reportes_index(request):
    return render(request, "core/admin/reportes/index.html")


def vista_reportes(request):
    return render(request, "core/admin/reportes/reportes_inicio.html")


# carga masiva


def limpiar_valor(valor):
    if isinstance(valor, (int, float)):
        return valor
    valor_str = (
        str(valor)
        .replace("$", "")
        .replace(",", "")
        .replace("(", "-")
        .replace(")", "")
        .strip()
    )
    try:
        return float(valor_str)
    except ValueError:
        return 0  # O puedes usar: raise ValueError("Valor inválido en Excel")


@login_required
@user_passes_test(es_vendedor, login_url="login")
def exportar_ventas_excel_vendedor(request):
    ventas = (
        Venta.objects.filter(usuario=request.user)
        .select_related("cliente")
        .order_by("-fecha")
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mis Ventas"

    # Encabezados
    ws.append(["Factura", "Cliente", "Tipo de Pago", "Total", "Fecha", "Estado"])

    for v in ventas:
        ws.append(
            [
                v.numero_factura,
                v.cliente.nombre,
                v.tipo_pago.capitalize(),
                float(v.total),
                v.fecha.strftime("%Y-%m-%d %H:%M"),
                v.estado.capitalize(),
            ]
        )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="mis_ventas.xlsx"'
    wb.save(response)
    return response


def cargar_productos_excel(request):
    if request.method == "POST" and request.FILES.get("archivo"):
        archivo = request.FILES["archivo"]

        wb = openpyxl.load_workbook(archivo)
        hoja = wb.active

        for fila in hoja.iter_rows(min_row=2, values_only=True):
            referencia, descripcion, valor_compra, precio, stock = fila

            # Limpiar valores contables o con formato
            valor_compra = limpiar_valor(valor_compra)
            precio = limpiar_valor(precio)
            stock = int(limpiar_valor(stock))

            # Validar que el stock no sea negativo
            if stock < 0:
                continue  # puedes usar messages.warning para avisar si quieres

            Product.objects.update_or_create(
                reference=referencia,
                defaults={
                    "description": descripcion,
                    "purchase_price": valor_compra,
                    "stock": stock,
                },
            )

        messages.success(request, "Productos cargados correctamente.")
        return redirect("admin_product_list")

    return render(request, "core/admin/products/cargar_productos.html")


@login_required
@user_passes_test(es_admin, login_url="login")
def exportar_productos_excel(request):
    """
    Exporta a Excel el listado filtrado de productos, incluyendo valor de inventario.
    """
    query = request.GET.get("buscar", "").strip()
    qs = Product.objects.all()
    if query:
        qs = qs.filter(Q(reference__icontains=query) | Q(description__icontains=query))
    products = qs.order_by("reference")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Productos"

    # Cabecera
    ws.append(
        ["Referencia", "Descripción", "Precio de Compra", "Stock", "Valor Inventario"]
    )

    # Filas
    for p in products:
        ws.append(
            [
                p.reference,
                p.description,
                float(p.purchase_price),
                p.stock,
                float(p.purchase_price * p.stock),
            ]
        )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="productos.xlsx"'
    wb.save(response)
    return response


# core/views.py
@login_required
@user_passes_test(es_admin, login_url="login")
def exportar_clientes_excel(request):
    """
    Exporta a Excel el listado de clientes filtrado por 'q' (nombre o cédula).
    """
    # 1) Obtener término de búsqueda
    q = request.GET.get("q", "").strip()

    # 2) Queryset inicial y posible filtro
    qs = Cliente.objects.all().order_by("nombre")
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(cedula__icontains=q))

    # 3) Crear workbook y hoja
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clientes"

    # 4) Cabecera
    ws.append(
        ["ID", "Nombre", "Cédula", "Teléfono", "Dirección", "Email", "Creado Por"]
    )

    # 5) Filas de datos
    for c in qs:
        ws.append(
            [
                c.id,
                c.nombre,
                c.cedula,
                c.telefono,
                c.direccion,
                c.email or "",
                c.creado_por.username if c.creado_por else "",
            ]
        )

    # 6) Preparar respuesta HTTP
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="clientes.xlsx"'
    wb.save(response)
    return response
