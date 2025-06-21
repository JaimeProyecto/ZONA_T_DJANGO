# core/urls.py
from django.urls import path
from django.shortcuts import redirect

# Vistas «globales»
from . import views

# Vistas de vendedor
from core.vendedor import views as vendedor_views

urlpatterns = [
    # --- Auth & Dashboards ---
    path("", lambda r: redirect("login/")),
    path("login/", views.login_view, name="login"),
    path("redirect-by-role/", views.redirect_by_role, name="redirect_by_role"),
    path("panel-admin/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path(
        "panel-vendedor/dashboard/", views.vendedor_dashboard, name="vendedor_dashboard"
    ),
    # --- Productos ---
    path("panel-admin/products/", views.admin_product_list, name="admin_product_list"),
    path(
        "panel-vendedor/products/",
        views.vendedor_product_list,
        name="vendedor_product_list",
    ),
    path("productos/crear/", views.product_create, name="product_create"),
    path("producto/<int:producto_id>/editar/", views.product_edit, name="product_edit"),
    path("productos/<int:pk>/eliminar/", views.product_delete, name="product_delete"),
    path("productos/cargar/", views.cargar_productos_excel, name="cargar_productos"),
    # --- Clientes ---
    path("panel-admin/clientes/", views.admin_cliente_list, name="admin_cliente_list"),
    path(
        "panel-vendedor/clientes/",
        views.vendedor_cliente_list,
        name="vendedor_cliente_list",
    ),
    path("clientes/crear/", views.cliente_create, name="cliente_create"),
    path(
        "clientes/<int:pk>/historial/",
        views.cliente_historial,
        name="cliente_historial",
    ),
    path("clientes/<int:cliente_id>/edit/", views.cliente_edit, name="cliente_edit"),
    path(
        "clientes/<int:cliente_id>/delete/", views.cliente_delete, name="cliente_delete"
    ),
    # --- Ventas Admin ---
    path("panel-admin/ventas/", views.venta_admin_list, name="venta_admin_list"),
    path(
        "panel-admin/ventas/<int:venta_id>/detalle/",
        views.venta_admin_detail,
        name="venta_admin_detail",
    ),
    # --- Ventas Vendedor ---
    path(
        "panel-vendedor/ventas/crear/", vendedor_views.crear_venta, name="venta_create"
    ),
    path(
        "panel-vendedor/ventas/print/<int:pk>/",
        vendedor_views.venta_print,
        name="venta_print",
    ),
    path(
        "panel-vendedor/ventas/",
        vendedor_views.venta_vendedor_list,
        name="venta_vendedor_list",
    ),
    path(
        "panel-vendedor/ventas/<int:venta_id>/detalle/",
        views.venta_vendedor_detail,
        name="venta_vendedor_detail",
    ),
    # --- Anular Venta ---
    path("ventas/<int:venta_id>/anular/", views.venta_delete, name="venta_delete"),
    # --- Pagos ---
    path("pagos/registrar-abono/", views.registrar_abono, name="registrar_abono"),
    path(
        "panel-admin/pagos/saldos/",
        views.saldo_pendiente_admin,
        name="saldo_pendiente_admin",
    ),
    path("pagos/saldo-pendiente/", views.saldo_pendiente, name="saldo_pendiente"),
    # --- Reportes y exportaciones ---
    path("reportes/", views.reportes_index, name="reportes_index"),
    path(
        "reportes/ventas-diarias/",
        views.reporte_ventas_diarias,
        name="reporte_ventas_diarias",
    ),
    path(
        "reportes/clientes-deuda/",
        views.reporte_clientes_con_deuda,
        name="reporte_clientes_con_deuda",
    ),
    path(
        "reportes/productos-mas-vendidos/",
        views.reporte_productos_mas_vendidos,
        name="reporte_productos_mas_vendidos",
    ),
    path(
        "reportes/ventas-diarias/exportar/<fecha>/",
        views.exportar_ventas_excel,
        name="exportar_ventas_excel",
    ),
    path(
        "exportar/clientes-deuda/",
        views.exportar_clientes_deuda_excel,
        name="exportar_clientes_deuda_excel",
    ),
    path(
        "exportar/productos-mas-vendidos/",
        views.exportar_productos_mas_vendidos_excel,
        name="exportar_productos_mas_vendidos_excel",
    ),
    path(
        "exportar/mis-ventas/",
        views.exportar_ventas_excel_vendedor,
        name="exportar_ventas_excel_vendedor",
    ),
    path(
        "exportar/ventas-admin/",
        views.exportar_ventas_excel_admin,
        name="exportar_ventas_excel_admin",
    ),
    # --- AJAX Autocomplete ---
    path("ajax/buscar-clientes/", views.buscar_clientes, name="buscar_clientes"),
    path("ajax/buscar-productos/", views.buscar_productos, name="buscar_productos"),
]
