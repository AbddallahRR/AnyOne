"""El overlay del player no debe robarle el clic al <iframe> cross-origin de JKanime.

Sin esto, el clic para pausar/reanudar solo funciona si el usuario clica tras 3s
sin mover el raton: cada mousemove vuelve a mostrar el overlay (pointer-events
activo, inset:0, z-index:200) y se come el clic antes de que llegue al player
embebido. Con un <video> propio el overlay SI debe seguir capturando el clic.

Se comprueba sobre el CSS y el JS reales del repo, no sobre una copia.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / 'static/css/reader.css').read_text(encoding='utf-8')
JS = (ROOT / 'static/js/reader.js').read_text(encoding='utf-8')
SERIE_JS = (ROOT / 'static/js/serie.js').read_text(encoding='utf-8')


def _rule(css: str, selector: str) -> str:
    """Devuelve el cuerpo de la regla CSS de *selector* (declaraciones_planas)."""
    m = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', css)
    assert m, f'no existe la regla {selector!r} en reader.css'
    return m.group(1)


def test_overlay_cubre_la_pantalla():
    """Si el overlay no cubriese la pantalla, el bug del clic no existiría."""
    body = _rule(CSS, '.player-overlay')
    assert 'inset: 0' in body
    assert re.search(r'z-index:\s*200', body)


def test_clase_clickthrough_deja_pasar_el_clic():
    assert 'pointer-events: none' in _rule(CSS, '.player-overlay.po-clickthrough')


def test_la_barra_superior_sigue_siendo_clicable():
    """po-top es pointer-events:none, pero sus hijos se reactivan: si no, el
    boton de volver / fullscreen quedaria muerto en modo remoto."""
    assert 'pointer-events: none' in _rule(CSS, '.po-top')
    assert 'pointer-events: auto' in _rule(CSS, '.po-top > *')


def test_la_barra_inferior_sigue_siendo_clicable():
    assert 'pointer-events: none' in _rule(CSS, '.po-bottom')
    assert 'pointer-events: auto' in _rule(CSS, '.po-bottom > *')


def test_la_clase_se_activa_en_anime_remoto():
    """loadRemoteAnimeChapter (el <iframe>) debe activar el click-through."""
    fn = JS[JS.index('async function loadRemoteAnimeChapter'):]
    fn = fn[:fn.index('\n  }\n')]
    assert 'setOverlayClickthrough(true)' in fn


def test_la_clase_se_desactiva_en_anime_local():
    """loadLocalAnimeChapter (el <video> propio) debe recuperar el overlay,
    o el play/pause por clic dejaria de funcionar en local."""
    fn = JS[JS.index('async function loadLocalAnimeChapter'):]
    fn = fn[:fn.index('\n  }\n')]
    assert 'setOverlayClickthrough(false)' in fn


def test_el_auto_hide_no_se_aplica_en_remoto():
    """El <iframe> se come los mousemove: si el overlay se auto-oculta en remoto,
    la barra superior se pierde para siempre (ya no llegan eventos que la
    vuelvan a mostrar). El guard va DENTRO del callback del temporizador, porque
    el timer puede estar en marcha antes de que se aplique la clase."""
    body = JS[JS.index('hideTimer = setTimeout('):]
    body = body[:body.index('}, 3000);')]
    assert "po-clickthrough" in body, 'el auto-hide debeSaltarse en modo remoto'


def test_activar_modo_remoto_revela_la_ui():
    """Si la UI ya se ocultó antes de aplicar la clase, hay que quitar po-hidden:
    en remoto no hay mousemove que la vuelva a mostrar."""
    fn = JS[JS.index('function setOverlayClickthrough'):]
    fn = fn[:fn.index('\n  }')]
    assert "remove('po-hidden')" in fn


def test_el_progreso_remoto_se_guarda_al_cargar():
    """loadRemoteAnimeChapter debe persistir el capítulo en curso via
    /api/progress/{type}/{source}/{content_id} (el endpoint ya existe y serie.js
    ya lo lee en modo remoto; solo faltaba grabarlo)."""
    fn = JS[JS.index('async function loadRemoteAnimeChapter'):]
    fn = fn[:fn.index('\n  }\n')]
    assert '/api/progress/' in fn
    assert 'currentChapterNum' in fn


def test_el_progreso_remoto_se_guarda_tambien_en_local():
    """El guardado debe vivir en el code path remoto, no solo en el local."""
    remote = JS[JS.index('async function loadRemoteAnimeChapter'):]
    remote = remote[:remote.index('\n  }\n')]
    local = JS[JS.index('async function loadLocalAnimeChapter'):]
    local = local[:local.index('\n  }\n')]
    assert '/api/progress/' in remote
    assert '/api/progress/' in local
    assert remote != local


def test_el_iframe_permite_autoplay():
    """El popup '¿Continuar donde te quedaste?' del DPlayer de JKAnime llama a
    play() dentro del iframe. Sin allow-autoplay en el sandbox, el navegador
    bloquea esa llamada y el video queda congelado en el frame inicial; en
    jkanime.com no pasa porque no usan sandbox. Es el permiso Policy, no el
    atributo autoplay del video."""
    fn = JS[JS.index('async function loadRemoteAnimeChapter'):]
    fn = fn[:fn.index('\n  }\n')]
    assert 'allow-autoplay' in fn, 'solo --allow? falta allow-autoplay en el sandbox'
    assert 'allow="autoplay' in fn, 'falta el permiso Policies allow=autoplay'


def test_el_bundle_de_produccion_incluye_la_clase():
    """El navegador carga static/dist, no los fuentes: si el bundle no lleva el
    fix, en produccion sigue roto aunque reader.js/css esten bien."""
    dist = ROOT / 'static/dist'
    bundles = json.loads((dist / 'build.json').read_text(encoding='utf-8'))['bundles']

    css = (dist / bundles['css:reader']).read_text(encoding='utf-8')
    assert 'po-clickthrough' in css, 'falta el fix en el bundle CSS: ejecuta scripts/build.py'

    js = (dist / bundles['js:reader']).read_text(encoding='utf-8')
    assert 'po-clickthrough' in js, 'falta el fix en el bundle JS: ejecuta scripts/build.py'


@pytest.mark.parametrize('bundle', ['js:reader', 'css:reader'])
def test_manifest_sin_bundles_rotos(bundle):
    dist = ROOT / 'static/dist'
    name = json.loads((dist / 'build.json').read_text(encoding='utf-8'))['bundles'][bundle]
    assert (dist / name).exists(), f'bundle {name} no existe en dist/'


APP_JS = (ROOT / 'static/js/app.js').read_text(encoding='utf-8')


def test_fila_de_remotos_usa_el_endpoint_y_la_url_remota():
    """loadRemoteRecent debe leer /api/recent/remote/{type} y enlazar los cards a
    /reader/{type}/{source}/{id}/{chapter} (NO a /reader/.../local/...)."""
    fn = APP_JS[APP_JS.index('async function loadRemoteRecent'):]
    fn = fn[:fn.index('\n  }\n')]
    assert '/api/recent/remote/${type}' in fn
    assert '/reader/${type}/${source}/${id}/${chapter' in fn
    assert 'local' not in fn


def test_fila_remota_se_carga_al_abrir_el_tab_anime():
    """setActiveTab debe invocar loadRemoteRecent para anime y manga."""
    fn = APP_JS[APP_JS.index('function setActiveTab'):]
    fn = fn[:fn.index('\n  }\n')]
    assert "loadRemoteRecent('anime')" in fn
    assert "loadRemoteRecent('manga')" in fn


def test_index_sin_empty_state_inicial():
    """Los paneles de búsqueda no deben empezar con 'Busca un X para comenzar':
    con la fila de recientes encima, ese empty-state inicial es ruido."""
    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    assert 'Busca un anime para comenzar' not in html
    assert 'Busca un manga para comenzar' not in html
    assert 'anime-recent-section' in html
    assert 'manga-recent-section' in html


def test_anime_remoto_muestra_porcentaje_de_la_serie():
    """En anime remoto no hay segundos (iframe cross-origin): el '0:00' es
    basura. Lo que sí se sabe es en qué capítulo vas de la serie: _renderProgress
    debe mostrar pct% (capítulo actual / total) en vez de minutos:fps."""
    fn = SERIE_JS[SERIE_JS.index('async function _renderProgress'):]
    fn = fn[:fn.index('\n  }\n')]
    assert 'chapters.length' in fn, 'el progreso remoto debe usar el total de capítulos'
    assert 'findIndex' in fn, 'debe localizar el capítulo actual en la lista'
    assert "'0:00'" not in fn or 'pct%' in fn


def test_anime_remoto_no_muestra_0_00_para_progreso_vacio():
    """El fallback mm:ss queda solo para el caso sin capítulos cargados (rareza
    defensiva); con la serie cargada el span del porcentaje se llena con pct%."""
    fn = SERIE_JS[SERIE_JS.index('async function _renderProgress'):]
    fn = fn[:fn.index('\n  }\n')]
    assert 'progressPercentSpan.textContent = `${pct}%`' in fn
