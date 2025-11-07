"""Servicios auxiliares para previews de enlaces (OpenGraph/Twitter Cards)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional, Dict
import requests
from urllib.parse import urlparse


router = APIRouter(prefix="/links", tags=["Links"])

# Cache simple en memoria con TTL (segundos)
_CACHE: dict[str, dict] = {}
_TTL_SECONDS = 3600


def _safe_url(u: str) -> str:
    try:
        p = urlparse(u)
        if p.scheme not in {"http", "https"}:
            return ""
        if not p.netloc:
            return ""
        return u
    except Exception:
        return ""


def _og_from_html(html: str) -> Dict[str, Optional[str]]:
    # Parse muy ligero con heurísticas (sin dependencias pesadas)
    import re
    def meta_prop(prop: str) -> Optional[str]:
        m = re.search(rf'<meta[^>]+property=[\"\']{re.escape(prop)}[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', html, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Variante name="twitter:..."
        m = re.search(rf'<meta[^>]+name=[\"\']{re.escape(prop)}[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', html, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None

    def link_icon() -> Optional[str]:
        m = re.search(r'<link[^>]+rel=[\"\'](?:icon|shortcut icon|apple-touch-icon)[\"\'][^>]+href=[\"\']([^\"\']+)[\"\']', html, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None

    return {
        "title": meta_prop("og:title") or meta_prop("twitter:title"),
        "site_name": meta_prop("og:site_name"),
        "description": meta_prop("og:description") or meta_prop("twitter:description"),
        "image": meta_prop("og:image") or meta_prop("twitter:image") or meta_prop("twitter:image:src"),
        "icon": link_icon(),
    }


@router.get("/preview", summary="Obtener metadatos OG de un enlace")
def preview(u: str = Query(..., description="URL a previsualizar")):
    url = _safe_url(u)
    if not url:
        raise HTTPException(status_code=400, detail="URL no válida")
    try:
        import time
        now = int(time.time())
        c = _CACHE.get(url)
        if c and (now - int(c.get("_ts", 0)) < _TTL_SECONDS):
            return {k: v for k, v in c.items() if k != "_ts"}
        # Descarga HTML con timeout conservador y UA genérico
        r = requests.get(url, timeout=6, headers={
            "User-Agent": "Mozilla/5.0 (AURA Link Preview)"
        })
        r.raise_for_status()
        html = r.text or ""
        og = _og_from_html(html)
        # Normaliza icon absoluto si es relativo
        try:
            from urllib.parse import urljoin
            if og.get("icon"):
                og["icon"] = urljoin(r.url, og["icon"])  # type: ignore
            if og.get("image"):
                og["image"] = urljoin(r.url, og["image"])  # type: ignore
        except Exception:
            pass
        out = {
            "url": url,
            "final_url": r.url,
            "title": og.get("title") or "",
            "site_name": og.get("site_name") or "",
            "description": og.get("description") or "",
            "image": og.get("image") or "",
            "favicon": og.get("icon") or "",
        }
        out_store = dict(out)
        out_store["_ts"] = now
        _CACHE[url] = out_store
        return out
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"No se pudo obtener la página: {e}")


@router.get("/fetch-image", summary="Proxy simple para imágenes externas de previews")
def fetch_image(u: str = Query(..., description="URL absoluta de la imagen")):
    url = _safe_url(u)
    if not url:
        raise HTTPException(status_code=400, detail="URL no válida")
    try:
        r = requests.get(url, timeout=8, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (AURA Link Preview)"
        })
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "image/jpeg")
        return StreamingResponse(r.raw, media_type=ctype)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"No se pudo obtener la imagen: {e}")
