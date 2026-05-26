"""
Script de arranque para Railway.
Resuelve el problema de BD creada con db.create_all() sin historial de migraciones:
1. Si Alembic no tiene ninguna revisión registrada → sella en la migración inicial
2. Ejecuta flask db upgrade para aplicar solo las migraciones pendientes
3. Arranca la aplicación
"""

import subprocess
import sys
import os


def run_cmd(cmd):
    """Ejecuta un comando de shell y retorna el código de salida."""
    print(f"[start] Ejecutando: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode


def get_current_revision():
    """Devuelve la revisión actual de Alembic, o None si no hay ninguna."""
    result = subprocess.run(
        "flask db current",
        shell=True,
        capture_output=True,
        text=True
    )
    output = result.stdout.strip()
    print(f"[start] Revisión actual de Alembic: '{output}'")
    return output if output else None


def main():
    # Revisión de la migración inicial (tablas creadas con db.create_all())
    INIT_REVISION = "220ad3d6dc9e"

    revision = get_current_revision()

    if not revision:
        print("[start] Sin historial de migraciones. Sellando en la migración inicial...")
        code = run_cmd(f"flask db stamp {INIT_REVISION}")
        if code != 0:
            print("[start] ERROR al sellar la base de datos. Abortando.")
            sys.exit(1)
    else:
        print(f"[start] Base de datos ya está en revisión: {revision}")

    # Aplicar migraciones pendientes
    print("[start] Aplicando migraciones pendientes...")
    code = run_cmd("flask db upgrade")
    if code != 0:
        print("[start] ERROR al aplicar migraciones. Abortando.")
        sys.exit(1)

    # Arrancar la aplicación
    print("[start] Iniciando aplicación...")
    os.execv(sys.executable, [sys.executable, "run.py"])


if __name__ == "__main__":
    main()
