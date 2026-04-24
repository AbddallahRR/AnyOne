class BaseSource:
    """Clase base para todas las fuentes (anime y manga)."""

    def search(self, query: str) -> list:
        """Busca contenido por título.
        Retorna lista de dicts con: {'id': str, 'title': str, 'cover': str}
        """
        raise NotImplementedError

    def get_details(self, content_id: str) -> dict:
        """Obtiene detalles de un contenido.
        Retorna dict con: {'title': str, 'cover': str, 'synopsis': str}
        """
        raise NotImplementedError

    def get_chapters(self, content_id: str) -> list:
        """Obtiene lista de capítulos.
        Retorna lista de dicts: [{'number': str, 'id': str}, ...]
        """
        raise NotImplementedError

    def download_chapter(self, content_id: str, chapter_id: str, dest_folder: str) -> str:
        """Descarga un capítulo completo (imágenes o video).
        Retorna la ruta del directorio donde se guardó el capítulo.
        """
        raise NotImplementedError

    def get_stream_url(self, content_id: str, chapter_id: str) -> str | None:
        """Opcional: retorna URL directa para streaming (solo anime)."""
        return None
       