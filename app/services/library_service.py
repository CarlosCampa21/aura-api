"""Servicio de búsqueda/respuesta para documentos institucionales.

Incluye utilidades para localizar assets (PDFs) en `library_asset`.
"""
from __future__ import annotations

from typing import Optional, Dict, List

from app.repositories.library_repo import search_documents, get_document
from app.repositories.library_asset_repo import search_assets
from app.services.schedule_service import get_current_timetable_for_user
from app.infrastructure.db.mongo import get_db
from bson import ObjectId


def search_document_answer(query: str) -> Optional[str]:
    items = search_documents(query, limit=3)
    if not items:
        return None
    # Formatea una respuesta breve con el mejor match y alternativas
    best = items[0]
    out = [
        f"Encontré esto: {best['title']}",
    ]
    if best.get("file_url"):
        out.append(f"Descargar/Ver: {best['file_url']}")
    if len(items) > 1:
        alts = ", ".join(i["title"] for i in items[1:])
        out.append(f"También tengo: {alts}.")
    return "\n".join(out)


def find_asset_pdf_url(query: str) -> Optional[Dict[str, str]]:
    """Busca en `library_asset` por título/tags y devuelve el mejor match con su URL pública.

    Retorna dict con: {"title": str, "url": str} o None si no encuentra.
    """
    items = search_assets(query, limit=5)
    if not items:
        return None
    # Prioriza elementos con file_url y mime_type PDF
    pdfs = [i for i in items if i.get("file_url") and str(i.get("mime_type", "")).lower().endswith("pdf")]
    best = pdfs[0] if pdfs else (items[0] if items and items[0].get("file_url") else None)
    if not best:
        return None
    return {"title": best.get("title") or "", "url": best.get("file_url")}


def find_calendar_pdf_url() -> Optional[Dict[str, str]]:
    """Heurística para ubicar el calendario escolar en assets.

    Intenta varias consultas comunes y devuelve el primer match con URL.
    """
    queries = [
        "calendario escolar 2025",
        "calendario 2025",
        "calendario escolar",
        "calendario uabcs",
    ]
    for q in queries:
        hit = find_asset_pdf_url(q)
        if hit and hit.get("url"):
            return hit
    return None


def find_calendar_image_url() -> Optional[Dict[str, str]]:
    """Localiza una imagen/miniatura del calendario escolar si existe en assets.

    Busca por consultas comunes y prioriza mime_type image/*. Devuelve {title,url}.
    """
    queries = [
        "calendario escolar 2025",
        "calendario 2025",
        "calendario escolar",
        "calendario uabcs",
    ]
    try:
        for q in queries:
            items = search_assets(q, limit=10)
            imgs = [i for i in items if (i.get("file_url") and str(i.get("mime_type", "" )).lower().startswith("image/"))]
            if imgs:
                return {"title": imgs[0].get("title") or "Calendario escolar", "url": imgs[0].get("file_url")}
    except Exception:
        return None
    return None


def find_campus_map_image_url() -> Optional[Dict[str, str]]:
    """Localiza la imagen del mapa del campus en assets.

    Heurística: busca por combinaciones comunes del título/tags como
    "Mapa del Campus UABCS", "mapa campus uabcs", etc. Prioriza mime_type image/*.
    Devuelve {title,url} o None si no hay coincidencias.
    """
    queries = [
        "Mapa del Campus UABCS",
        "mapa campus UABCS",
        "mapa del campus",
        "mapa campus",
        "plano campus UABCS",
        "croquis campus UABCS",
    ]
    try:
        for q in queries:
            items = search_assets(q, limit=10)
            imgs = [
                i for i in items
                if (i.get("file_url") and str(i.get("mime_type", "")).lower().startswith("image/"))
            ]
            if imgs:
                return {"title": imgs[0].get("title") or "Mapa del Campus UABCS", "url": imgs[0].get("file_url")}
    except Exception:
        return None
    return None


def _normalize_building(s: str | None) -> str:
    """Normaliza nombres de edificio a slugs cortos usados como tags.

    Reglas actuales (DASC):
    - AD-46 → "ad46"
    - DSC-39 → "dsc39"
    Acepta variantes con/ sin guion/espacios/ mayúsculas.
    """
    t = (s or "").strip().lower().replace(" ", "").replace("-", "")
    if not t:
        return ""
    if t in {"ad46", "ad046", "ad-46".replace("-", ""), "ad 46".replace(" ", "")}:
        return "ad46"
    if t in {"dsc39", "dsc039", "dsc-39".replace("-", ""), "dsc 39".replace(" ", "")}:
        return "dsc39"
    # DASC genérico (sin edificio concreto)
    if t in {"dasc"}:
        return ""
    return t


def _normalize_floor(s: str | None) -> str:
    """Normaliza planta a códigos cortos: pb/pa."""
    t = (s or "").strip().lower()
    if not t:
        return ""
    if t in {"pb", "planta baja", "baja", "p.b."}:
        return "pb"
    if t in {"pa", "planta alta", "alta", "p.a."}:
        return "pa"
    return t


def find_room_image(name: str, building: str | None = None, floor: str | None = None, view: str | None = None) -> Optional[Dict[str, str]]:
    """Localiza una imagen de un salón/aula por nombre y metadatos.

    Busca en `library_asset` por título/tags; prioriza `image/*`.
    Requiere que los assets estén etiquetados con tags como:
      ["salon","aula","<nombre>","ad46"|"dsc39","pb"|"pa","puerta"|"interior"...]
    """
    try:
        nm = (name or "").strip().lower()
        if not nm:
            return None
        b = _normalize_building(building)
        f = _normalize_floor(floor)
        v = (view or "").strip().lower()

        # Construye varias consultas robustas (en orden → la primera coincidencia gana)
        toks_base: List[str] = ["salon", nm]
        queries: List[str] = []
        # Soporte de áreas no-aula (p. ej., sala de servidores)
        infra_synonyms: List[str] = []
        if nm in {"servidores", "server", "server-room", "server room", "cuarto-servidores", "cuarto de servidores", "sala de servidores", "centro de datos", "redes"}:
            infra_synonyms = ["servidores", "server room", "cuarto-servidores", "sala de servidores", "centro de datos", "redes"]

        def add_q(parts: List[str]):
            q = " ".join([p for p in parts if p])
            if q and q not in queries:
                queries.append(q)

        # Con combinaciones progresivas
        add_q(toks_base + [b, f, v])
        add_q(toks_base + [b, f])
        add_q(toks_base + [b])
        add_q(toks_base + [f])
        add_q(["aula", nm, b, f])
        add_q([nm, "salon", b, f])
        add_q([nm, b])

        # También prueba variantes del nombre en mayúsculas en caso de títulos exactos
        add_q(["salon", nm.upper(), b, f])
        add_q(["aula", nm.upper(), b, f])

        # Para infraestructura: intenta búsquedas sin prefijos salón/aula
        for syn in ([nm] + infra_synonyms):
            add_q([syn, b, f, v])
            add_q([syn, b, f])
            add_q(["infraestructura", syn, b, f])
            add_q(["redes", syn, b, f])

        # Intento por cada consulta hasta topar una imagen
        for q in queries:
            items = search_assets(q, limit=10)
            imgs = [i for i in items if (i.get("file_url") and str(i.get("mime_type", "")).lower().startswith("image/"))]
            if imgs:
                top = imgs[0]
                return {"title": top.get("title") or f"Salón {name.upper()}", "url": top.get("file_url")}
        return None
    except Exception:
        return None


def find_schedule_image_for_user(user_email: str) -> Optional[Dict[str, str]]:
    """Intenta localizar una imagen de horario para el timetable vigente del usuario.

    Heurística: construye consultas por título/tags con "horario <program> <semester> <shift> <period>".
    Devuelve {title,url} o None.
    """
    try:
        tt = get_current_timetable_for_user(user_email)
        if not tt:
            return None
        program = (tt.get("program_code") or "").upper()
        sem = str(tt.get("semester") or "")
        shift = str(tt.get("shift") or "").upper()
        period = str(tt.get("period_code") or "")
        # 0) Intentar por doc_ref si existe un library_doc con el mismo título
        try:
            title_guess = tt.get("title") or f"Horario {program} {sem} {shift} {period}".strip()
            if title_guess:
                docs = search_documents(title_guess, limit=1)
                if docs:
                    did = docs[0].get("id")
                    if did:
                        db = get_db()
                        rows = list(db["library_asset"].find({"doc_ref": ObjectId(did), "enabled": True}))
                        imgs = [r for r in rows if str(r.get("mime_type","" )).lower().startswith("image/") and r.get("url")]
                        if imgs:
                            return {"title": imgs[0].get("title") or title_guess, "url": imgs[0].get("url")}
        except Exception:
            pass

        # 1) Construye múltiples consultas robustas
        # Normaliza y amplía sinónimos de turno (TM<->MT, TV<->VT)
        def shift_aliases(s: str) -> List[str]:
            s = (s or "").upper()
            if s == "TM":
                return ["TM", "MT", "MATUTINO", "MAÑANA", "MANANA"]
            if s == "TV":
                # incluir alias usados en títulos: VP (vespertino)
                return ["TV", "VT", "VP", "VESPERTINO", "TARDE"]
            return [s] if s else []

        aliases = shift_aliases(shift)
        queries: List[str] = []
        for sh in aliases or [""]:
            base1 = " ".join([p for p in [program, sem, sh, period] if p])
            base2 = " ".join([p for p in [program, sem, sh] if p])
            queries.extend([
                " ".join([p for p in ["horario", base1] if p]),
                " ".join([p for p in ["horario", base2] if p]),
                base1,
                base2,
                # variantes con la palabra 'imagen' al frente (para títulos tipo Imagen_Horario...)
                " ".join([p for p in ["imagen", "horario", base1] if p]),
                " ".join([p for p in ["imagen", "horario", base2] if p]),
            ])
        queries.append(tt.get("title") or "")
        # 2) Intenta primero imágenes explícitas
        for q in queries + [q + " imagen" for q in queries]:
            if not q.strip():
                continue
            items = search_assets(q, limit=10)
            imgs = [
                i for i in items
                if (i.get("file_url") and str(i.get("mime_type", "")).lower().startswith("image/"))
            ]
            if imgs:
                return {"title": imgs[0].get("title") or "", "url": imgs[0].get("file_url")}
        # 3) Como último recurso, acepta un PDF si no hay imagen
        for q in queries:
            if not q.strip():
                continue
            hit = find_asset_pdf_url(q)
            if hit:
                return hit
        return None
    except Exception:
        return None


def find_schedule_image_by_params(program: str, semester: int | str, shift: str | None, period: str | None = None, group: str | None = None) -> Optional[Dict[str, str]]:
    """Localiza una imagen de horario usando parámetros explícitos.

    Busca en `library_asset` por título/tags. Prioriza mime_type image/*.
    """
    try:
        prog = (program or "").upper()
        sem = str(semester or "").strip()
        sh = (shift or "").upper().strip()
        grp = (group or "").strip().upper()
        per = str(period or "").strip()

        def shift_aliases(s: str) -> List[str]:
            s = (s or "").upper()
            if s == "TM":
                return ["TM", "MT", "MATUTINO", "MAÑANA", "MANANA"]
            if s == "TV":
                return ["TV", "VT", "VP", "VESPERTINO", "TARDE"]
            return [s] if s else []

        queries: List[str] = []
        for sh_alias in shift_aliases(sh) or [""]:
            # Partes base
            sem_str = str(sem)
            base_core = [prog, sem_str, sh_alias, per]
            base = " ".join([p for p in base_core if p])
            # Variantes de grupo
            grp_variants: List[str] = []
            if grp:
                letter = grp[0].upper()
                grp_variants = [
                    f"GRUPO {letter}",   # "GRUPO A"
                    f"{sem_str}{letter}",# "1A" o "3B"
                    letter,               # "A" (menos específica)
                ]
            # Construye consultas combinando variantes con y sin grupo (prioriza con grupo)
            bases_to_try: List[str] = []
            for gv in grp_variants:
                b_with = " ".join([p for p in [prog, sem_str, gv, sh_alias, per] if p])
                if b_with:
                    bases_to_try.append(b_with)
            bases_to_try.append(base)
            # Genera queries para cada base
            for b in bases_to_try:
                for prefix in ("horario", None, "imagen horario"):
                    q = " ".join([p for p in ([prefix, b] if prefix else [b]) if p])
                    if q and q not in queries:
                        queries.append(q)
        for q in queries:
            if not q.strip():
                continue
            items = search_assets(q, limit=10)
            imgs = [i for i in items if (i.get("file_url") and str(i.get("mime_type","" )).lower().startswith("image/"))]
            if imgs:
                # Si se especificó grupo, prioriza coincidencias explícitas por título o tags
                if grp:
                    g = (grp or "").strip().upper()
                    pat1 = f"grupo {g}".lower()
                    pat2 = f"{sem_str}{g}".lower()
                    def score(it: Dict[str, str]) -> int:
                        s = 0
                        title = (it.get("title") or "").lower()
                        tags = [str(t).lower() for t in (it.get("tags") or [])]
                        if pat1 in title:
                            s += 3
                        if pat2 in title:
                            s += 2
                        if g.lower() in tags:
                            s += 2
                        # bonus por incluir todas las piezas clave
                        if prog.lower() in title and sem_str in title and (sh_alias or "").lower() in title:
                            s += 1
                        return s
                    imgs = sorted(imgs, key=score, reverse=True)
                return {"title": imgs[0].get("title") or "", "url": imgs[0].get("file_url")}
        return None
    except Exception:
        return None


def find_schedule_image_by_title(title: str) -> Optional[Dict[str, str]]:
    """Localiza una imagen de horario buscando por el título completo (o parte de él).

    Útil cuando el turno previo ya mostró el horario en texto con "Horario vigente: <title>".
    """
    try:
        raw = (title or "").strip()
        if not raw:
            return None

        # 0) Intentar parsear parámetros (programa/semestre/turno/periodo/grupo) desde el título
        #    Ej.: "IDS 7 TM Grupo A 2025-II" → IDS, 7, TM, 2025-II
        import re
        prog = None
        sem = None
        shift = None
        period = None
        group = None
        # Programa: primer token alfabético de 2-8 letras
        m_prog = re.search(r"\b([A-Za-z]{2,8})\b", raw)
        if m_prog:
            prog = m_prog.group(1).upper()
        # Semestre: primer número 1-9
        m_sem = re.search(r"\b(\d{1,2})\b", raw)
        if m_sem:
            try:
                sem = int(m_sem.group(1))
            except Exception:
                sem = None
        # Turno: TM/TV o palabras
        s_low = raw.lower()
        if any(w in s_low for w in ["tm", "mt", "matutino", "mañana", "manana"]):
            shift = "TM"
        elif any(w in s_low for w in ["tv", "vt", "vp", "vespertino", "tarde"]):
            shift = "TV"
        # Grupo: 'Grupo A' o 'Grupo B'
        m_grp = re.search(r"\bgrupo\s*([ab])\b", raw, re.IGNORECASE)
        if m_grp:
            group = m_grp.group(1).upper()
        # Periodo: algo tipo 2025-II o 2025 II
        m_per = re.search(r"\b(20\d{2})\s*-?\s*([ivx]+)\b", raw, re.IGNORECASE)
        if m_per:
            period = f"{m_per.group(1)}-{m_per.group(2).upper()}"

        if prog and sem and shift:
            hit = find_schedule_image_by_params(prog, sem, shift, period, group)
            if hit:
                return hit

        # 1) doc_ref preferente con el título completo
        try:
            docs = search_documents(raw, limit=1)
            if docs:
                did = docs[0].get("id")
                if did:
                    db = get_db()
                    rows = list(db["library_asset"].find({"doc_ref": ObjectId(did), "enabled": True}))
                    imgs = [r for r in rows if str(r.get("mime_type","" )).lower().startswith("image/") and r.get("url")]
                    if imgs:
                        return {"title": imgs[0].get("title") or raw, "url": imgs[0].get("url")}
        except Exception:
            pass

        # 2) Variantes del título para aumentar recall: sin "Grupo X" y con prefijo "horario"
        variants = [raw]
        # También probamos forzando 'Grupo A/B' si existía
        if group:
            variants.append(raw)
        # y una versión sin el fragmento de grupo
        variants.append(re.sub(r"\bGrupo\s+[A-Za-z0-9]+\b", "", raw, flags=re.IGNORECASE).strip())
        for v in list(variants):
            if not v.lower().startswith("horario"):
                variants.append("Horario " + v)

        # 3) Búsqueda directa en assets por cada variante
        for q in variants:
            if not q:
                continue
            items = search_assets(q, limit=10)
            imgs = [i for i in items if (i.get("file_url") and str(i.get("mime_type","" )).lower().startswith("image/"))]
            if imgs:
                return {"title": imgs[0].get("title") or q, "url": imgs[0].get("file_url")}
        return None
    except Exception:
        return None
