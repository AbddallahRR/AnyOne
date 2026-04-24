from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/serie/<type>/<source>/<id>')
def serie_detail(type, source, id):
    return render_template('serie.html', type=type, source=source, id=id)

@main_bp.route('/reader/<type>/<source>/<content_id>/<chapter>')
def reader(type, source, content_id, chapter):
    """Página de lectura/reproducción a pantalla completa."""
    return render_template('reader.html', 
                           type=type, 
                           source=source, 
                           content_id=content_id, 
                           chapter=chapter)