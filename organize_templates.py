import os
import shutil

BASE_DIR = os.path.join("core", "templates", "core")
RESTRUCTURE_MAP = {
    "clientes": "admin/clientes",
    "pagos": "admin/pagos",
    "products": "admin/products",
    "reportes": "admin/reportes",
    "ventas": "vendedor/ventas",
}


def move_templates():
    for src_dir, target_dir in RESTRUCTURE_MAP.items():
        src_path = os.path.join(BASE_DIR, src_dir)
        target_path = os.path.join(BASE_DIR, target_dir)
        if os.path.exists(src_path):
            os.makedirs(target_path, exist_ok=True)
            for file_name in os.listdir(src_path):
                src_file = os.path.join(src_path, file_name)
                target_file = os.path.join(target_path, file_name)
                print(f"Moviendo {src_file} -> {target_file}")
                shutil.move(src_file, target_file)
            os.rmdir(src_path)


def update_template_paths(root_dir="core"):
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".py") or file.endswith(".html"):
                file_path = os.path.join(subdir, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                updated = content
                for old, new in RESTRUCTURE_MAP.items():
                    updated = updated.replace(f"core/{old}/", f"core/{new}/")
                if updated != content:
                    print(f"Actualizando rutas en {file_path}")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(updated)


if __name__ == "__main__":
    move_templates()
    update_template_paths()
    print("\n✅ Estructura reorganizada y rutas actualizadas.")
