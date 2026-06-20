"""
Import service - Extraction d'ordres d'investissement depuis n'importe quel
document (CSV, capture d'écran, PDF) à l'aide d'un LLM.

Architecture multi-fournisseur :
- Un seul client *compatible OpenAI* (paramétré par base_url + clé) sert
  OpenAI, Qwen (Alibaba Model Studio), DeepSeek et MiniMax.
- Claude utilise le SDK Anthropic natif.
- Les PDF sont rastérisés en images (PyMuPDF) pour fonctionner uniformément
  sur tous les modèles multimodaux.

Ajouter un modèle = ajouter une entrée dans MODEL_REGISTRY (aucune autre
modification de code nécessaire pour les fournisseurs compatibles OpenAI).
"""

import os
import re
import json
import math
import base64
import logging
import unicodedata
from functools import lru_cache
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Fichier de correspondance nom de fonds -> code ISIN (produit par un scraper
# externe). Formats acceptés : {"nom": "ISIN", ...} ou [{"name": ..., "isin": ...}].
ISIN_MAP_PATH = os.environ.get(
    "ISIN_MAP_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "isin_map.json"),
)

# Limites de garde
MAX_FILE_SIZE = 10 * 1024 * 1024      # 10 Mo
MAX_PDF_PAGES = 15                     # pages rastérisées au maximum
PDF_RENDER_DPI = 150                   # résolution de rastérisation des PDF

# Types MIME acceptés
IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
TEXT_MIME_TYPES = {"text/csv", "text/plain", "application/csv", "text/tab-separated-values"}
PDF_MIME_TYPE = "application/pdf"


# ============================================================================
# Schémas de sortie structurée
# ============================================================================

class ParsedOrder(BaseModel):
    """Un ordre/transaction extrait du document."""
    date: Optional[str] = None             # ISO YYYY-MM-DD
    isin: Optional[str] = None             # peut manquer (ex. screenshot)
    name: Optional[str] = None             # nom du fonds/ETF tel que lu
    quantity: Optional[float] = None
    unit_price_eur: Optional[float] = None
    total_eur: Optional[float] = None
    side: Optional[str] = None             # "buy" / "sell"
    confidence: Optional[float] = None     # 0..1, pour signaler les lignes douteuses


class ImportResult(BaseModel):
    """Résultat global de l'extraction."""
    orders: List[ParsedOrder] = []
    declared_total_eur: Optional[float] = None   # total global lu dans le document
    currency_warning: Optional[str] = None       # ex. devise ≠ EUR détectée


# ============================================================================
# Registre des modèles
# ============================================================================

@dataclass
class ModelSpec:
    key: str               # identifiant interne (utilisé par l'UI)
    label: str             # libellé affiché
    provider: str          # 'anthropic' | 'openai_compatible'
    model_id: str          # identifiant côté API du fournisseur
    price_in: float        # $ / 1M tokens (indicatif)
    price_out: float       # $ / 1M tokens (indicatif)
    multimodal: bool       # accepte images / PDF
    api_key_env: str       # variable d'env contenant la clé
    base_url_env: Optional[str] = None   # variable d'env de surcharge du endpoint
    default_base_url: Optional[str] = None
    note: str = ""

    def resolve_base_url(self) -> Optional[str]:
        if self.base_url_env and os.environ.get(self.base_url_env):
            return os.environ[self.base_url_env]
        return self.default_base_url

    def has_credentials(self) -> bool:
        return bool(os.environ.get(self.api_key_env))


# L'ordre de la liste = ordre d'affichage dans le sélecteur.
MODEL_REGISTRY: List[ModelSpec] = [
    ModelSpec(
        key="qwen3-vl-plus",
        label="Qwen3-VL-Plus (Alibaba) — spécialiste documents",
        provider="openai_compatible",
        model_id=os.environ.get("QWEN_MODEL_ID", "qwen3-vl-plus"),
        price_in=0.30, price_out=1.20, multimodal=True,
        api_key_env="DASHSCOPE_API_KEY",
        base_url_env="DASHSCOPE_BASE_URL",
        default_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        note="Spécialisé extraction documents/OCR, meilleur rapport perf/prix.",
    ),
    ModelSpec(
        key="gpt-5-mini",
        label="GPT-5 mini (OpenAI)",
        provider="openai_compatible",
        model_id=os.environ.get("OPENAI_MODEL_ID", "gpt-5-mini"),
        price_in=0.25, price_out=2.00, multimodal=True,
        api_key_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        default_base_url=None,   # endpoint OpenAI par défaut
        note="Sortie structurée fiable, peu d'hallucinations.",
    ),
    ModelSpec(
        key="minimax-m3",
        label="MiniMax M3 — contexte 1M",
        provider="openai_compatible",
        model_id=os.environ.get("MINIMAX_MODEL_ID", "MiniMax-M3"),
        price_in=0.60, price_out=2.30, multimodal=True,
        api_key_env="MINIMAX_API_KEY",
        base_url_env="MINIMAX_BASE_URL",
        default_base_url="https://api.minimax.io/v1",
        note="Généraliste multimodal, très grand contexte.",
    ),
    ModelSpec(
        key="claude-haiku-4-5",
        label="Claude Haiku 4.5 (Anthropic)",
        provider="anthropic",
        model_id="claude-haiku-4-5",
        price_in=1.0, price_out=5.0, multimodal=True,
        api_key_env="ANTHROPIC_API_KEY",
        note="Rapide, sortie propre.",
    ),
    ModelSpec(
        key="claude-sonnet-4-6",
        label="Claude Sonnet 4.6 (Anthropic)",
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        price_in=3.0, price_out=15.0, multimodal=True,
        api_key_env="ANTHROPIC_API_KEY",
        note="Équilibré perf/prix.",
    ),
    ModelSpec(
        key="claude-opus-4-8",
        label="Claude Opus 4.8 (Anthropic) — précision max",
        provider="anthropic",
        model_id="claude-opus-4-8",
        price_in=5.0, price_out=25.0, multimodal=True,
        api_key_env="ANTHROPIC_API_KEY",
        note="Précision maximale sur screenshots/PDF difficiles.",
    ),
    ModelSpec(
        key="deepseek-v4-flash",
        label="DeepSeek V4 Flash — texte/CSV uniquement",
        provider="openai_compatible",
        model_id=os.environ.get("DEEPSEEK_MODEL_ID", "deepseek-chat"),
        price_in=0.14, price_out=0.28, multimodal=False,
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_BASE_URL",
        default_base_url="https://api.deepseek.com/v1",
        note="Le moins cher, mais ne lit pas les images / PDF scannés.",
    ),
]

_REGISTRY_BY_KEY = {spec.key: spec for spec in MODEL_REGISTRY}
DEFAULT_MODEL_KEY = os.environ.get("IMPORT_MODEL", "qwen3-vl-plus")


class ImportError_(Exception):
    """Erreur fonctionnelle d'import (message destiné à l'utilisateur)."""


def get_registry_public() -> Dict[str, Any]:
    """Registre exposé au front (sans secrets), avec dispo et défaut."""
    default_key = DEFAULT_MODEL_KEY if DEFAULT_MODEL_KEY in _REGISTRY_BY_KEY else "qwen3-vl-plus"
    return {
        "default": default_key,
        "models": [
            {
                "key": s.key,
                "label": s.label,
                "provider": s.provider,
                "priceIn": s.price_in,
                "priceOut": s.price_out,
                "multimodal": s.multimodal,
                "available": s.has_credentials(),
                "note": s.note,
            }
            for s in MODEL_REGISTRY
        ],
    }


def resolve_model(model_key: Optional[str]) -> ModelSpec:
    """Résout la clé reçue de l'UI ; repli sur le défaut si inconnue."""
    if model_key and model_key in _REGISTRY_BY_KEY:
        return _REGISTRY_BY_KEY[model_key]
    if DEFAULT_MODEL_KEY in _REGISTRY_BY_KEY:
        return _REGISTRY_BY_KEY[DEFAULT_MODEL_KEY]
    return _REGISTRY_BY_KEY["qwen3-vl-plus"]


# ============================================================================
# Construction des "parts" (texte + images) à partir du fichier
# ============================================================================

@dataclass
class ContentPart:
    kind: str                      # 'text' | 'image'
    text: Optional[str] = None
    image_b64: Optional[str] = None
    media_type: Optional[str] = None


def _normalize_mime(filename: str, mime_type: str) -> str:
    mime = (mime_type or "").lower().split(";")[0].strip()
    name = (filename or "").lower()
    if mime in IMAGE_MIME_TYPES or mime in TEXT_MIME_TYPES or mime == PDF_MIME_TYPE:
        return mime
    # Repli sur l'extension
    if name.endswith(".pdf"):
        return PDF_MIME_TYPE
    if name.endswith((".png",)):
        return "image/png"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith((".webp",)):
        return "image/webp"
    if name.endswith((".gif",)):
        return "image/gif"
    if name.endswith((".csv", ".txt", ".tsv")):
        return "text/csv"
    return mime or "application/octet-stream"


def _rasterize_pdf(content: bytes) -> List[ContentPart]:
    """Rastérise chaque page du PDF en PNG (max MAX_PDF_PAGES)."""
    import fitz  # PyMuPDF
    parts: List[ContentPart] = []
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        for page in doc[:MAX_PDF_PAGES]:
            pix = page.get_pixmap(dpi=PDF_RENDER_DPI)
            png_bytes = pix.tobytes("png")
            parts.append(ContentPart(
                kind="image",
                image_b64=base64.standard_b64encode(png_bytes).decode("utf-8"),
                media_type="image/png",
            ))
    finally:
        doc.close()
    if not parts:
        raise ImportError_("Le PDF ne contient aucune page exploitable.")
    return parts


def _build_parts(filename: str, content: bytes, mime_type: str, spec: ModelSpec) -> List[ContentPart]:
    """Transforme le fichier en parts texte/image, en validant le type."""
    if len(content) > MAX_FILE_SIZE:
        raise ImportError_("Fichier trop volumineux (max 10 Mo).")

    mime = _normalize_mime(filename, mime_type)

    if mime in TEXT_MIME_TYPES:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            decoded = content.decode("latin-1", errors="replace")
        return [ContentPart(kind="text", text=f"Contenu du fichier `{filename}` :\n\n{decoded}")]

    # À partir d'ici : image ou PDF → nécessite un modèle multimodal
    if not spec.multimodal:
        raise ImportError_(
            f"Le modèle « {spec.label} » ne lit pas les images/PDF. "
            "Choisis un modèle multimodal (Qwen3-VL, GPT-5 mini, MiniMax, Claude) "
            "ou dépose un fichier CSV/texte."
        )

    if mime in IMAGE_MIME_TYPES:
        media = "image/jpeg" if mime == "image/jpg" else mime
        return [ContentPart(
            kind="image",
            image_b64=base64.standard_b64encode(content).decode("utf-8"),
            media_type=media,
        )]

    if mime == PDF_MIME_TYPE:
        return _rasterize_pdf(content)

    raise ImportError_(
        f"Type de fichier non supporté ({mime}). "
        "Formats acceptés : CSV/texte, PNG/JPEG/WebP/GIF, PDF. "
        "(Pour un .xlsx, exporte d'abord en CSV.)"
    )


# ============================================================================
# Prompt
# ============================================================================

SYSTEM_PROMPT = (
    "Tu es un assistant d'extraction de transactions financières. À partir du "
    "document fourni (export CSV, capture d'écran d'un portefeuille de courtier, "
    "ou PDF de relevé), extrais UNIQUEMENT les ordres d'ACHAT de titres "
    "(ETF, actions, fonds).\n\n"
    "EXCLUS impérativement (ne les renvoie pas) : virements, dépôts d'espèces, "
    "retraits, ventes, dividendes, coupons, intérêts, frais, taxes, et toute "
    "ligne qui n'est pas l'achat d'un instrument financier.\n\n"
    "Règles :\n"
    "- Normalise les dates au format ISO AAAA-MM-JJ.\n"
    "- N'INVENTE JAMAIS d'ISIN : si l'ISIN n'est pas lisible, laisse-le à null.\n"
    "- `name` = nom du fonds/ETF/action tel qu'affiché (important : il sert à "
    "retrouver l'ISIN s'il manque).\n"
    "- `side` = \"buy\" pour chaque ligne renvoyée.\n"
    "- `unit_price_eur` et `total_eur` : montants en euros si disponibles, sinon null.\n"
    "- `confidence` entre 0 et 1 pour signaler les lignes douteuses.\n"
    "- Si un total global du portefeuille/relevé est visible, reporte-le dans "
    "`declared_total_eur`.\n"
    "- Si une devise différente de l'EUR est détectée, explique-le brièvement dans "
    "`currency_warning`.\n"
)

USER_INSTRUCTION = "Extrais tous les ordres de ce document."


# ============================================================================
# Adaptateurs fournisseurs
# ============================================================================

def _extract_anthropic(spec: ModelSpec, parts: List[ContentPart]) -> ImportResult:
    import anthropic

    if not spec.has_credentials():
        raise ImportError_("Clé ANTHROPIC_API_KEY absente (configure-la dans .env).")

    client = anthropic.Anthropic(api_key=os.environ[spec.api_key_env])

    content_blocks: List[Dict[str, Any]] = []
    for p in parts:
        if p.kind == "text":
            content_blocks.append({"type": "text", "text": p.text})
        else:
            content_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": p.media_type, "data": p.image_b64},
            })
    content_blocks.append({"type": "text", "text": USER_INSTRUCTION})

    try:
        response = client.messages.parse(
            model=spec.model_id,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content_blocks}],
            output_format=ImportResult,
        )
        return response.parsed_output
    except anthropic.APIStatusError as e:
        raise ImportError_(f"Erreur Anthropic ({e.status_code}) : {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise ImportError_("Connexion à l'API Anthropic impossible.") from e


def _extract_openai_compatible(spec: ModelSpec, parts: List[ContentPart]) -> ImportResult:
    from openai import OpenAI, APIError, APIConnectionError

    if not spec.has_credentials():
        raise ImportError_(
            f"Clé {spec.api_key_env} absente pour « {spec.label} » (configure-la dans .env)."
        )

    client = OpenAI(
        api_key=os.environ[spec.api_key_env],
        base_url=spec.resolve_base_url(),
    )

    user_content: List[Dict[str, Any]] = [{"type": "text", "text": USER_INSTRUCTION}]
    for p in parts:
        if p.kind == "text":
            user_content.append({"type": "text", "text": p.text})
        else:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{p.media_type};base64,{p.image_b64}"},
            })

    # JSON mode portable : on fournit le schéma dans le prompt et on valide nous-mêmes.
    schema_hint = json.dumps(ImportResult.model_json_schema(), ensure_ascii=False)
    system = (
        SYSTEM_PROMPT
        + "\n\nRéponds STRICTEMENT en JSON valide respectant ce schéma "
        f"(clés exactes, pas de texte autour) :\n{schema_hint}"
    )

    # OpenAI natif (base_url par défaut) attend `max_completion_tokens` pour les
    # modèles récents (GPT-5…) ; les endpoints compatibles tiers gardent `max_tokens`.
    token_param = "max_completion_tokens" if spec.default_base_url is None else "max_tokens"
    request_kwargs: Dict[str, Any] = {
        "model": spec.model_id,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        token_param: 8000,
    }

    try:
        resp = client.chat.completions.create(**request_kwargs)
    except APIConnectionError as e:
        raise ImportError_(f"Connexion à l'API ({spec.label}) impossible.") from e
    except APIError as e:
        raise ImportError_(f"Erreur API ({spec.label}) : {getattr(e, 'message', str(e))}") from e

    text = (resp.choices[0].message.content or "").strip()
    try:
        return ImportResult.model_validate_json(text)
    except Exception:
        # Repli : tenter d'isoler le bloc JSON
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return ImportResult.model_validate_json(text[start:end + 1])
            except Exception as e:
                raise ImportError_(
                    f"Le modèle « {spec.label} » n'a pas renvoyé de JSON exploitable."
                ) from e
        raise ImportError_(
            f"Le modèle « {spec.label} » n'a pas renvoyé de JSON exploitable."
        )


# ============================================================================
# Post-traitement : ne garder que les achats + résolution ISIN par nom
# ============================================================================

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

# Côtés/types qui ne sont PAS des achats → exclus
NON_BUY_SIDES = {
    "sell", "vente", "sale", "withdrawal", "retrait", "transfer", "virement",
    "deposit", "depot", "dépôt", "dividend", "dividende", "fee", "frais",
    "interest", "interet", "intérêt", "tax", "taxe", "impot", "impôt",
}


def _is_buy(order: ParsedOrder) -> bool:
    """Vrai si la ligne est un achat (ou côté indéterminé = supposé achat)."""
    side = (order.side or "").strip().lower()
    return side not in NON_BUY_SIDES


def _normalize_name(name: str) -> str:
    """Normalise un nom de fonds pour la correspondance (sans accents, minuscules)."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Canonicalisation des variantes d'écriture d'un même concept, pour que par ex.
# « Distributing », « Dist », « (D) » comptent comme le même token. On NE
# fusionne PAS acc/dist entre eux (ce sont des ISIN différents) : on unifie
# seulement les notations d'une même classe de part.
_TOKEN_SYNONYMS = {
    "accumulating": "acc", "accumulation": "acc", "capi": "acc",
    "capitalisation": "acc", "capitalising": "acc", "cap": "acc", "c": "acc",
    "distributing": "dist", "distribution": "dist", "distrib": "dist",
    "d": "dist",
    "hdg": "hedged", "hgd": "hedged",
}

# Tokens trop génériques pour discriminer (présents dans presque toutes les
# lignes) : on les ignore pour ne pas gonfler artificiellement les scores.
_STOP_TOKENS = {"ucits", "etf", "etc", "the", "fund", "index", "ii", "i"}


def _tokenize(name: str) -> Tuple[str, ...]:
    """Découpe un nom normalisé en tokens canoniques (synonymes unifiés)."""
    norm = _normalize_name(name)
    if not norm:
        return tuple()
    toks = [_TOKEN_SYNONYMS.get(t, t) for t in norm.split()]
    toks = [t for t in toks if t not in _STOP_TOKENS]
    return tuple(toks)


@lru_cache(maxsize=1)
def _load_isin_map() -> Tuple[Tuple[str, str, Tuple[str, ...]], ...]:
    """Charge le fichier de correspondance nom→ISIN (mis en cache).

    Renvoie un tuple de (nom_normalisé, ISIN, tokens). Tolère un dict ou une liste.
    """
    path = ISIN_MAP_PATH
    if not os.path.exists(path):
        return tuple()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("Lecture du fichier ISIN échouée (%s): %s", path, e)
        return tuple()

    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = [(d.get("name"), d.get("isin")) for d in raw if isinstance(d, dict)]
    else:
        items = []

    entries: List[Tuple[str, str, Tuple[str, ...]]] = []
    for name, isin in items:
        norm = _normalize_name(name or "")
        isin = (isin or "").strip().upper()
        if norm and ISIN_RE.match(isin):
            entries.append((norm, isin, _tokenize(name or "")))
    return tuple(entries)


@lru_cache(maxsize=1)
def _idf() -> Dict[str, float]:
    """Poids IDF de chaque token sur le corpus (un mot rare discrimine plus)."""
    entries = _load_isin_map()
    n = len(entries) or 1
    df: Dict[str, int] = {}
    for _, _, toks in entries:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    return {t: math.log((n + 1) / (c + 0.5)) + 1.0 for t, c in df.items()}


# Seuil de similarité cosinus en dessous duquel on refuse de deviner un ISIN
# (mieux vaut laisser l'ISIN vide qu'attribuer le mauvais fonds).
_MATCH_THRESHOLD = 0.45


def _idf_w(token: str, idf: Dict[str, float]) -> float:
    """Poids d'un token ; un token inconnu du corpus reste discriminant."""
    return idf.get(token, max(idf.values()) if idf else 1.0)


def _resolve_isin(name: str) -> Optional[str]:
    """Trouve l'ISIN correspondant à un nom via le fichier de correspondance.

    Stratégie permissive :
      1) correspondance exacte (nom normalisé) ;
      2) sinon similarité cosinus pondérée IDF entre les tokens lus et ceux de
         chaque entrée — la meilleure au-dessus du seuil gagne. Les notations de
         classe de part sont unifiées (Dist/(D), Acc/(C)…) et les mots
         génériques (UCITS, ETF…) ignorés, ce qui tolère ordre des mots,
         devise, tickers parasites et suffixes manquants.
    """
    entries = _load_isin_map()
    if not entries or not name:
        return None

    target_norm = _normalize_name(name)
    if not target_norm:
        return None

    # 1) exact (normalisé)
    for norm, isin, _ in entries:
        if norm == target_norm:
            return isin

    # 2) cosinus IDF sur les tokens
    q_tokens = set(_tokenize(name))
    if not q_tokens:
        return None
    idf = _idf()
    q_norm = math.sqrt(sum(_idf_w(t, idf) ** 2 for t in q_tokens))
    if q_norm == 0:
        return None

    best_isin, best_score = None, 0.0
    for _, isin, toks in entries:
        d_tokens = set(toks)
        if not d_tokens:
            continue
        inter = q_tokens & d_tokens
        if not inter:
            continue
        num = sum(_idf_w(t, idf) ** 2 for t in inter)
        d_norm = math.sqrt(sum(_idf_w(t, idf) ** 2 for t in d_tokens))
        score = num / (q_norm * d_norm)
        if score > best_score:
            best_isin, best_score = isin, score

    return best_isin if best_score >= _MATCH_THRESHOLD else None


def _postprocess(result: ImportResult) -> ImportResult:
    """Garde uniquement les achats et complète les ISIN manquants via le nom."""
    kept: List[ParsedOrder] = []
    for o in result.orders:
        if not _is_buy(o):
            continue
        # Un achat débite le compte : le document peut afficher les montants en
        # négatif (« -59,60 € »). On ne garde que des magnitudes positives.
        if o.quantity is not None:
            o.quantity = abs(o.quantity)
        if o.unit_price_eur is not None:
            o.unit_price_eur = abs(o.unit_price_eur)
        if o.total_eur is not None:
            o.total_eur = abs(o.total_eur)
        isin = (o.isin or "").strip().upper()
        if not isin or not ISIN_RE.match(isin):
            resolved = _resolve_isin(o.name or "")
            if resolved:
                o.isin = resolved
            else:
                o.isin = isin or None
        else:
            o.isin = isin
        kept.append(o)
    result.orders = kept
    return result


# ============================================================================
# Point d'entrée
# ============================================================================

def _extract_one(spec: ModelSpec, filename: str, content: bytes, mime_type: str) -> ImportResult:
    """Extraction brute d'un fichier (sans post-traitement)."""
    parts = _build_parts(filename, content, mime_type, spec)
    if spec.provider == "anthropic":
        return _extract_anthropic(spec, parts)
    return _extract_openai_compatible(spec, parts)


def parse_orders_from_file(
    filename: str,
    content: bytes,
    mime_type: str,
    model_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Extrait les ordres d'UN fichier (achats uniquement, ISIN complétés).

    Renvoie : { orders, declared_total_eur, currency_warning, model }
    Lève ImportError_ pour les erreurs fonctionnelles (message utilisateur).
    """
    spec = resolve_model(model_key)
    result = _postprocess(_extract_one(spec, filename, content, mime_type))
    return {
        "orders": [o.model_dump() for o in result.orders],
        "declared_total_eur": result.declared_total_eur,
        "currency_warning": result.currency_warning,
        "model": {"key": spec.key, "label": spec.label},
    }


def parse_orders_from_files(
    files: List[Tuple[str, bytes, str]],
    model_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Extrait et fusionne les ordres de PLUSIEURS fichiers.

    `files` = liste de tuples (filename, content, mime_type).
    Renvoie : { orders, declared_total_eur, currency_warning, model, file_errors }
    Une erreur sur un fichier n'interrompt pas les autres (collectée dans
    `file_errors`).
    """
    spec = resolve_model(model_key)

    all_orders: List[ParsedOrder] = []
    declared_totals: List[float] = []
    warnings: List[str] = []
    file_errors: List[Dict[str, str]] = []

    for filename, content, mime_type in files:
        try:
            result = _postprocess(_extract_one(spec, filename, content, mime_type))
            all_orders.extend(result.orders)
            if result.declared_total_eur is not None:
                declared_totals.append(result.declared_total_eur)
            if result.currency_warning:
                warnings.append(f"{filename} : {result.currency_warning}")
        except ImportError_ as fe:
            file_errors.append({"file": filename, "error": str(fe)})
        except Exception as e:  # noqa: BLE001
            logger.exception("Extraction échouée pour %s", filename)
            file_errors.append({"file": filename, "error": str(e)})

    if not all_orders and file_errors and len(file_errors) == len(files):
        # Tous les fichiers ont échoué → remonter la première erreur
        raise ImportError_(file_errors[0]["error"])

    return {
        "orders": [o.model_dump() for o in all_orders],
        "declared_total_eur": round(sum(declared_totals), 2) if declared_totals else None,
        "currency_warning": " · ".join(warnings) if warnings else None,
        "model": {"key": spec.key, "label": spec.label},
        "file_errors": file_errors,
    }
