# 📦 Sistema de Gestión de Pedidos

Sistema web en tiempo real para coordinar pedidos entre el equipo de ventas y la fábrica.

## 🚀 Características

- **Para Vendedores**: Cargar clientes y pedidos en tiempo real
- **Para Fábrica**: Visualizar pedidos actualizados automáticamente
- **Notificaciones**: Cambios resaltados con colores
- **Observaciones**: Comunicación bidireccional sobre estado de pedidos
- **Asignación**: Designar responsables de producción

## 📋 Requisitos

- Python 3.8+
- SQLite (desarrollo) o PostgreSQL (producción)

## ⚙️ Instalación

1. Clonar el repositorio
```bash
git clone [URL_DE_TU_REPO]
cd gestion_pedidos
```

2. Crear entorno virtual
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instalar dependencias
```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno
```bash
cp .env.example .env
# Editar .env con tus valores
```

5. Inicializar base de datos
```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

6. Ejecutar aplicación
```bash
python run.py
```

La aplicación estará disponible en `http://localhost:5000`

## 👥 Roles de Usuario

- **Vendedor**: Gestiona clientes y pedidos
- **Operario Fábrica**: Visualiza y actualiza estado de pedidos

## 🔧 Tecnologías

- **Backend**: Flask, SQLAlchemy
- **Frontend**: HTML, CSS, JavaScript
- **Tiempo Real**: Flask-SocketIO
- **Base de Datos**: SQLite/PostgreSQL

## 📝 Estructura del Proyecto
```
gestion_pedidos/
├── app/              # Aplicación Flask
├── migrations/       # Migraciones de BD
├── venv/            # Entorno virtual
├── config.py        # Configuración
└── run.py          # Punto de entrada
```

## 📄 Licencia

Privado - Uso interno de la empresa