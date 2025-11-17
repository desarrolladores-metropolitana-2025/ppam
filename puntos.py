from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from app import db
from modelos import PuntoPredicacion

bp_puntos = Blueprint('puntos', __name__)

# --- INDEX ---
@bp_puntos.route('/puntos')
def puntos_index():
    puntos = PuntoPredicacion.query.all()
    return render_template('puntos.html', puntos=puntos)

# --- API: LISTAR ---
@bp_puntos.route('/api/puntos', methods=['GET'])
def puntos_listar():
    puntos = PuntoPredicacion.query.all()
    return jsonify([p.to_dict() for p in puntos])

# --- API: CREAR O EDITAR ---
@bp_puntos.route('/api/puntos', methods=['POST'])
def puntos_guardar():
    data = request.get_json()
    id = data.get('id')

    if id:
        punto = PuntoPredicacion.query.get(id)
        if not punto:
            return jsonify({'error': 'Punto no encontrado'}), 404
    else:
        punto = PuntoPredicacion()

    punto.nombre = data.get('nombre')
    punto.direccion = data.get('direccion')
    punto.horario = data.get('horario')
    punto.responsable = data.get('responsable')

    db.session.add(punto)
    db.session.commit()

    return jsonify({'success': True, 'id': punto.id})

# --- API: ELIMINAR ---
@bp_puntos.route('/api/puntos/<int:id>', methods=['DELETE'])
def puntos_eliminar(id):
    punto = PuntoPredicacion.query.get(id)
    if not punto:
        return jsonify({'error': 'Punto no encontrado'}), 404
    db.session.delete(punto)
    db.session.commit()
    return jsonify({'success': True})
