from flask import jsonify

def api_response(data=None, message="OK", status=200):
    return jsonify({
        "status": "success",
        "message": message,
        "data": data
    }), status

def api_error(message="Error", status=400):
    return jsonify({
        "status": "error",
        "message": message
    }), status

def normalize_pa(returned):
    """Asegura formato (data, status)."""
    if isinstance(returned, tuple) and len(returned) == 2:
        return returned  # OK normal
    return returned, 200  # fallback cuando PA devuelve solo data
    
def _detect_free_account(html_text: str) -> bool:
    if not html_text:
        return False

    # limpiar escapes "#012" → espacios
    txt = html_text.replace("#012", " ").lower()

    # patrones detectables
    free_signals = [
        "upgrade to a paid account",
        "forbidden",
        "free account",
    ]

    # detectar página 404 HTML
    not_found_signals = [
        "page not found",
        "<title>page not found",
    ]

    # FREE?
    if any(s in txt for s in free_signals):
        return True

    # 404 from PA
    if any(s in txt for s in not_found_signals):
        return True

    return False



