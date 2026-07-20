from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash

# Instancia global de la base de datos
db = SQLAlchemy()

# Modelo de Usuario para la base de datos
class User(UserMixin, db.Model):
    __tablename__ = 'usuarios_admin'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

# ========================================================
# NUEVO MODELO: Para guardar los layouts dinámicos de Vue
# ========================================================
class LayoutConfig(db.Model):
    __tablename__ = 'layout_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(50), unique=True, nullable=False)  # Ejemplo: 'hites'
    columnas = db.Column(db.JSON, nullable=False)  # Aquí se guarda el array completo enviado desde Vue

def init_db_and_admins(app):
    """
    Crea las tablas si no existen e inyecta los 3 usuarios administradores iniciales.
    """
    with app.app_context():
        # Crea todas las tablas definidas en los modelos (usuarios_admin y layout_configs)
        db.create_all()

        # Lista de administradores a crear por defecto (Usuario, Contraseña temporal)
        # IMPORTANTE: En producción, ellos deberán cambiar estas contraseñas
        admins_iniciales = [
            ("admin1", "Soporte.2026*"),
            ("admin2", "Soporte.2026*"),
            ("admin3", "Soporte.2026*")
        ]

        for username, password in admins_iniciales:
            # Verifica si el usuario ya existe para no duplicarlo
            user_exists = User.query.filter_by(username=username).first()
            if not user_exists:
                nuevo_admin = User(username=username)
                nuevo_admin.set_password(password) # Encripta la contraseña
                db.session.add(nuevo_admin)
                print(f"[SEMBRADO] Usuario administrador '{username}' creado exitosamente.")
        
        # Guarda los cambios en PostgreSQL
        db.session.commit()