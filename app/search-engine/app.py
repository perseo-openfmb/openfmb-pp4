import os
import re
import unicodedata
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, abort
import pdfplumber

app = Flask(__name__)


_ACCENT_CLASSES = {
    "a": "[aáàâä]", "e": "[eéèêë]", "i": "[iíìîï]",
    "o": "[oóòôö]", "u": "[uúùûü]", "n": "[nñ]",
}


def _accent_pattern(term):
    """Convierte un término en un patrón regex que ignora tildes, para que
    resaltar coincida con la MISMA lógica que usa la búsqueda (normalize())."""
    return "".join(_ACCENT_CLASSES.get(ch.lower(), re.escape(ch)) for ch in term)


@app.template_filter("highlight")
def highlight_filter(text, query):
    """Resalta cada término de la query (no solo la frase completa), sin
    importar tildes — antes solo buscaba la query entera como frase literal,
    así que una búsqueda de 2+ palabras nunca resaltaba nada en esta vista."""
    terms = [t for t in query.split() if t]
    safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if not terms:
        return safe_text
    pattern = "(" + "|".join(_accent_pattern(t) for t in terms) + ")"
    return re.sub(
        pattern,
        r'<span class="highlight-match">\1</span>',
        safe_text,
        flags=re.IGNORECASE,
    )

# Raíz única donde Docker monta todo el contenido a indexar (ver docker-compose.yml).
# Recorremos esta carpeta de forma recursiva: no hay que listar subcarpetas a mano.
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/docs"))

TEXT_EXTENSIONS = {".yaml", ".yml", ".toml", ".sql", ".csv"}
ALL_EXTENSIONS = TEXT_EXTENSIONS | {".pdf"}

ICONS = {
    ".pdf": "📄",
    ".yaml": "⚙️",
    ".yml": "⚙️",
    ".toml": "⚙️",
    ".sql": "🗄️",
    ".csv": "📊",
    ".md": "📝",
}


CSV_LABELS = {
    "identificadores_microrred.csv": "Identificadores (mRID) de dispositivos de la microrred",
    "mapeo_variables_openfmb_api_CC.csv": "Mapeo de variables - Color Control GX",
    "mapeo_variables_openfmb_api_Fron.csv": "Mapeo de variables - Inversor Fronius",
    "mapeo_variables_openfmb_api_sch.csv": "Mapeo de variables - Medidor Schneider",
    "mapeo_variables_openfmb_api_sie.csv": "Mapeo de variables - Medidor Siemens",
    "mapeo_variables_openfmb_api_pyra.csv": "Mapeo de variables - Piranómetro",
}


def normalize(text):
    """minúsculas y sin tildes, para que 'configuracion' encuentre 'configuración'."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# El español solo usa acento agudo (á é í ó ú) y ñ. Antes este mapa también
# "arreglaba" secuencias con comillas rectas y backtick (`a`, "a, etc.) para
# imitar acentos de otros idiomas que el español no usa — eso corrompía
# palabras normales como "api" -> äpi o `echo` -> èchò. Se deja solo lo que
# realmente puede pasar en un PDF de LaTeX en español.
ACCENT_MAP = {
    "\u00b4a": "á", "\u00b4e": "é", "\u00b4i": "í", "\u00b4o": "ó", "\u00b4u": "ú",
    "~n": "ñ",
}

def fix_accents(text):
    """Reconstruye tildes que el PDF entregó como glifo de acento (´) o
    virgulilla (~) separado de su letra, en vez de un carácter ya compuesto.
    NFC ya resuelve el caso de un acento Unicode combinante pegado a la
    letra; esto cubre el caso adicional de un carácter de acento suelto."""
    if not text:
        return text

    result = unicodedata.normalize("NFC", text)

    # Caso "´a" -> "á" (acento antes de la letra)
    for pair, replacement in ACCENT_MAP.items():
        result = result.replace(pair, replacement)

    # Caso "a´" -> "á" (acento después de la letra)
    def recombine_reverse(m):
        letter, accent = m.group(1), m.group(2)
        replacement = ACCENT_MAP.get(accent + letter.lower())
        if not replacement:
            return m.group(0)
        return replacement.upper() if letter.isupper() else replacement

    result = re.sub(r'([aeiouAEIOUn])(\u00b4|~)', recombine_reverse, result)

    return result


def iter_source_files():
    if not DATA_DIR.exists():
        print(f"Directorio no encontrado: {DATA_DIR}")
        return
    for path in DATA_DIR.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext == ".pdf":
            yield path
        elif ext == ".csv":
            yield path


def extract_pdf(path):
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text, sections = extract_page_with_sections(page)
            if text:
                pages.append({"page_num": i + 1, "text": text, "sections": sections})
        total = len(pdf.pages)
    return pages, total


def extract_page_with_sections(page):
    """Extract text and identify section headings by font size and pattern."""
    chars = page.chars
    if not chars:
        fallback = page.extract_text(x_tolerance=3) or ""
        return fix_accents(fallback), []

    # top = distancia desde el borde SUPERIOR de la página (crece hacia abajo).
    # Ascendente = arriba-a-abajo, que es el orden real de lectura.
    chars = sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"]))

    lines = []
    current_line = []
    last_top = None
    last_x1 = None

    for char in chars:
        top = round(char["top"], 1)
        x0 = char["x0"]
        text = char.get("text", "")

        if last_top is not None and abs(top - last_top) > 2:
            lines.append(current_line)
            current_line = []

        if current_line and last_x1 is not None:
            gap = x0 - last_x1
            font_size = char.get("size", 10) or 10
            space_width = font_size * 0.25
            if gap > space_width:
                current_line.append(" ")

        current_line.append(text)
        last_top = top
        last_x1 = char.get("x1", x0 + char.get("width", 0))

    if current_line:
        lines.append(current_line)

    # Rebuild text and detect section headings
    text_lines = []
    sections = []
    position = 0

    for line_chars in lines:
        line_text = "".join(line_chars)
        text_lines.append(line_text)

        clean = line_text.strip()
        if clean and len(clean) < 120:
            is_section = False

            # Pattern 1: Numbered sections like "1.", "1.1", "2.3.1"
            if re.match(r'^\d+(\.\d+)*\.?\s+\S', clean):
                is_section = True

            # Pattern 2: All caps or title case short lines (likely headings)
            elif len(clean) < 60 and clean[0].isupper():
                # Check if mostly uppercase or title case
                words = clean.split()
                if len(words) <= 8:
                    upper_count = sum(1 for w in words if w.isupper() and len(w) > 1)
                    if upper_count >= len(words) * 0.5:
                        is_section = True
                    # Title case: each word starts with capital
                    elif all(w[0].isupper() for w in words if len(w) > 2):
                        is_section = True

            # Pattern 3: Lines that look like "Seccion X", "Capitulo X", etc.
            if re.match(r'^(secci[oó]n|cap[ií]tulo|ap[eé]ndice|tabla|figura|anexo)\s', clean, re.IGNORECASE):
                is_section = True

            if is_section:
                sections.append({"title": fix_accents(clean), "position": position})

        position += len(line_text) + 1  # +1 for \n

    full_text = "\n".join(text_lines)
    return fix_accents(full_text), sections


def extract_text_file(path):
    text = path.read_text(errors="ignore")
    if path.suffix.lower() == ".csv":
        import csv
        with open(path, newline='', errors="ignore") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            rows = list(reader)
        if rows:
            headers = rows[0]
            data_rows = rows[1:]
            return [{"page_num": 1, "text": text, "csv_headers": headers, "csv_rows": data_rows}], 1
    return [{"page_num": 1, "text": text}], 1


def build_index():
    """Extrae texto de todos los archivos soportados y arma el índice en memoria.

    Se ejecuta al importar el módulo (no solo bajo `python app.py`), para que
    funcione también bajo gunicorn, que importa `app:app` sin correr __main__.
    """
    docs = {}
    for path in iter_source_files():
        ext = path.suffix.lower()
        try:
            if ext == ".pdf":
                pages, total = extract_pdf(path)
            else:
                pages, total = extract_text_file(path)
        except Exception as e:
            print(f"Error extrayendo {path}: {e}")
            continue

        if pages:
            key = str(path)
            docs[key] = {
                "name": path.name,
                "display_path": str(path.relative_to(DATA_DIR)),
                "ext": ext,
                "icon": ICONS.get(ext, "📁"),
                "pages": pages,
                "total_pages": total,
            }
    return docs


def parse_query(query):
    """Parse query supporting single-quoted exact phrases.
    Examples:
        'mRID mapping' voltage → ['mRID mapping', 'voltage']
        'exact phrase' → ['exact phrase']
        word1 word2 → ['word1', 'word2']
    """
    import re as _re
    terms = []
    for match in _re.finditer(r"'([^']+)'", query):
        term = normalize(match.group(1))
        if term:
            terms.append(term)
    remaining = _re.sub(r"'[^']*'", '', query)
    for word in remaining.split():
        word = normalize(word)
        if word:
            terms.append(word)
    return terms


def find_matches(text, terms, context_chars=150):
    """Ubica cada término (ya normalizado) en el texto original y arma fragmentos
    de contexto, evitando duplicar fragmentos que se solapan demasiado."""
    matches = []
    norm_text = normalize(text)
    seen_positions = []

    for term in terms:
        start = 0
        while True:
            idx = norm_text.find(term, start)
            if idx == -1:
                break
            if not any(abs(idx - seen) < context_chars for seen in seen_positions):
                match_start = max(0, idx - context_chars)
                match_end = min(len(text), idx + len(term) + context_chars)
                snippet = text[match_start:match_end]
                if match_start > 0:
                    snippet = "…" + snippet
                if match_end < len(text):
                    snippet = snippet + "…"
                line_num = text.count("\n", 0, idx) + 1
                matches.append({"text": snippet, "position": idx, "line": line_num})
                seen_positions.append(idx)
            start = idx + max(len(term), 1)

    matches.sort(key=lambda m: m["position"])
    return matches


def search_docs(query, docs):
    """Búsqueda OR multi-término con agrupación por sección para PDFs.
    Máximo 20 resultados por archivo para no saturar la página.
    Para CSVs, si un término coincide con el label, se muestran todas las filas."""
    MAX_PER_DOC = 20
    terms = parse_query(query)
    if not terms or not docs:
        return []

    results = []
    for doc_data in docs.values():
        is_pdf = doc_data["ext"] == ".pdf"
        is_csv = doc_data["ext"] == ".csv"

        # --- CSV label match: show all rows even if content doesn't match ---
        if is_csv:
            label = CSV_LABELS.get(doc_data["display_path"], "")
            label_match = label and any(normalize(term) in normalize(label) for term in terms)
            if label_match:
                page = doc_data["pages"][0]
                if page.get("csv_headers") and page.get("csv_rows"):
                    results.append({
                        "document": doc_data["name"],
                        "display_path": doc_data["display_path"],
                        "icon": doc_data["icon"],
                        "ext": doc_data["ext"],
                        "page": page["page_num"],
                        "total_pages": doc_data["total_pages"],
                        "section": None,
                        "matches": [],
                        "csv_headers": page["csv_headers"],
                        "csv_rows": page["csv_rows"],
                        "show_all": True,
                        "score": 100,
                    })
                continue  # label matched, no need to search content

        # --- Content-based search (PDFs + CSVs without label match) ---
        doc_count = 0
        for page in doc_data["pages"]:
            if doc_count >= MAX_PER_DOC:
                break
            norm_page = normalize(page["text"])
            if not any(term in norm_page for term in terms):
                continue

            matches = find_matches(page["text"], terms)
            if not matches:
                continue

            score = sum(norm_page.count(term) for term in terms)

            if is_pdf and page.get("sections"):
                sections = page["sections"]
                section_groups = assign_matches_to_sections(matches, sections)

                for sec_title, sec_matches in section_groups:
                    if doc_count >= MAX_PER_DOC:
                        break
                    doc_count += 1
                    results.append({
                        "document": doc_data["name"],
                        "display_path": doc_data["display_path"],
                        "icon": doc_data["icon"],
                        "ext": doc_data["ext"],
                        "page": page["page_num"],
                        "total_pages": doc_data["total_pages"],
                        "section": sec_title or f"Sin sección detectada",
                        "matches": sec_matches,
                        "score": score + (10 if sec_title else 0),
                    })
            elif is_pdf:
                doc_count += 1
                results.append({
                    "document": doc_data["name"],
                    "display_path": doc_data["display_path"],
                    "icon": doc_data["icon"],
                    "ext": doc_data["ext"],
                    "page": page["page_num"],
                    "total_pages": doc_data["total_pages"],
                    "section": f"Página {page['page_num']}",
                    "matches": matches,
                    "score": score,
                })
            else:
                # CSV content match — show matching rows only
                result = {
                    "document": doc_data["name"],
                    "display_path": doc_data["display_path"],
                    "icon": doc_data["icon"],
                    "ext": doc_data["ext"],
                    "page": page["page_num"],
                    "total_pages": doc_data["total_pages"],
                    "section": None,
                    "matches": matches,
                    "score": score,
                }
                if page.get("csv_headers") and page.get("csv_rows"):
                    headers = page["csv_headers"]
                    matched_rows = []
                    for row in page["csv_rows"]:
                        row_text = normalize(" ".join(row))
                        if any(term in row_text for term in terms):
                            matched_rows.append(row)
                    result["csv_headers"] = headers
                    result["csv_rows"] = matched_rows[:5]
                doc_count += 1
                results.append(result)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def assign_matches_to_sections(matches, sections):
    """Assign each match to the section it belongs to. Returns list of (title, [matches])."""
    if not sections:
        return [(None, matches)]

    groups = {}
    for match in matches:
        pos = match["position"]
        # Find the last section that starts before this match
        current_section = None
        for sec in sections:
            if sec["position"] <= pos:
                current_section = sec["title"]
            else:
                break

        key = current_section
        if key not in groups:
            groups[key] = []
        groups[key].append(match)

    return [(title, ms) for title, ms in groups.items()]


# Se construye al importar el módulo -> funciona tanto con `python app.py`
# como con gunicorn (que solo hace `import app`).
print("Indexando archivos...")
docs_cache = build_index()
print(f"Indexados {len(docs_cache)} archivos")


def safe_path(filename):
    """Resuelve filename dentro de DATA_DIR y bloquea cualquier intento de
    escapar del directorio (path traversal, ej. /pdf/../../etc/passwd)."""
    candidate = (DATA_DIR / filename).resolve()
    if not candidate.is_relative_to(DATA_DIR.resolve()):
        abort(404)
    return candidate


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    doc_filter = request.args.get("doc", "").strip()

    if not query:
        return jsonify({"results": [], "query": "", "total": 0})

    if doc_filter:
        keys = [k.strip() for k in doc_filter.split(",") if k.strip()]
        filtered = {k: v for k, v in docs_cache.items() if k in keys}
        results = search_docs(query, filtered)
    else:
        results = search_docs(query, docs_cache)

    return jsonify({"results": results, "query": query, "total": len(results)})


@app.route("/pdf/<path:filename>")
def serve_pdf(filename):
    """Serve a PDF file for viewing in browser."""
    pdf_path = safe_path(filename)
    if pdf_path.exists() and pdf_path.suffix.lower() == ".pdf":
        return send_file(pdf_path, mimetype="application/pdf")
    abort(404)


@app.route("/view/<path:filename>")
def view_file(filename):
    """View a text file with context around a specific line."""
    line = request.args.get("line", 1, type=int)
    query = request.args.get("q", "")

    file_path = safe_path(filename)

    if not file_path.exists() or file_path.suffix.lower() == ".pdf":
        abort(404)

    try:
        content = file_path.read_text(errors="ignore")
        lines = content.split("\n")
    except Exception:
        abort(500)

    csv_data = None
    if file_path.suffix.lower() == ".csv":
        import csv as _csv
        with open(file_path, newline='', errors="ignore") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = _csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except _csv.Error:
                dialect = _csv.excel
            reader = _csv.reader(f, dialect)
            all_rows = list(reader)
        if all_rows:
            csv_data = {"headers": all_rows[0], "rows": all_rows[1:]}

    total_lines = len(lines)
    context = 40
    start = max(0, line - context - 1)
    end = min(total_lines, line + context)
    visible_lines = lines[start:end]

    return render_template(
        "view.html",
        filename=filename,
        display_path=filename,
        content=visible_lines,
        start_line=start + 1,
        hidden_above=start,
        hidden_below=total_lines - end,
        highlight_line=line,
        total_lines=total_lines,
        query=query,
        csv_data=csv_data,
    )


@app.route("/api/docs")
def api_docs():
    docs_list = [
        {
            "key": key,
            "name": data["name"],
            "display_path": data["display_path"],
            "ext": data["ext"],
            "icon": data["icon"],
            "pages": data["total_pages"],
        }
        for key, data in docs_cache.items()
    ]
    docs_list.sort(key=lambda d: d["display_path"])
    return jsonify({"docs": docs_list})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5500, debug=False)
