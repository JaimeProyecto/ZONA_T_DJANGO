import json
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Sum, F, Q, Value, ExpressionWrapper, DecimalField, Count
from django.db.models.functions import Coalesce
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import localdate
from django.utils import timezone
from .forms import ProductForm, ClienteForm, AbonoForm
from .models import Cliente, Product, Venta, VentaItem, Abono
from datetime import timedelta
import openpyxl
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from datetime import datetime
from django.http import JsonResponse
from decimal import Decimal
from django.contrib.auth.decorators import user_passes_test


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


@login_required
def admin_dashboard(request):
    clientes_por_vendedor = Cliente.objects.values("creado_por__username").annotate(
        total=Count("id")
    )
    return render(
        request,
        "core/admin/admin_dashboard.html",
        {"clientes_por_vendedor": clientes_por_vendedor},
    )


@login_required
def vendedor_dashboard(request):
    return render(request, "core/vendedor/vendedor_dashboard.html")


# --- CRUD Productos ---
def admin_product_list(request):
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
        "core/admin/products/list.html",
        {
            "products": products,
            "todos_los_productos": Product.objects.all(),
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
        sale_price = request.POST.get("sale_price")
        stock_add = request.POST.get("stock_add")

        if not reference or not description:
            messages.error(request, "Todos los campos son obligatorios.")
        else:
            try:
                producto.reference = reference
                producto.description = description
                producto.purchase_price = float(purchase_price)
                producto.sale_price = float(sale_price)
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


# --- Clientes ---
@login_required
@user_passes_test(es_admin, login_url="login")
def venta_admin_list(request):
    ventas = Venta.objects.all().select_related("cliente", "usuario")
    ventas = ventas.order_by("-fecha")
    return render(
        request,
        "core/admin/ventas/list.html",
        {"ventas": ventas},
    )


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
                "sale_price": float(p.sale_price),
                "stock": p.stock,  # Agregado aquí
            }
            for p in productos
        ],
        safe=False,
    )


# ventas
@login_required
@user_passes_test(es_vendedor, login_url="login")
def crear_venta(request):
    clientes = Cliente.objects.all()
    productos = Product.objects.all().values("id", "reference", "description")

    if request.method == "POST":
        data = request.POST
        cliente_id = data.get("cliente")
        tipo_pago = data.get("tipo_pago", "contado")
        # Procesar descuento con separador de miles
        descuento_raw = data.get("descuento", "0").replace(".", "")
        descuento_mil = Decimal(descuento_raw)
        productos_json = json.loads(data.get("productos_data", "[]"))

        if not cliente_id or not productos_json:
            messages.error(
                request, "Debes seleccionar un cliente y al menos un producto."
            )
            return redirect("venta_create")

        try:
            with transaction.atomic():
                # Prefijo según tipo de pago
                if tipo_pago == "credito":
                    pref = "FC-"
                elif tipo_pago == "transferencia":
                    pref = "FT-"
                elif tipo_pago == "garantia":
                    pref = "FG-"
                else:
                    pref = "FV-"

                nro = Venta.objects.filter(tipo_pago=tipo_pago).count() + 1
                fac = f"{pref}{nro}"

                venta = Venta.objects.create(
                    cliente_id=cliente_id,
                    numero_factura=fac,
                    tipo_pago=tipo_pago,
                    usuario=request.user,
                )

                bruto = Decimal("0")
                for itm in productos_json:
                    prod = Product.objects.get(pk=itm["producto_id"])
                    cant = int(itm["cantidad"])
                    # Tomar precio ingresado manualmente
                    precio = Decimal(str(itm.get("precio", "0")))
                    if prod.stock < cant:
                        raise ValueError(f"Stock insuficiente {prod.reference}")

                    sub = precio * cant
                    VentaItem.objects.create(
                        venta=venta,
                        producto=prod,
                        cantidad=cant,
                        precio=precio,
                    )
                    prod.stock -= cant
                    prod.save()
                    bruto += sub

                # Aplicar descuento
                neto = bruto - descuento_mil
                venta.total = neto if neto > 0 else Decimal("0")
                venta.save()

                # ——— Aquí: imprimir ticket a la E200i ———
                try:
                    from escpos.printer import Usb

                    # Inicializar impresora
                    p = Usb(0x04B8, 0x0202, timeout=0)

                    # Encabezado centrado con nombre del negocio
                    p.set(align="center")
                    p.text("ZONA T\n")
                    p.set(align="left")

                    # Datos del cliente
                    p.text(f"{venta.cliente.nombre}\n")
                    p.text(f"{venta.cliente.direccion}\n")
                    p.text(f"{venta.cliente.telefono}\n")

                    # Datos de la venta
                    p.text(f"Venta N° {venta.numero_factura}\n")
                    p.text(f"Método de pago: {tipo_pago.capitalize()}\n")
                    p.text("\n")
                    p.text(
                        f"Fecha: {timezone.localtime(venta.created_at).strftime('%d/%m/%Y %H:%M')}\n"
                    )
                    p.text("-" * 32 + "\n")

                    # Encabezados de detalle
                    p.text("REF   DESC       CANT  VALOR\n")
                    p.text("-" * 32 + "\n")

                    # Detalle de ítems
                    for item in venta.items.all():
                        ref = item.producto.reference[:10]
                        desc = item.producto.description[:10]
                        line = f"{ref:10s} {desc:10s} {item.cantidad:3d} {item.precio:7.2f}\n"
                        p.text(line)

                    p.text("-" * 32 + "\n")
                    p.text(f"TOTAL: {venta.total:.2f}\n")
                    p.cut()
                except Exception as e:
                    messages.warning(
                        request, f"❗ Venta registrada, pero NO se imprimió: {e}"
                    )

                messages.success(
                    request, f"✅ Venta #{venta.numero_factura} registrada."
                )
                return redirect("venta_vendedor_list")

        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
            return redirect("venta_create")

    return render(
        request,
        "core/vendedor/ventas/create.html",
        {
            "clientes": clientes,
            "productos": list(productos),
        },
    )


@login_required
@user_passes_test(es_admin, login_url="login")
def venta_admin_detail(request, venta_id):
    venta = get_object_or_404(Venta, id=venta_id)
    return render(request, "core/admin/ventas/detail.html", {"venta": venta})


@login_required
@user_passes_test(es_vendedor, login_url="login")
def venta_vendedor_detail(request, venta_id):
    venta = get_object_or_404(Venta, id=venta_id, usuario=request.user)
    return render(request, "core/vendedor/ventas/detail.html", {"venta": venta})


# core/views.py
@login_required
@user_passes_test(es_admin, login_url="login")
def venta_admin_list(request):
    query = request.GET.get("q", "").strip()
    fecha_inicio = request.GET.get("fecha_inicio", "").strip()
    fecha_fin = request.GET.get("fecha_fin", "").strip()

    qs = (
        Venta.objects.select_related("cliente", "usuario")
        .prefetch_related("items__producto", "abonos__usuario")
        .order_by("-fecha")
    )
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
        # ganancia
        ganancia = sum(
            (item.precio - item.producto.purchase_price) * item.cantidad
            for item in v.items.all()
        )
        # último abono
        ultimo = v.abonos.order_by("-fecha").first()
        v.ultimo_abono_por = (
            ultimo.usuario.username if (ultimo and ultimo.usuario) else None
        )
        v.ultimo_abono_monto = ultimo.monto if ultimo else None
        v.ganancia = ganancia
        ventas.append(v)

    total_ventas = sum(v.total for v in ventas)
    total_ganancias = sum(v.ganancia for v in ventas)

    return render(
        request,
        "core/admin/ventas/list.html",
        {
            "ventas": ventas,
            "query": query,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "total_ventas": total_ventas,
            "total_ganancias": total_ganancias,
        },
    )


# core/views.py
@login_required
@user_passes_test(es_vendedor, login_url="login")
def venta_vendedor_list(request):
    query = request.GET.get("q", "").strip()
    fecha_inicio = request.GET.get("fecha_inicio", "").strip()
    fecha_fin = request.GET.get("fecha_fin", "").strip()

    qs = (
        Venta.objects.filter(usuario=request.user)
        .select_related("cliente")
        .prefetch_related("abonos__usuario")
        .order_by("-fecha")
    )
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
        # último abono
        ultimo = v.abonos.order_by("-fecha").first()
        v.ultimo_abono_por = (
            ultimo.usuario.username if (ultimo and ultimo.usuario) else None
        )
        v.ultimo_abono_monto = ultimo.monto if ultimo else None
        ventas.append(v)

    total_ventas = sum(v.total for v in ventas)

    return render(
        request,
        "core/vendedor/ventas/list.html",
        {
            "ventas": ventas,
            "query": query,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "total_ventas": total_ventas,
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
    venta_id = request.GET.get("venta_id")

    if request.method == "POST":
        form = AbonoForm(request.POST)
        if form.is_valid():
            abono = form.save(commit=False)
            abono.usuario = request.user
            abono.save()
            # Redirige al listado de saldos pendientes según rol
            if request.user.is_superuser:
                return redirect("saldo_pendiente_admin")
            else:
                return redirect("saldo_pendiente")
    else:
        form = AbonoForm(initial={"venta": venta_id}) if venta_id else AbonoForm()

    return render(
        request,
        "core/admin/pagos/registrar_abono.html",  # o core/vendedor/... si tienes plantilla distinta
        {"form": form},
    )


# core/views.py
@login_required
@user_passes_test(es_admin, login_url="login")
def saldo_pendiente_admin(request):
    query = request.GET.get("q", "").strip()

    qs = (
        Venta.objects.filter(tipo_pago="credito")
        .select_related("cliente", "usuario")
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
            # datos que ya tenías
            v.total_compra = v.total
            v.saldo_pendiente = saldo

            # extraigo el último abono
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
        "core/admin/pagos/saldo_pendiente.html",
        {
            "ventas": ventas,
            "query": query,
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
def reporte_clientes_con_deuda(request):
    query = request.GET.get("q", "")
    clientes = Cliente.objects.all()

    if query:
        clientes = clientes.filter(nombre__icontains=query)

    clientes_con_deuda = []

    for cliente in clientes:
        ventas = cliente.venta_set.filter(estado="activa", tipo_pago="credito")
        saldo_total = sum(venta.calcular_saldo_pendiente() for venta in ventas)
        if saldo_total > 0:
            cliente.deuda_total = saldo_total  # asignar atributo dinámico
            clientes_con_deuda.append(cliente)

    return render(
        request,
        "core/admin/reportes/clientes_con_deuda.html",
        {"clientes": clientes_con_deuda},
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


@login_required
@user_passes_test(es_admin, login_url="login")
def exportar_ventas_excel_admin(request):
    ventas = Venta.objects.select_related("cliente", "usuario").order_by("-fecha")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas Administrador"

    ws.append(
        ["Factura", "Cliente", "Tipo de Pago", "Total", "Fecha", "Estado", "Usuario"]
    )

    for v in ventas:
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

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="ventas_admin.xlsx"'
    wb.save(response)
    return response


def exportar_clientes_deuda_excel(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clientes con Deuda"

    # Cabeceras
    ws.append(["Nombre", "Teléfono", "Ciudad", "Deuda ($)"])

    clientes = Cliente.objects.all()

    for cliente in clientes:
        ventas = cliente.venta_set.filter(estado="activa", tipo_pago="credito")
        saldo_total = sum(venta.calcular_saldo_pendiente() for venta in ventas)
        if saldo_total > 0:
            ws.append(
                [cliente.nombre, cliente.telefono, cliente.ciudad, float(saldo_total)]
            )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=clientes_con_deuda.xlsx"
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
                    "sale_price": precio,
                    "stock": stock,
                },
            )

        messages.success(request, "Productos cargados correctamente.")
        return redirect("admin_product_list")

    return render(request, "core/admin/products/cargar_productos.html")
