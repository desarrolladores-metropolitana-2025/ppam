from flask_app import app, enviar_notificacion_turno
from datetime import datetime, time
from types import SimpleNamespace

# Contexto de Flask
with app.app_context():

    # Creamos publicadores ficticios
    publicadores = [
        SimpleNamespace(nombre="Juan", apellido="Pérez", mail="juan@example.com"),
        SimpleNamespace(nombre="María", apellido="Gómez", mail="maria@example.com"),
    ]

    # Creamos un turno ficticio
    turno = SimpleNamespace(
        punto_id=1,
        fecha=datetime.today(),
        hora_inicio=time(10, 0),
        hora_fin=time(11, 0),
        capitan_id=1,
        publicador1_id=2,
        publicador2_id=None,
        publicador3_id=None,
        publicador4_id=None
    )

    # Simulamos la consulta de publicadores dentro de la función
    def mock_query_publicadores(ids):
        return publicadores

    # Sobrescribimos momentáneamente la consulta dentro de la función
    # para que use nuestros publicadores ficticios
    from flask_app import Publicador, Turno, PuntoPredicacion, db

    original_query = Publicador.query.filter

    class MockQuery:
        def filter(self, *args, **kwargs):
            return self
        def all(self):
            return publicadores

    Publicador.query.filter = lambda *args, **kwargs: MockQuery()

    # También simulamos el punto
    original_get = PuntoPredicacion.query.get
    PuntoPredicacion.query.get = lambda id: SimpleNamespace(punto_nombre="Punto Test")

    # Enviamos el mail
    try:
        enviar_notificacion_turno(turno)
        print("✅ Mail enviado (o al menos pasó la función sin errores).")
    except Exception as e:
        print("❌ Ocurrió un error:", e)

    # Restaurar los originales
    Publicador.query.filter = original_query
    PuntoPredicacion.query.get = original_get
