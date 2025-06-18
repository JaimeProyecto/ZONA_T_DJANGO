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


def cliente_create(request):
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.creado_por = request.user
            cliente.save()
            if request.user.is_superuser:
                return redirect("admin_cliente_list")
            return redirect("vendedor_cliente_list")
    else:
        form = ClienteForm()
    return render(request, "core/admin/clientes/create.html", {"form": form})


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
    productos = Product.objects.all()

    if request.method == "POST":
        try:
            data = request.POST
            cliente_id = data.get("cliente")
            tipo_pago = data.get("tipo_pago", "contado")
            productos_json = json.loads(data.get("productos_data", "[]"))

            if not cliente_id or not productos_json:
                messages.error(
                    request, "Debes seleccionar un cliente y al menos un producto."
                )

                print("🚨 POST completado, usuario actual:", request.user)
                print("¿Autenticado?", request.user.is_authenticated)
                print(
                    "¿Está en grupo 'vendedor'?",
                    request.user.groups.filter(name="vendedor").exists(),
                )

                return redirect("venta_create")

            with transaction.atomic():
                # Generar número de factura único
                prefijo = "FV1-" if tipo_pago == "credito" else "FE1-"
                ultimas = Venta.objects.filter(tipo_pago=tipo_pago).count() + 1
                numero_factura = f"{prefijo}{ultimas}"

                venta = Venta.objects.create(
                    cliente_id=cliente_id,
                    numero_factura=numero_factura,
                    tipo_pago=tipo_pago,
                    usuario=request.user,
                )

                total = Decimal("0.00")
                for item in productos_json:
                    producto = Product.objects.get(pk=item["producto_id"])
                    cantidad = int(item["cantidad"])

                    if producto.stock < cantidad:
                        messages.error(
                            request,
                            f"Stock insuficiente para el producto {producto.reference}.",
                        )
                        return redirect("venta_create")

                    subtotal = producto.sale_price * cantidad

                    VentaItem.objects.create(
                        venta=venta,
                        producto=producto,
                        cantidad=cantidad,
                        precio=Decimal(str(producto.sale_price)),
                    )

                    # Actualizar stock
                    producto.stock -= cantidad
                    producto.save()
                    total += subtotal

                venta.total = total
                venta.save()

                messages.success(
                    request,
                    f"✅ Venta #{venta.numero_factura} registrada correctamente.",
                )

                if request.user.groups.filter(name="admin").exists():
                    return redirect("venta_admin_list")
                else:
                    return redirect("venta_vendedor_list")

        except Exception as e:
            messages.error(request, f"❌ Error al registrar la venta: {e}")
            return redirect("venta_create")

    productos_data = list(
        productos.values("id", "reference", "description", "sale_price")
    )

    return render(
        request,
        "core/vendedor/ventas/create.html",
        {
            "clientes": clientes,
            "productos": productos_data,
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


@login_required
@user_passes_test(es_admin, login_url="login")
def venta_admin_list(request):
    query = request.GET.get("q", "").strip()
    fecha_inicio = request.GET.get("fecha_inicio", "").strip()
    fecha_fin = request.GET.get("fecha_fin", "").strip()

    ventas = Venta.objects.all().select_related("cliente", "usuario")

    if query:
        ventas = ventas.filter(
            Q(cliente__nombre__icontains=query) | Q(numero_factura__icontains=query)
        )

    if fecha_inicio:
        ventas = ventas.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        ventas = ventas.filter(fecha__date__lte=fecha_fin)

    ventas = ventas.order_by("-fecha")

    context = {
        "ventas": ventas,
        "query": query,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }
    return render(request, "core/admin/ventas/list.html", context)


@login_required
@user_passes_test(es_vendedor, login_url="login")
def venta_vendedor_list(request):
    query = request.GET.get("q", "").strip()
    fecha_inicio = request.GET.get("fecha_inicio", "").strip()
    fecha_fin = request.GET.get("fecha_fin", "").strip()

    ventas = Venta.objects.filter(usuario=request.user).select_related("cliente")

    if query:
        ventas = ventas.filter(
            Q(cliente__nombre__icontains=query) | Q(numero_factura__icontains=query)
        )

    if fecha_inicio:
        ventas = ventas.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        ventas = ventas.filter(fecha__date__lte=fecha_fin)

    ventas = ventas.order_by("-fecha")

    return render(
        request,
        "core/vendedor/ventas/list.html",
        {
            "ventas": ventas,
            "query": query,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
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
@user_passes_test(es_admin, login_url="login")  # <— si sólo admin puede abonar
def registrar_abono(request):
    venta_id = request.GET.get("venta_id")

    if request.method == "POST":
        form = AbonoForm(request.POST)
        if form.is_valid():
            form.save()
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


@login_required
@user_passes_test(es_admin, login_url="login")
def saldo_pendiente_admin(request):
    query = request.GET.get("q", "").strip()

    ventas = (
        Venta.objects.filter(tipo_pago="credito")
        .select_related("cliente", "usuario")
        .order_by("-fecha")
    )

    if query:
        ventas = ventas.filter(
            Q(cliente__nombre__icontains=query) | Q(numero_factura__icontains=query)
        )

    # Filtrar ventas con saldo pendiente
    ventas = [v for v in ventas if v.calcular_saldo_pendiente() > 0]

    return render(
        request,
        "core/admin/pagos/saldo_pendiente.html",
        {"ventas": ventas, "query": query},
    )


@login_required
@user_passes_test(es_vendedor, login_url="login")
def saldo_pendiente(request):
    query = request.GET.get("q", "").strip()

    ventas = Venta.objects.filter(
        usuario=request.user, tipo_pago="credito"
    ).select_related("cliente")

    if query:
        ventas = ventas.filter(
            Q(cliente__nombre__icontains=query) | Q(numero_factura__icontains=query)
        )

    ventas = [v for v in ventas if v.calcular_saldo_pendiente() > 0]

    return render(
        request,
        "core/vendedor/pagos/saldo_pendiente.html",
        {"ventas": ventas, "query": query},
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
                venta.cliente.nombre_completo,
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


def exportar_productos_mas_vendidos_excel(request):
    fecha_inicio = request.GET.get("fecha_inicio")
    fecha_fin = request.GET.get("fecha_fin")

    ventas = VentaItem.objects.all()

    if fecha_inicio:
        ventas = ventas.filter(venta__fecha__gte=fecha_inicio)
    if fecha_fin:
        ventas = ventas.filter(venta__fecha__lte=fecha_fin)

    productos = (
        ventas.values("producto__descripcion")
        .annotate(total_vendido=Sum("cantidad"))
        .order_by("-total_vendido")
    )

    # Convertir a DataFrame para exportar
    data = [
        {
            "Producto": p["producto__descripcion"],
            "Unidades Vendidas": p["total_vendido"],
        }
        for p in productos
    ]
    df = pd.DataFrame(data)

    # Preparar respuesta HTTP con archivo Excel
    fecha_hora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"productos_mas_vendidos_{fecha_hora}.xlsx"

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    with pd.ExcelWriter(response, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Productos Más Vendidos")

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
