# -*- coding: utf-8 -*-
"""
CAD Assistant — Proiezioni Ortogonali
Creato da: ENRICO BOTTONE

Avvio:  streamlit run app.py
Requisiti: streamlit>=1.30 (Pillow è già installato come dipendenza di Streamlit)
"""

import base64
import hashlib
import hmac
import io
import json
import math
import re
import os
import secrets
import time
import sqlite3
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageOps

# ----------------------------------------------------------------------------
# CONFIGURAZIONE
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="CAD Assistant — Proiezioni Ortogonali",
    page_icon="📐",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "cad_users.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_MB = 15
ALLOWED_EXT = ["jpg", "jpeg", "png", "webp"]
SCALES = ["1:1", "1:2", "2:1", "1:5", "5:1", "1:10"]

ROLE_DEV = "sviluppatore"
ROLE_STUDENT = "studente"

PBKDF2_ITERATIONS = 200_000


# ----------------------------------------------------------------------------
# DATABASE E AUTENTICAZIONE
# ----------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt_hex: str) -> str:
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS
    )
    return dk.hex()


def create_user(username: str, password: str, role: str) -> None:
    salt = secrets.token_hex(16)
    pwd_hash = hash_password(password, salt)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            (username, pwd_hash, salt, role),
        )


REQUIRED_COLUMNS = {"id", "username", "password_hash", "salt", "role", "created_at"}


def migrate_legacy_table() -> None:
    """Se esiste una vecchia tabella 'users' con schema diverso, la mette da parte."""
    with get_conn() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if cols and not REQUIRED_COLUMNS.issubset(cols):
            conn.execute("DROP TABLE IF EXISTS users_legacy")
            conn.execute("ALTER TABLE users RENAME TO users_legacy")


def init_db() -> None:
    migrate_legacy_table()
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('sviluppatore', 'studente')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = 'DEV'"
        ).fetchone()
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                trace_path TEXT,
                trace_sig TEXT,
                current_step INTEGER NOT NULL DEFAULT 0,
                scale TEXT
            )
            """
        )
    if not exists:
        create_user("DEV", "sviluppatore@", ROLE_DEV)


SESSION_HOURS = 12


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(24)
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) "
            "VALUES (?, ?, datetime('now', ?))",
            (token, user_id, f"+{SESSION_HOURS} hours"),
        )
    return token


def load_session(token: str):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT s.trace_path, s.trace_sig, s.current_step, s.scale,
                   u.id AS user_id, u.username, u.role
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > datetime('now')
            """,
            (token,),
        ).fetchone()


def save_session_state() -> None:
    token = st.session_state.get("token")
    if not token:
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET trace_path = ?, trace_sig = ?, "
            "current_step = ?, scale = ? WHERE token = ?",
            (
                st.session_state.get("trace_path"),
                st.session_state.get("trace_sig"),
                int(st.session_state.get("current_step", 0)),
                st.session_state.get("scale"),
                token,
            ),
        )


def delete_session(token) -> None:
    if not token:
        return
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def restore_login() -> None:
    """Ripristina il login dopo una riconnessione (es. dopo la scelta della foto su mobile)."""
    if st.session_state.user:
        return
    token = st.query_params.get("s")
    if not token:
        return
    row = load_session(token)
    if row is None:
        st.query_params.clear()
        return
    st.session_state.user = {
        "id": row["user_id"],
        "username": row["username"],
        "role": row["role"],
    }
    st.session_state.token = token
    if row["trace_path"] and Path(row["trace_path"]).exists():
        st.session_state.trace_path = row["trace_path"]
        st.session_state.trace_sig = row["trace_sig"]
    st.session_state.current_step = row["current_step"] or 0
    st.session_state.scale = row["scale"] if row["scale"] in SCALES else "1:1"


def authenticate(username: str, password: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None:
        return None
    candidate = hash_password(password, row["salt"])
    if hmac.compare_digest(candidate, row["password_hash"]):
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    return None


def list_students():
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username, created_at FROM users WHERE role = ? ORDER BY username",
            (ROLE_STUDENT,),
        ).fetchall()


def delete_student(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM users WHERE id = ? AND role = ?", (user_id, ROLE_STUDENT)
        )


def reset_student_password(user_id: int, new_password: str) -> None:
    salt = secrets.token_hex(16)
    pwd_hash = hash_password(new_password, salt)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ? AND role = ?",
            (pwd_hash, salt, user_id, ROLE_STUDENT),
        )


# ----------------------------------------------------------------------------
# STILE (DARK MODE)
# ----------------------------------------------------------------------------
CSS = """
<style>
.stApp {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 55%, #0f172a 100%);
    color: #e2e8f0;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1224 0%, #111c3a 100%);
    border-right: 1px solid rgba(148, 163, 184, 0.15);
}
h1, h2, h3, h4 { color: #f8fafc !important; letter-spacing: 0.2px; }

.hero {
    background: linear-gradient(120deg, rgba(56,189,248,0.15), rgba(139,92,246,0.18));
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 20px;
    padding: 1.6rem 1.8rem;
    margin-bottom: 1.4rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
}
.hero h1 { margin: 0 0 0.4rem 0; font-size: 2rem; }
.hero p { margin: 0.2rem 0; color: #cbd5e1; font-size: 1rem; line-height: 1.5; }
.hero .author {
    display: inline-block; margin-top: 0.7rem; padding: 0.25rem 0.8rem;
    border-radius: 999px; background: rgba(56,189,248,0.18);
    color: #7dd3fc; font-weight: 600; font-size: 0.85rem; letter-spacing: 0.5px;
}

.card {
    background: rgba(30, 41, 59, 0.75);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 16px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1rem;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
}
.card h3 { margin-top: 0; color: #7dd3fc !important; }
.card ul { margin: 0.4rem 0 0 1.1rem; }
.card li { margin-bottom: 0.3rem; color: #e2e8f0; }
.step-badge {
    display: inline-block; padding: 0.15rem 0.7rem; border-radius: 999px;
    background: rgba(139,92,246,0.25); color: #c4b5fd;
    font-size: 0.8rem; font-weight: 600; margin-bottom: 0.5rem;
}
.tip {
    border-left: 4px solid #38bdf8; background: rgba(56,189,248,0.08);
    padding: 0.6rem 0.9rem; border-radius: 8px; margin-top: 0.7rem; color: #bae6fd;
}

.stButton > button, .stFormSubmitButton > button {
    background: linear-gradient(90deg, #0ea5e9, #6366f1);
    color: white; border: none; border-radius: 12px;
    padding: 0.55rem 1.3rem; font-weight: 600;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(99, 102, 241, 0.45);
    color: white; border: none;
}
.stButton > button:disabled {
    background: #334155; color: #94a3b8; box-shadow: none; transform: none;
}
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #38bdf8, #8b5cf6);
}
[data-testid="stFileUploader"] section {
    background: rgba(30, 41, 59, 0.6);
    border: 1.5px dashed rgba(125, 211, 252, 0.5);
    border-radius: 14px;
}
.login-wrap { max-width: 460px; margin: 4vh auto 0 auto; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# STATO DI SESSIONE
# ----------------------------------------------------------------------------
def init_state():
    defaults = {
        "user": None,
        "current_step": 0,
        "trace_path": None,
        "trace_sig": None,
        "scale": "1:1",
        "token": None,
        "widget_gen": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def logout():
    delete_session(st.session_state.get("token"))
    st.query_params.clear()
    path = st.session_state.get("trace_path")
    if path and Path(path).exists():
        try:
            Path(path).unlink()
        except OSError:
            pass
    for key in ["user", "current_step", "trace_path", "trace_sig", "scale", "token"]:
        if key in st.session_state:
            del st.session_state[key]


# ----------------------------------------------------------------------------
# SCHERMATA DI LOGIN
# ----------------------------------------------------------------------------
def login_page():
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="hero" style="text-align:center;">
            <h1>📐 CAD Assistant</h1>
            <p>Proiezioni Ortogonali</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Accedi")
    if submitted:
        user = authenticate(username, password)
        if user:
            token = create_session(user["id"])
            st.session_state.user = user
            st.session_state.token = token
            st.query_params["s"] = token
            st.rerun()
        else:
            st.error("Credenziali non valide.")
    st.markdown("</div>", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# GESTIONE UTENTI (SOLO SVILUPPATORE)
# ----------------------------------------------------------------------------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,30}$")


def user_management_page():
    user = st.session_state.user
    if not user or user["role"] != ROLE_DEV:
        st.error("Accesso negato.")
        return

    st.markdown(
        """
        <div class="hero">
            <h1>👥 Gestione Utenti</h1>
            <p>Crea e gestisci gli account con ruolo <b>studente</b>.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_new, tab_list = st.tabs(["➕ Nuovo studente", "📋 Elenco studenti"])

    with tab_new:
        with st.form("new_student_form", clear_on_submit=True):
            new_user = st.text_input("Username studente")
            new_pwd = st.text_input("Password", type="password")
            new_pwd2 = st.text_input("Conferma password", type="password")
            create = st.form_submit_button("Crea account studente")
        if create:
            if not USERNAME_RE.match(new_user or ""):
                st.error("Username non valido: 3-30 caratteri (lettere, numeri, . _ -).")
            elif len(new_pwd) < 6:
                st.error("La password deve avere almeno 6 caratteri.")
            elif new_pwd != new_pwd2:
                st.error("Le password non coincidono.")
            else:
                try:
                    create_user(new_user.strip(), new_pwd, ROLE_STUDENT)
                    st.success(f"Account studente «{new_user.strip()}» creato.")
                except sqlite3.IntegrityError:
                    st.error("Esiste già un utente con questo username.")

    with tab_list:
        students = list_students()
        if not students:
            st.info("Nessuno studente registrato.")
        for s in students:
            with st.expander(f"🎓 {s['username']}  ·  creato il {s['created_at']}"):
                c1, c2 = st.columns([3, 1])
                with c1:
                    pwd = st.text_input(
                        "Nuova password",
                        type="password",
                        key=f"pwd_{s['id']}",
                    )
                    if st.button("Aggiorna password", key=f"upd_{s['id']}"):
                        if len(pwd) < 6:
                            st.error("Minimo 6 caratteri.")
                        else:
                            reset_student_password(s["id"], pwd)
                            st.success("Password aggiornata.")
                with c2:
                    st.write("")
                    st.write("")
                    if st.button("Elimina", key=f"del_{s['id']}"):
                        delete_student(s["id"])
                        st.rerun()


# ----------------------------------------------------------------------------
# GUIDA PASSO-PASSO
# ----------------------------------------------------------------------------
def scale_factor(scale: str) -> float:
    """'1:2' -> 0.5 ; '2:1' -> 2.0 (misura disegno = misura reale * fattore)."""
    a, b = scale.split(":")
    return float(a) / float(b)


def build_steps(scale: str):
    f = scale_factor(scale)
    if scale == "1:1":
        kind = "scala naturale: le misure sul foglio coincidono con quelle reali"
    elif f < 1:
        kind = "scala di riduzione: le misure sul foglio sono più piccole di quelle reali"
    else:
        kind = "scala di ingrandimento: le misure sul foglio sono più grandi di quelle reali"

    return [
        {
            "title": "Analisi della traccia",
            "items": [
                "Osserva la traccia e individua la forma generale del solido o del pezzo.",
                "Identifica fori, smussi, raccordi, gole e sporgenze.",
                "Annota tutte le quote note e individua quelle che mancano.",
                "Stabilisci quali elementi saranno visibili e quali nascosti nelle diverse viste.",
            ],
            "tip": "Una buona lettura della traccia evita errori nelle fasi successive.",
        },
        {
            "title": "Scala e formato del foglio",
            "items": [
                f"Scala scelta: <b>{scale}</b> — {kind}.",
                f"Formula: misura da disegnare = misura reale × <b>{f:g}</b>.",
                "Scegli il formato (A4, A3…) in modo che le tre viste entrino con margini adeguati.",
                "Traccia il riquadro (margini) e predisponi lo spazio per il cartiglio.",
            ],
            "tip": "Le quote scritte restano sempre quelle reali, indipendentemente dalla scala.",
        },
        {
            "title": "Scelta della vista frontale",
            "items": [
                "La vista frontale (prospetto) è quella che descrive meglio la forma del pezzo.",
                "Scegli la posizione di lavoro o d'uso più naturale del pezzo.",
                "Mostra il maggior numero di particolari in vista (meno linee tratteggiate).",
                "Il numero di viste deve essere il minimo necessario per definire completamente l'oggetto.",
            ],
            "tip": "Il pezzo deve essere definito completamente con il minor numero di viste.",
        },
        {
            "title": "Disposizione delle viste (metodo europeo)",
            "items": [
                "Vista frontale in alto a sinistra del foglio.",
                "Pianta (vista dall'alto) <b>sotto</b> la vista frontale.",
                "Vista laterale sinistra <b>a destra</b> della vista frontale.",
                "Lascia tra le viste uno spazio sufficiente per le quote.",
            ],
            "tip": "Nel metodo europeo (primo diedro) l'oggetto si trova fra l'osservatore e il piano di proiezione.",
        },
        {
            "title": "Assi e linee di costruzione",
            "items": [
                "Traccia con linea sottile gli assi di simmetria (linea a tratto e punto).",
                "Disegna le linee di costruzione leggere per gli ingombri massimi.",
                "Prepara la bisettrice a 45° per riportare le misure tra pianta e vista laterale.",
                "Usa matita dura (H/2H) per le linee di costruzione.",
            ],
            "tip": "Le linee di costruzione devono essere leggere: andranno rinforzate solo dove serve.",
        },
        {
            "title": "Proiezione della vista frontale",
            "items": [
                "Riporta larghezza e altezza reali applicando la scala scelta.",
                "Disegna il contorno esterno, poi i particolari interni (fori, smussi).",
                "Evidenzia con linee di richiamo i punti notevoli da proiettare.",
                "Verifica le proporzioni confrontando con la traccia.",
            ],
            "tip": "Lavora dal generale al particolare.",
        },
        {
            "title": "Proiezione della pianta",
            "items": [
                "Proietta verso il basso, con linee verticali, i punti della vista frontale.",
                "Riporta le profondità reali moltiplicate per il fattore di scala.",
                "Disegna contorni e particolari visibili dall'alto.",
                "Controlla che larghezze della pianta e del prospetto coincidano.",
            ],
            "tip": "Le larghezze devono corrispondere perfettamente nelle due viste.",
        },
        {
            "title": "Proiezione della vista laterale",
            "items": [
                "Proietta orizzontalmente le altezze dalla vista frontale.",
                "Riporta le profondità dalla pianta usando la bisettrice a 45°.",
                "Disegna contorni e particolari della vista laterale sinistra.",
                "Controlla che altezze e profondità siano coerenti con le altre viste.",
            ],
            "tip": "La bisettrice a 45° è lo strumento più rapido per trasferire le profondità.",
        },
        {
            "title": "Tipi di linea e parti nascoste",
            "items": [
                "Contorni e spigoli in vista: linea continua grossa.",
                "Spigoli nascosti: linea tratteggiata sottile.",
                "Assi e centri: linea a tratto e punto sottile.",
                "Rinforza i contorni definitivi e cancella le costruzioni superflue.",
            ],
            "tip": "Rispetta le norme UNI/ISO sui tipi e gli spessori di linea.",
        },
        {
            "title": "Quotatura",
            "items": [
                "Quota ogni elemento una sola volta, nella vista dove è più chiaro.",
                "Linee di misura sottili, frecce ben formate, numeri leggibili.",
                "Scrivi le quote reali (non quelle scalate).",
                "Evita quote ridondanti e non quotare sulle linee nascoste.",
            ],
            "tip": "Le quote devono permettere di realizzare il pezzo senza fare misurazioni sul disegno.",
        },
        {
            "title": "Cartiglio e verifica finale",
            "items": [
                "Compila il cartiglio: titolo, scala, data, nome, classe, metodo di proiezione.",
                f"Indica nel cartiglio la scala <b>{scale}</b> e il simbolo del metodo europeo.",
                "Controlla coerenza tra le viste, quote complete, linee corrette.",
                "Ripulisci il foglio e consegna l'elaborato.",
            ],
            "tip": "Una verifica finale accurata fa la differenza nella valutazione.",
        },
    ]


def go_prev():
    if st.session_state.current_step > 0:
        st.session_state.current_step -= 1


def go_next(total: int):
    if st.session_state.current_step < total - 1:
        st.session_state.current_step += 1


def save_upload(uploaded) -> None:
    """Salva il file su disco con getbuffer() e memorizza solo il percorso."""
    size_mb = uploaded.size / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        st.error(f"File troppo grande ({size_mb:.1f} MB). Limite: {MAX_UPLOAD_MB} MB.")
        return

    ext = Path(uploaded.name).suffix.lower()
    if ext.lstrip(".") not in ALLOWED_EXT:
        st.error("Formato non supportato.")
        return

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with open(dest, "wb") as f:
        f.write(uploaded.getbuffer())

    # Verifica che sia davvero un'immagine valida (senza caricarla tutta in memoria)
    try:
        with Image.open(dest) as img:
            img.verify()
    except Exception:
        dest.unlink(missing_ok=True)
        st.error("Il file caricato non è un'immagine valida.")
        return

    # Elimina la traccia precedente
    old = st.session_state.get("trace_path")
    if old and Path(old).exists():
        try:
            Path(old).unlink()
        except OSError:
            pass

    st.session_state.trace_path = str(dest)
    st.session_state.trace_sig = f"{uploaded.name}-{uploaded.size}"
    st.session_state.current_step = 0


def remove_trace():
    old = st.session_state.get("trace_path")
    if old and Path(old).exists():
        try:
            Path(old).unlink()
        except OSError:
            pass
    st.session_state.trace_path = None
    st.session_state.trace_sig = None
    st.session_state.current_step = 0
    st.session_state.widget_gen += 1


# ----------------------------------------------------------------------------
# MODELLO 3D DEL SOLIDO E PROIEZIONI (metodo europeo, 1° diedro)
# ----------------------------------------------------------------------------
# Il solido e' descritto come unione (op "add") meno sottrazioni (op "sub") di parti:
#   box       {"op","tipo":"box","x":[x0,x1],"y":[y0,y1],"z":[z0,z1]}
#   prisma    {"op","tipo":"prisma","asse":"z|x|y","profilo":[[a,b],...],"da":t0,"a":t1}
#   cilindro  {"op","tipo":"cilindro","asse":"z|x|y","centro":[a,b],"raggio":r,"da":t0,"a":t1}
# Assi: x = larghezza (sinistra->destra in vista frontale), y = altezza (basso->alto),
#       z = profondita' (z=0 faccia frontale, cresce verso il fondo).
# Coordinate del profilo/centro: asse z -> (x,y); asse x -> (y,z); asse y -> (x,z).
SHEETS = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420)}

LINE_STYLES = {
    "v": 'stroke="#111827" stroke-width="0.6" stroke-linecap="round"',
    "t": 'stroke="#6b7280" stroke-width="0.2"',
    "h": 'stroke="#111827" stroke-width="0.35" stroke-dasharray="3 1.5"',
    "a": 'stroke="#374151" stroke-width="0.25" stroke-dasharray="9 1.5 1.5 1.5"',
}

AX = {"x": 0, "y": 1, "z": 2}
CYL_FACETS = 96          # multiplo di 4
MAX_PARTS = 40
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-flash-latest"]

GEMINI_PROMPT = """Sei un esperto di disegno tecnico. L'immagine mostra l'esercizio di un libro di disegno
(di solito un solido in assonometria o prospettiva con le quote, a volte con le viste).
Ricostruisci il solido in 3D e restituisci SOLO un oggetto JSON (nessun testo fuori dal JSON).

Sistema di assi (millimetri): x = larghezza (da sinistra a destra nella vista frontale),
y = altezza (dal basso verso l'alto), z = profondita' (z=0 e' la faccia frontale, z cresce verso il fondo).
Scegli come vista frontale la faccia piu' significativa del solido.

Il solido e' l'unione delle parti con "op":"add" meno le parti con "op":"sub" (fori, scassi, gole).
Tipi di parte:
- {"op":"add","tipo":"box","x":[x0,x1],"y":[y0,y1],"z":[z0,z1]}
- {"op":"add","tipo":"prisma","asse":"z","profilo":[[a,b],...],"da":t0,"a":t1}
  poligono estruso lungo l'asse indicato; coordinate del profilo: asse z -> [x,y]; asse x -> [y,z]; asse y -> [x,z].
  Serve per esagoni, triangoli, trapezi, smussi, cunei. Calcola tu le coordinate esatte (2 decimali).
- {"op":"add","tipo":"cilindro","asse":"z","centro":[a,b],"raggio":r,"da":t0,"a":t1}
  centro: asse z -> [x,y]; asse x -> [y,z]; asse y -> [x,z].
Regole: i fori/scassi ("sub") devono sporgere di 1 mm oltre le facce che attraversano se sono passanti.
Suggerimenti: una scanalatura o asola con fondo/estremita' arrotondata = box + cilindro da togliere; una faccia
inclinata o uno smusso = prisma con profilo poligonale; un foro cieco = cilindro "sub" che NON attraversa tutto.
Controlla che le quote parziali sommate diano la quota totale e che ogni quota dell'immagine sia rispettata.
In assonometria la direzione inclinata e' la profondita' z. Non inventare parti che non si vedono.
Usa le quote scritte sull'esercizio; se una quota manca, stimala dalle proporzioni. Il solido puo' essere
composto da piu' parti "add" che si toccano o si sovrappongono.

Formato di risposta:
{"titolo":"Esercitazione N","scala":"1:1","descrizione":"breve descrizione in italiano",
 "parti":[ ... ]}
("scala" e' quella indicata nel testo dell'esercizio, oppure null.)

Esempio: parallelepipedo 40x20x30 con foro cilindrico passante di diametro 10 lungo z al centro:
{"titolo":"Esempio","scala":null,"descrizione":"Blocco con foro","parti":[
 {"op":"add","tipo":"box","x":[0,40],"y":[0,20],"z":[0,30]},
 {"op":"sub","tipo":"cilindro","asse":"z","centro":[20,10],"raggio":5,"da":-1,"a":31}]}"""


def example_14_json():
    """Esercitazione 14: prisma esagonale regolare (lato 24) con foro quadrato 18 passante, profondita' 20."""
    L = 24.0
    ah = L * math.sqrt(3) / 2
    cx, cy = L, ah
    prof = [
        [cx + L, cy], [cx + L / 2, cy + ah], [cx - L / 2, cy + ah],
        [cx - L, cy], [cx - L / 2, cy - ah], [cx + L / 2, cy - ah],
    ]
    prof = [[round(a, 3), round(b, 3)] for a, b in prof]
    q = 9.0
    data = {
        "titolo": "Esercitazione 14",
        "scala": "1:1",
        "descrizione": "Prisma esagonale regolare (lato 24) con foro quadrato passante 18x18, profondità 20.",
        "parti": [
            {"op": "add", "tipo": "prisma", "asse": "z", "profilo": prof, "da": 0, "a": 20},
            {"op": "sub", "tipo": "box", "x": [cx - q, cx + q], "y": [round(cy - q, 3), round(cy + q, 3)], "z": [-1, 21]},
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=1)


# ---------------------------- Geometria di base ------------------------------
def _perp(axis):
    return {"z": (0, 1), "x": (1, 2), "y": (0, 2)}[axis]


def _cross2(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _poly_ccw(poly):
    n = len(poly)
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    return poly if area > 0 else poly[::-1]


def _is_convex(poly):
    n = len(poly)
    return all(_cross2(poly[i], poly[(i + 1) % n], poly[(i + 2) % n]) >= -1e-9 for i in range(n))


def _in_tri(p, a, b, c):
    return _cross2(a, b, p) >= -1e-9 and _cross2(b, c, p) >= -1e-9 and _cross2(c, a, p) >= -1e-9


def _triangulate(poly):
    """Ear clipping: scompone un poligono (CCW) in triangoli, che sono sempre convessi."""
    idx = list(range(len(poly)))
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 2000:
        guard += 1
        found = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if _cross2(a, b, c) <= 1e-9:
                continue
            if any(_in_tri(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append([a, b, c])
            idx.pop(k)
            found = True
            break
        if not found:
            raise ValueError("profilo non valido (lati che si incrociano?)")
    tris.append([poly[i] for i in idx])
    return tris


def _piece(poly, axis, t0, t1, cid=None):
    """Poligono convesso CCW, nel piano perpendicolare a 'axis', esteso da t0 a t1."""
    ia, ib = _perp(axis)
    ax = AX[axis]
    n = len(poly)
    A, d, tags, verts = [], [], [], []
    for k in range(n):
        p, q = poly[k], poly[(k + 1) % n]
        ex, ey = q[0] - p[0], q[1] - p[1]
        length = math.hypot(ex, ey)
        if length < 1e-9:
            continue
        n2 = (ey / length, -ex / length)
        v = [0.0, 0.0, 0.0]
        v[ia], v[ib] = n2
        A.append(v)
        d.append(n2[0] * p[0] + n2[1] * p[1])
        tags.append((cid, k, n) if cid is not None else None)
    for sgn, t in ((1.0, t1), (-1.0, -t0)):
        v = [0.0, 0.0, 0.0]
        v[ax] = sgn
        A.append(v)
        d.append(t)
        tags.append(None)
    for p in poly:
        for t in (t0, t1):
            q = [0.0, 0.0, 0.0]
            q[ia], q[ib], q[ax] = p[0], p[1], t
            verts.append(q)
    return np.array(A), np.array(d), tags, np.array(verts)


def _num(v, what):
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"valore non numerico in {what}")


def _parts_to_pieces(data, shift):
    parts = data.get("parti")
    if not isinstance(parts, list) or not parts:
        raise ValueError("manca l'elenco 'parti'")
    if len(parts) > MAX_PARTS:
        raise ValueError(f"troppe parti (massimo {MAX_PARTS})")
    pieces, cyls = [], []
    cid = 0
    for p in parts:
        op = p.get("op", "add")
        if op not in ("add", "sub"):
            raise ValueError("'op' deve essere add o sub")
        tipo = p.get("tipo")
        shapes = []
        if tipo == "box":
            x0, x1 = sorted(_num(v, "box.x") for v in p["x"])
            y0, y1 = sorted(_num(v, "box.y") for v in p["y"])
            z0, z1 = sorted(_num(v, "box.z") for v in p["z"])
            sx, sy, sz = shift
            poly = [[x0 - sx, y0 - sy], [x1 - sx, y0 - sy], [x1 - sx, y1 - sy], [x0 - sx, y1 - sy]]
            shapes.append((poly, "z", z0 - sz, z1 - sz, None))
        elif tipo == "prisma":
            axis = p.get("asse", "z")
            if axis not in AX:
                raise ValueError("'asse' deve essere x, y o z")
            ia, ib = _perp(axis)
            ax = AX[axis]
            prof = p["profilo"]
            if len(prof) < 3:
                raise ValueError("il profilo ha meno di 3 punti")
            poly = [[_num(a, "profilo") - shift[ia], _num(b, "profilo") - shift[ib]] for a, b in prof]
            t0, t1 = sorted((_num(p["da"], "da") - shift[ax], _num(p["a"], "a") - shift[ax]))
            poly = _poly_ccw(poly)
            for sub_poly in ([poly] if _is_convex(poly) else _triangulate(poly)):
                shapes.append((sub_poly, axis, t0, t1, None))
        elif tipo == "cilindro":
            axis = p.get("asse", "z")
            if axis not in AX:
                raise ValueError("'asse' deve essere x, y o z")
            ia, ib = _perp(axis)
            ax = AX[axis]
            ca = _num(p["centro"][0], "centro") - shift[ia]
            cb = _num(p["centro"][1], "centro") - shift[ib]
            r = _num(p["raggio"], "raggio")
            if r <= 0:
                raise ValueError("raggio non valido")
            t0, t1 = sorted((_num(p["da"], "da") - shift[ax], _num(p["a"], "a") - shift[ax]))
            cid += 1
            poly = [
                [ca + r * math.cos(2 * math.pi * k / CYL_FACETS), cb + r * math.sin(2 * math.pi * k / CYL_FACETS)]
                for k in range(CYL_FACETS)
            ]
            shapes.append((poly, axis, t0, t1, cid))
            cyls.append((axis, ca, cb, r, t0, t1))
        else:
            raise ValueError(f"tipo di parte sconosciuto: {tipo}")
        for poly, axis, t0, t1, c in shapes:
            pieces.append((op,) + _piece(poly, axis, t0, t1, c))
    return pieces, cyls


def _contains(P, add, sub):
    """Punti interni al solido: unione delle parti 'add' (interno stretto) meno le 'sub' (chiuse)."""
    ins = np.zeros(len(P), bool)
    for A, d in add:
        ins |= ((P @ A.T - d[None, :]) < -1e-9).all(axis=1)
    for A, d in sub:
        ins &= ~((P @ A.T - d[None, :]) <= 1e-9).all(axis=1)
    return ins


def _hidden(P, dirv, add, sub):
    """True per i punti P nascosti da materiale lungo il raggio verso l'osservatore (direzione dirv)."""
    EPS = 1e-3
    N = len(P)
    B = [np.full(N, EPS)]
    for A, d in add + sub:
        a = A @ dirv
        c = d[None, :] - P @ A.T
        lo = np.full(N, -np.inf)
        hi = np.full(N, np.inf)
        bad = np.zeros(N, bool)
        for k in range(len(a)):
            if abs(a[k]) < 1e-9:
                bad |= c[:, k] < -1e-9
            elif a[k] > 0:
                hi = np.minimum(hi, c[:, k] / a[k])
            else:
                lo = np.maximum(lo, c[:, k] / a[k])
        lo = np.maximum(lo, EPS)
        ok = (~bad) & (hi > lo)
        B.append(np.where(ok, lo, EPS))
        B.append(np.where(ok, np.maximum(hi, EPS), EPS))
    B = np.sort(np.stack(B, axis=1), axis=1)
    mids = (B[:, :-1] + B[:, 1:]) / 2
    width = B[:, 1:] - B[:, :-1]
    pts = P[:, None, :] + mids[:, :, None] * dirv[None, None, :]
    occ = _contains(pts.reshape(-1, 3), add, sub).reshape(mids.shape)
    return (occ & (width > 1e-6)).any(axis=1)


def _hidden4(P, dirv, add, sub, delta=0.02):
    """Nascosto solo se bloccati tutti e 4 i raggi leggermente spostati (evita errori sulle facce parallele alla vista)."""
    k = int(np.argmax(np.abs(dirv)))
    e1, e2 = [np.eye(3)[i] for i in range(3) if i != k]
    res = np.ones(len(P), bool)
    for s1 in (1.0, -1.0):
        for s2 in (1.0, -1.0):
            res &= _hidden(P + delta * (s1 * e1 + s2 * e2), dirv, add, sub)
    return res


def _close(p, q, tol=0.35):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def _sym_axes(vis, hid, ext=3.0):
    """Assi (tratto-punto) per le viste simmetriche che hanno dettagli interni."""
    segs = [("v", a, b) for a, b in vis] + [("h", a, b) for a, b in hid]
    if len(segs) <= 4:
        return []
    xs = [pt[0] for _, a, b in segs for pt in (a, b)]
    ys = [pt[1] for _, a, b in segs for pt in (a, b)]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def symmetric(mirror):
        for k, a, b in segs:
            ma, mb = mirror(a), mirror(b)
            if not any(
                k == k2 and ((_close(ma, a2) and _close(mb, b2)) or (_close(ma, b2) and _close(mb, a2)))
                for k2, a2, b2 in segs
            ):
                return False
        return True

    out = []
    if symmetric(lambda q: (2 * cx - q[0], q[1])):
        out.append(((cx, y0 - ext), (cx, y1 + ext)))
    if symmetric(lambda q: (q[0], 2 * cy - q[1])):
        out.append(((x0 - ext, cy), (x1 + ext, cy)))
    return out


def _snap(t, cand, tol):
    if cand.size:
        k = int(np.argmin(np.abs(cand - t)))
        if abs(cand[k] - t) <= tol:
            return float(cand[k])
    return t


def _merge(segs):
    """Unisce i segmenti collineari che si sovrappongono o si toccano."""
    groups = {}
    for (x1, y1), (x2, y2) in segs:
        dx, dy = x2 - x1, y2 - y1
        if math.hypot(dx, dy) < 1e-6:
            continue
        ang = math.atan2(dy, dx) % math.pi
        if ang > math.pi - 1e-6:
            ang = 0.0
        c, s_ = math.cos(ang), math.sin(ang)
        rho = -s_ * x1 + c * y1
        t1, t2 = c * x1 + s_ * y1, c * x2 + s_ * y2
        groups.setdefault((round(ang, 3), round(rho, 2)), []).append((min(t1, t2), max(t1, t2), ang, rho))
    out = []
    for iv in groups.values():
        iv.sort()
        ang, rho = iv[0][2], iv[0][3]
        c, s_ = math.cos(ang), math.sin(ang)
        cur = [iv[0][0], iv[0][1]]
        merged = []
        for a, b, _, _ in iv[1:]:
            if a <= cur[1] + 0.3:
                cur[1] = max(cur[1], b)
            else:
                merged.append(tuple(cur))
                cur = [a, b]
        merged.append(tuple(cur))
        for a, b in merged:
            out.append(((a * c - rho * s_, a * s_ + rho * c), (b * c - rho * s_, b * s_ + rho * c)))
    return out


VIEWS = {  # direzione verso l'osservatore, assi 3D mostrati (orizzontale, verticale), asse eliminato
    "front": (np.array([0.0, 0.0, -1.0]), (0, 1), 2),
    "top": (np.array([0.0, 1.0, 0.0]), (0, 2), 1),
    "left": (np.array([-1.0, 0.0, 0.0]), (2, 1), 0),
}


def _axis_lines(cyls, dims, vi, ia, ib):
    segs = []
    for axis, ca, cb, r, t0, t1 in cyls:
        ax = AX[axis]
        pa, pb = _perp(axis)
        c = [0.0, 0.0, 0.0]
        c[pa], c[pb] = ca, cb
        if ax == vi:
            for k in (pa, pb):
                p, q = list(c), list(c)
                p[k] -= r + 3
                q[k] += r + 3
                segs.append(((p[ia], p[ib]), (q[ia], q[ib])))
        else:
            p, q = list(c), list(c)
            p[ax] = max(t0, 0.0) - 3
            q[ax] = min(t1, dims[ax]) + 3
            segs.append(((p[ia], p[ib]), (q[ia], q[ib])))
    return segs


@st.cache_data(show_spinner=False)
def compute_solid(json_text):
    """Calcola gli spigoli (in vista e nascosti) delle tre viste di un solido descritto in JSON."""
    data = json.loads(json_text)
    if not isinstance(data, dict):
        raise ValueError("il JSON deve essere un oggetto")
    raw, _ = _parts_to_pieces(data, [0.0, 0.0, 0.0])
    addv = [p[4] for p in raw if p[0] == "add"]
    if not addv:
        raise ValueError("serve almeno una parte con op 'add'")
    allv = np.vstack(addv)
    mn, mx = allv.min(axis=0), allv.max(axis=0)
    dims = tuple(float(v) for v in (mx - mn))
    if min(dims) < 1e-6:
        raise ValueError("il solido ha una dimensione nulla")
    pieces, cyls = _parts_to_pieces(data, list(mn))
    add = [(p[1], p[2]) for p in pieces if p[0] == "add"]
    sub = [(p[1], p[2]) for p in pieces if p[0] == "sub"]

    # piani unici
    planes = {}
    for _op, A, d, tags, _v in pieces:
        for n_, d_, tag in zip(A, d, tags):
            n_ = np.array(n_, float)
            dd = float(d_)
            first = n_[np.nonzero(np.abs(n_) > 1e-9)[0][0]]
            if first < 0:
                n_, dd = -n_, -dd
            key = (tuple(np.round(n_, 5)), round(dd, 3))
            if key not in planes:
                planes[key] = (n_, dd, tag)
    PN = np.array([v[0] for v in planes.values()])
    PD = np.array([v[1] for v in planes.values()])
    PT = [v[2] for v in planes.values()]

    lo = np.full(3, -0.5)
    hi = np.array(dims) + 0.5
    step, eps = 0.25, 0.02
    sa, sb, run_pts, run_curve = [], [], [], []
    n = len(PN)
    for i in range(n):
        for j in range(i + 1, n):
            ni, nj = PN[i], PN[j]
            u = np.cross(ni, nj)
            nu = np.linalg.norm(u)
            if nu < 1e-6:
                continue
            ti, tj = PT[i], PT[j]
            curve = ti is not None or tj is not None
            if ti is not None and tj is not None:
                if ti[0] != tj[0]:
                    continue
                nf, ki, kj = ti[2], ti[1], tj[1]
                if (kj - ki) % nf == 1:
                    vtx = kj
                elif (ki - kj) % nf == 1:
                    vtx = ki
                else:
                    continue
                if vtx % (nf // 4) != 0:
                    continue
            elif abs(float(ni @ nj)) > 0.94:
                continue
            u = u / nu
            try:
                p0 = np.linalg.solve(np.array([ni, nj, u]), np.array([PD[i], PD[j], 0.0]))
            except np.linalg.LinAlgError:
                continue
            t0, t1, ok = -1e9, 1e9, True
            for k in range(3):
                if abs(u[k]) < 1e-9:
                    if p0[k] < lo[k] or p0[k] > hi[k]:
                        ok = False
                        break
                else:
                    a_, b_ = (lo[k] - p0[k]) / u[k], (hi[k] - p0[k]) / u[k]
                    t0, t1 = max(t0, min(a_, b_)), min(t1, max(a_, b_))
            if not ok or t1 - t0 < 1e-3:
                continue
            m = max(1, int(math.ceil((t1 - t0) / step)))
            ts = t0 + np.arange(m + 1) * (t1 - t0) / m
            P = p0[None, :] + ts[:, None] * u[None, :]
            v1 = np.cross(u, ni)
            v1 /= np.linalg.norm(v1)
            v2 = np.cross(u, nj)
            v2 /= np.linalg.norm(v2)
            S = len(P)
            Q = np.vstack([P + eps * (v1 + v2), P + eps * (v1 - v2), P + eps * (-v1 - v2), P + eps * (-v1 + v2)])
            b = _contains(Q, add, sub).reshape(4, S)
            pp, pm, mm, mp = b
            cnt = pp.astype(int) + pm + mm + mp
            diag = (pp & mm & ~pm & ~mp) | (pm & mp & ~pp & ~mm)
            mask = (cnt == 1) | (cnt == 3) | diag
            idx = np.nonzero(mask)[0]
            if idx.size == 0:
                continue
            runs = np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1)
            den = PN @ u
            valid = np.abs(den) > 1e-6
            cand = ((PD - PN @ p0)[valid]) / den[valid]
            half = 0.5 * (ts[1] - ts[0])
            for r in runs:
                ta = _snap(ts[r[0]] - half, cand, 0.2)
                tb = _snap(ts[r[-1]] + half, cand, 0.2)
                if tb - ta < 1e-3:
                    continue
                mm_ = max(1, int(math.ceil((tb - ta) / 0.5)))
                tt = np.linspace(ta, tb, mm_ + 1)
                pts = p0[None, :] + tt[:, None] * u[None, :]
                sa.append(pts[:-1])
                sb.append(pts[1:])
                run_pts.append((pts[0], pts[-1]))
                run_curve.append(curve)
    if not sa:
        raise ValueError("nessuno spigolo trovato: controlla la descrizione del solido")
    SA, SB = np.vstack(sa), np.vstack(sb)
    MID = (SA + SB) / 2

    views = {}
    for name, (dirv, (ia, ib), vi) in VIEWS.items():
        hid = np.concatenate([_hidden4(MID[k:k + 3000], dirv, add, sub) for k in range(0, len(MID), 3000)])
        vis_s, hid_s = [], []
        for a, b2, h in zip(SA, SB, hid):
            seg = ((float(a[ia]), float(a[ib])), (float(b2[ia]), float(b2[ib])))
            (hid_s if h else vis_s).append(seg)
        pts = set()
        for (pa_, pb_), curve in zip(run_pts, run_curve):
            if not curve:
                for q in (pa_, pb_):
                    pts.add((round(float(q[ia]), 2), round(float(q[ib]), 2)))
        for axis_, ca_, cb_, r_, t0_, t1_ in cyls:
            ax_ = AX[axis_]
            pa_, pb_ = _perp(axis_)
            for da_ in (-r_, 0.0, r_):
                for db_ in (-r_, 0.0, r_):
                    for tt_ in (t0_, t1_):
                        q_ = [0.0, 0.0, 0.0]
                        q_[pa_], q_[pb_] = ca_ + da_, cb_ + db_
                        q_[ax_] = min(max(tt_, 0.0), dims[ax_])
                        pts.add((round(q_[ia], 2), round(q_[ib], 2)))
        vm, hm = _merge(vis_s), _merge(hid_s)
        views[name] = {
            "v": vm,
            "h": hm,
            "a": _merge(_axis_lines(cyls, dims, vi, ia, ib) + _sym_axes(vm, hm)),
            "pts": sorted(pts),
        }
    return {
        "dims": dims,
        "views": views,
        "titolo": str(data.get("titolo") or "Esercitazione"),
        "scala": data.get("scala"),
        "descrizione": str(data.get("descrizione") or ""),
    }


# ------------------------------ Disegno SVG ----------------------------------
def build_projection_svg(solid, scale_txt, sheet, title):
    s = scale_factor(scale_txt)
    Wd, Hd, Dd = (v * s for v in solid["dims"])
    M = 10
    GMIN, GCOMF, GMAX = 6.0, 18.0, 27.0
    BAND = (150.0, 26.0)     # cartiglio standard (fascia in basso)
    SIDE = (72.0, 24.0)      # cartiglio compatto, nell'angolo a destra

    def layout(sh, g):
        w_, h_ = SHEETS[sh]
        dw_, dh_ = Wd + Dd + 2 * g, Hd + Dd + 2 * g
        if dh_ + 10 <= h_ - 2 * M - (BAND[1] + 4) and dw_ + 20 <= w_ - 2 * M:
            return "band"
        if dh_ + 4 <= h_ - 2 * M and dw_ + 8 <= w_ - 2 * M - (SIDE[0] + 6):
            return "side"
        return None

    if sheet == "Auto":
        sheet = next((sh for sh in SHEETS if layout(sh, GMIN)), "A2")
    mode = layout(sheet, GCOMF) or layout(sheet, GMIN)
    fits = mode is not None
    mode = mode or "band"
    W, H = SHEETS[sheet]
    tbw, tbh = BAND if mode == "band" else SIDE
    if mode == "band":
        area_w, area_h = W - 2 * M, H - 2 * M - (tbh + 4)
        slack_w, slack_h = 20, 10
    else:
        area_w, area_h = W - 2 * M - (tbw + 6), H - 2 * M
        slack_w, slack_h = 8, 4
    g = min((area_w - slack_w - (Wd + Dd)) / 2, (area_h - slack_h - (Hd + Dd)) / 2)
    g = max(GMIN, min(g, GMAX))
    A_P = B_P = G_P = g

    xmin, xmax = -(G_P + Wd), B_P + Dd
    zmax, zmin = A_P + Hd, -(B_P + Dd)
    dw, dh = xmax - xmin, zmax - zmin
    ox = M + (area_w - dw) / 2 - xmin
    oy = M + (area_h - dh) / 2 + zmax

    def X(x):
        return ox + x

    def Y(z):
        return oy - z

    # trasformazioni dalle coordinate naturali di ogni vista alle coordinate del foglio (y verso l'alto)
    def f_front(p):
        return p[0] * s - (G_P + Wd), A_P + p[1] * s

    def f_top(p):
        return p[0] * s - (G_P + Wd), p[1] * s - (B_P + Dd)

    def f_left(p):
        return B_P + Dd - p[0] * s, A_P + p[1] * s

    maps = {"front": f_front, "top": f_top, "left": f_left}

    parts = []

    def ln(p, q, k):
        parts.append(
            f'<line x1="{X(p[0]):.2f}" y1="{Y(p[1]):.2f}" x2="{X(q[0]):.2f}" y2="{Y(q[1]):.2f}" {LINE_STYLES[k]}/>'
        )

    def txt(x, y, t, size=5, anchor="start", bold=False, max_w=None):
        w = ' font-weight="bold"' if bold else ""
        if max_w and len(t) * size * 0.56 > max_w:
            w += f' textLength="{max_w:.1f}" lengthAdjust="spacingAndGlyphs"'
        parts.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" font-family="Arial, Helvetica, sans-serif" '
            f'fill="#111827" text-anchor="{anchor}"{w}>{escape(t)}</text>'
        )

    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    parts.append(
        f'<rect x="{M}" y="{M}" width="{W - 2 * M}" height="{H - 2 * M}" fill="none" stroke="#111827" stroke-width="0.7"/>'
    )
    parts.append(f'<line x1="{M}" y1="{Y(0):.2f}" x2="{W - M}" y2="{Y(0):.2f}" {LINE_STYLES["t"]}/>')
    parts.append(f'<line x1="{X(0):.2f}" y1="{M}" x2="{X(0):.2f}" y2="{H - M}" {LINE_STYLES["t"]}/>')
    tb = B_P + Dd + 4
    ln((0, 0), (tb, -tb), "t")  # bisettrice

    views = solid["views"]
    # linee di proiezione (sottili), solo negli spazi tra le viste
    xs = sorted({round(f_front(p)[0], 2) for p in views["front"]["pts"]})
    for x in xs:
        ln((x, A_P), (x, -B_P), "t")
    zs = sorted({round(f_front(p)[1], 2) for p in views["front"]["pts"]})
    for z in zs:
        ln((-G_P, z), (B_P, z), "t")
    vs = sorted({round(f_top(p)[1], 2) for p in views["top"]["pts"]})
    for v in vs:
        ln((-G_P, v), (-v, v), "t")
        ln((-v, v), (-v, A_P), "t")

    for name in ("front", "top", "left"):
        f = maps[name]
        for p, q in views[name]["a"]:
            ln(f(p), f(q), "a")
    for name in ("front", "top", "left"):
        f = maps[name]
        for p, q in views[name]["h"]:
            ln(f(p), f(q), "h")
    for name in ("front", "top", "left"):
        f = maps[name]
        for p, q in views[name]["v"]:
            ln(f(p), f(q), "v")

    txt(M + 4, M + 9, "P.V.", 6, bold=True)
    txt(W - M - 4, M + 9, "P.L.", 6, anchor="end", bold=True)
    txt(M + 4, H - M - 5, "P.O.", 6, bold=True)
    txt(W - M - 3, Y(0) - 2, "L.T.", 4, anchor="end")
    txt(M + 3, Y(0) - 2, "x", 4)
    txt(X(0) + 2, H - M - 4, "y", 4)

    x0, y0 = W - M - tbw, H - M - tbh
    half = tbh / 2
    cut = min(46.0, tbw * 0.34)
    small = mode == "side"
    parts.append(
        f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{tbw}" height="{tbh}" fill="#ffffff" stroke="#111827" stroke-width="0.5"/>'
    )
    parts.append(
        f'<line x1="{x0:.2f}" y1="{y0 + half:.2f}" x2="{x0 + tbw:.2f}" y2="{y0 + half:.2f}" stroke="#111827" stroke-width="0.3"/>'
    )
    parts.append(
        f'<line x1="{x0 + cut:.2f}" y1="{y0 + half:.2f}" x2="{x0 + cut:.2f}" y2="{y0 + tbh:.2f}" stroke="#111827" stroke-width="0.3"/>'
    )
    txt(x0 + 2.5, y0 + half - 3.5, title, 4.4 if small else 5.5, bold=True, max_w=tbw - 5 - (0 if small else 28))
    if not small:
        txt(x0 + tbw - 3, y0 + half - 3.5, "CAD Assistant", 3.5, anchor="end")
    txt(x0 + 2.5, y0 + tbh - 3.5, f"Scala {scale_txt}", 4.4 if small else 5)
    txt(
        x0 + cut + 2.5, y0 + tbh - 3.5,
        "Proiezioni ortogonali" + ("" if small else " - metodo europeo"),
        3.4 if small else 4, max_w=tbw - cut - 5,
    )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">'
        + "".join(parts)
        + "</svg>"
    )
    return svg, fits, sheet


# ------------------------------ Gemini (foto -> solido) ----------------------
def get_gemini_key():
    try:
        k = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        k = ""
    return str(k or os.environ.get("GEMINI_API_KEY", "")).strip()


def gemini_read_trace(path, key):
    """Invia la foto a Gemini e restituisce il JSON del solido (testo)."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((1600, 1600))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
    body = {
        "contents": [{
            "parts": [
                {"text": GEMINI_PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode("ascii")}},
            ]
        }],
    }
    models = []
    try:
        custom = str(st.secrets.get("GEMINI_MODEL", "")).strip()
        if custom:
            models.append(custom)
    except Exception:
        pass
    models += [m for m in GEMINI_MODELS if m not in models]

    last = ""
    t_start = time.time()
    for model in models:
        if time.time() - t_start > 100:
            break
        cfg = {"temperature": 0.1, "responseMimeType": "application/json", "maxOutputTokens": 8192}
        if "2.5" in model:
            cfg["thinkingConfig"] = {"thinkingBudget": 0}   # risposta piu' veloce
        body["generationConfig"] = cfg
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = requests.post(
                url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=(10, 50)
            )
        except requests.Timeout:
            last = f"{model}: nessuna risposta entro 50 secondi."
            continue
        except requests.RequestException as e:
            last = f"{model}: connessione non riuscita ({e})"
            continue
        if r.status_code == 200:
            try:
                cand = r.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in cand if not p.get("thought"))
                text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                return json.dumps(json.loads(text), ensure_ascii=False, indent=1)
            except Exception:
                last = f"{model}: risposta non leggibile, riprova."
                continue
        try:
            msg = r.json().get("error", {}).get("message", "")
        except Exception:
            msg = ""
        if r.status_code == 429:
            raise RuntimeError("Quota gratuita di Gemini esaurita: riprova tra qualche minuto o domani.")
        if r.status_code in (401, 403) or "API key" in msg:
            raise RuntimeError("La chiave API non è valida o non è abilitata.")
        last = f"{model}: {msg or 'errore ' + str(r.status_code)}"
    raise RuntimeError(last or "Nessun modello Gemini disponibile.")


def _clean_data(data):
    """Normalizza la risposta (Gemini o esempio): scarta le parti incomplete."""
    if not isinstance(data, dict):
        raise ValueError("risposta non valida")
    parti = []
    for p in data.get("parti") or []:
        if not isinstance(p, dict):
            continue
        op = "sub" if p.get("op") == "sub" else "add"
        try:
            if p.get("tipo") == "box":
                parti.append({
                    "op": op, "tipo": "box",
                    "x": [float(v) for v in p["x"][:2]],
                    "y": [float(v) for v in p["y"][:2]],
                    "z": [float(v) for v in p["z"][:2]],
                })
            elif p.get("tipo") == "prisma":
                axis = p.get("asse") if p.get("asse") in AX else "z"
                parti.append({
                    "op": op, "tipo": "prisma", "asse": axis,
                    "profilo": [[float(a), float(b)] for a, b in p["profilo"]],
                    "da": float(p["da"]), "a": float(p["a"]),
                })
            elif p.get("tipo") == "cilindro":
                axis = p.get("asse") if p.get("asse") in AX else "z"
                parti.append({
                    "op": op, "tipo": "cilindro", "asse": axis,
                    "centro": [float(p["centro"][0]), float(p["centro"][1])],
                    "raggio": float(p["raggio"]),
                    "da": float(p["da"]), "a": float(p["a"]),
                })
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    if not parti:
        raise ValueError("nessuna parte riconosciuta nella risposta")
    return {
        "titolo": str(data.get("titolo") or "Esercitazione"),
        "scala": data.get("scala"),
        "descrizione": str(data.get("descrizione") or ""),
        "parti": parti,
    }


TIPI = {"box": "Parallelepipedo", "prisma": "Prisma", "cilindro": "Cilindro"}
OPS = {"add": "Aggiungi materiale", "sub": "Togli materiale (foro / scasso)"}
PLANE_NAMES = {"z": ("x", "y"), "x": ("y", "z"), "y": ("x", "z")}
NEW_PARTS = {
    "box": {"op": "add", "tipo": "box", "x": [0.0, 20.0], "y": [0.0, 20.0], "z": [0.0, 20.0]},
    "cilindro": {"op": "sub", "tipo": "cilindro", "asse": "z", "centro": [10.0, 10.0], "raggio": 4.0, "da": -1.0, "a": 21.0},
    "prisma": {"op": "add", "tipo": "prisma", "asse": "z", "profilo": [[0.0, 0.0], [20.0, 0.0], [0.0, 20.0]], "da": 0.0, "a": 20.0},
}


def _num_in(label, value, key):
    return st.number_input(label, value=float(value), step=1.0, format="%.2f", key=key)


def solid_editor():
    """Editor semplice delle parti del solido: aggiorna st.session_state.solid."""
    data = st.session_state.solid
    gen = st.session_state.solid_gen
    st.caption(
        "x = larghezza (sinistra → destra) · y = altezza (basso → alto) · z = profondità (dalla faccia frontale al fondo). "
        "Misure in mm."
    )
    new_parts, delete_idx = [], None
    for i, p in enumerate(data["parti"]):
        k = f"g{gen}_{i}"
        tipo = p["tipo"]
        head = f"{i + 1}. {'➕' if p['op'] == 'add' else '➖'} {TIPI[tipo]}"
        with st.expander(head):
            op = st.selectbox(
                "Operazione", list(OPS), index=list(OPS).index(p["op"]), format_func=OPS.get, key=k + "op"
            )
            q = {"op": op, "tipo": tipo}
            if tipo == "box":
                c1, c2 = st.columns(2)
                with c1:
                    x0 = _num_in("x da (sinistra)", p["x"][0], k + "x0")
                    y0 = _num_in("y da (basso)", p["y"][0], k + "y0")
                    z0 = _num_in("z da (fronte)", p["z"][0], k + "z0")
                with c2:
                    x1 = _num_in("x a (destra)", p["x"][1], k + "x1")
                    y1 = _num_in("y a (alto)", p["y"][1], k + "y1")
                    z1 = _num_in("z a (fondo)", p["z"][1], k + "z1")
                q.update(x=[x0, x1], y=[y0, y1], z=[z0, z1])
            else:
                axis = st.selectbox(
                    "Asse", ["x", "y", "z"], index=["x", "y", "z"].index(p["asse"]), key=k + "as"
                )
                na, nb = PLANE_NAMES[axis]
                c1, c2 = st.columns(2)
                with c1:
                    t0 = _num_in(f"{axis} da", p["da"], k + "da")
                with c2:
                    t1 = _num_in(f"{axis} a", p["a"], k + "a")
                q.update(asse=axis, da=t0, a=t1)
                if tipo == "cilindro":
                    c3, c4, c5 = st.columns(3)
                    with c3:
                        ca = _num_in(f"centro {na}", p["centro"][0], k + "ca")
                    with c4:
                        cb = _num_in(f"centro {nb}", p["centro"][1], k + "cb")
                    with c5:
                        r = _num_in("raggio", p["raggio"], k + "r")
                    q.update(centro=[ca, cb], raggio=r)
                else:
                    st.caption(f"Punti del profilo ({na}, {nb}) — puoi aggiungere o togliere righe.")
                    df = pd.DataFrame(p["profilo"], columns=[na, nb])
                    ed = st.data_editor(
                        df, num_rows="dynamic", hide_index=True, key=f"{k}prof{axis}"
                    )
                    q["profilo"] = [[float(a), float(b)] for a, b in ed.dropna().values.tolist()]
            if st.button("🗑 Elimina questa parte", key=k + "del"):
                delete_idx = i
        new_parts.append(q)
    st.session_state.solid["parti"] = new_parts

    st.markdown("**Aggiungi una parte**")
    b1, b2, b3 = st.columns(3)
    with b1:
        add_box = st.button("➕ Blocco", key=f"g{gen}_addbox")
    with b2:
        add_cyl = st.button("➕ Cilindro", key=f"g{gen}_addcyl")
    with b3:
        add_pri = st.button("➕ Prisma", key=f"g{gen}_addpri")
    changed = False
    if delete_idx is not None:
        st.session_state.solid["parti"].pop(delete_idx)
        changed = True
    for clicked, name in ((add_box, "box"), (add_cyl, "cilindro"), (add_pri, "prisma")):
        if clicked:
            st.session_state.solid["parti"].append(json.loads(json.dumps(NEW_PARTS[name])))
            changed = True
    if changed:
        st.session_state.solid_gen += 1
        st.rerun()


def drawing_tab():
    scale = st.session_state.scale
    st.session_state.setdefault("solid", None)
    st.session_state.setdefault("solid_gen", 0)
    st.markdown("#### Disegno completo delle tre proiezioni")
    path = st.session_state.trace_path
    has_trace = bool(path and Path(path).exists())

    c1, c2 = st.columns(2)
    with c1:
        read_clicked = st.button("🔍 Riconosci dalla foto", disabled=not has_trace)
    with c2:
        ex_clicked = st.button("📘 Esempio: Esercitazione 14")

    if ex_clicked:
        st.session_state.solid = _clean_data(json.loads(example_14_json()))
        st.session_state.solid_gen += 1
    if read_clicked:
        key = get_gemini_key()
        if not key:
            st.error("Chiave Gemini non trovata nei Secrets dell'app.")
        else:
            with st.spinner("Sto leggendo la traccia (anche 1 minuto)..."):
                try:
                    st.session_state.solid = _clean_data(json.loads(gemini_read_trace(path, key)))
                    st.session_state.solid_gen += 1
                except Exception as e:
                    st.error(str(e))

    if has_trace:
        with st.expander("Vedi la traccia caricata"):
            st.image(path)
    if not st.session_state.solid:
        st.info("Carica la traccia e tocca «Riconosci dalla foto», oppure prova l'esempio.")
        return

    with st.expander("✏️ Correggi le misure"):
        solid_editor()
    data = st.session_state.solid
    try:
        with st.spinner("Calcolo le proiezioni..."):
            solid = compute_solid(json.dumps(data, sort_keys=True, ensure_ascii=False))
    except Exception as e:
        st.error(f"Non riesco a disegnare questo solido: {e}")
        return

    W_, H_, D_ = solid["dims"]
    if data["descrizione"]:
        st.caption(data["descrizione"])
    st.caption(f"Ingombro: {W_:.1f} × {H_:.1f} × {D_:.1f} mm (larghezza × altezza × profondità).")
    if data["scala"] and str(data["scala"]) != scale:
        st.caption(f"L'esercizio indica la scala {data['scala']}, ma hai selezionato {scale}.")
    c3, c4 = st.columns(2)
    with c3:
        sheet = st.selectbox("Formato foglio", ["Auto"] + list(SHEETS), key="sheet_fmt")
    with c4:
        title = st.text_input("Titolo nel cartiglio", value=data["titolo"])

    svg, fits, used = build_projection_svg(solid, scale, sheet, title)
    if not fits:
        st.warning(
            f"Alla scala {scale} il solido è troppo grande per il formato {used}, anche con il cartiglio compatto: "
            "scegli un formato più grande (A2) oppure una scala più piccola."
        )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    st.markdown(
        '<div style="background:#fff;border-radius:12px;padding:6px;">'
        f'<img src="data:image/svg+xml;base64,{b64}" style="width:100%;height:auto;display:block;"/></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Linea continua: spigoli in vista · tratteggiata: parti nascoste · tratto-punto: assi · "
        f"linee sottili: proiezione. Stampato al 100% su {used} le misure sono quelle reali (scala {scale})."
    )
    st.download_button(
        "⬇ Scarica il disegno (SVG)",
        data=svg.encode("utf-8"),
        file_name=f"proiezioni_{scale.replace(':', 'a')}.svg",
        mime="image/svg+xml",
    )


def assistant_page():
    st.markdown(
        """
        <div class="hero">
            <h1>📐 CAD Assistant — Proiezioni Ortogonali</h1>
            <p>Sistema educativo di disegno tecnico: carica la foto della traccia,
            scegli la scala di rappresentazione e segui la guida interattiva
            passo-passo per costruire correttamente le proiezioni ortogonali
            (vista frontale, pianta e vista laterale) con il metodo europeo.</p>
            <span class="author">Creato da: ENRICO BOTTONE</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Caricamento traccia e scala -------------------------------------
    col_up, col_scale = st.columns([2, 1])
    with col_up:
        st.markdown("#### 🖼️ Traccia dell'esercizio")
        gen = st.session_state.widget_gen
        mode = st.radio(
            "Come vuoi caricare la traccia?",
            ["📁 Galleria / file", "📷 Fotocamera integrata"],
            horizontal=True,
            key="trace_source",
        )
        if mode.startswith("📁"):
            source = st.file_uploader(
                "Carica la foto della traccia (jpg, png, webp)",
                type=ALLOWED_EXT,
                key=f"trace_uploader_{gen}",
            )
            st.caption(
                "Consiglio da telefono: scatta prima la foto con l'app Fotocamera, "
                "poi sceglila dalla galleria. Apri l'app nel browser (Chrome/Safari), "
                "non dentro un'altra app."
            )
        else:
            source = st.camera_input(
                "Scatta la foto della traccia",
                key=f"trace_camera_{gen}",
            )
        if source is not None:
            sig = f"{source.name}-{source.size}"
            if sig != st.session_state.trace_sig:
                save_upload(source)
        if st.session_state.trace_path:
            if st.button("Rimuovi traccia"):
                remove_trace()
                st.rerun()

    with col_scale:
        st.markdown("#### 📏 Scala di rappresentazione")
        st.selectbox(
            "Seleziona la scala",
            SCALES,
            key="scale",
        )
        f = scale_factor(st.session_state.scale)
        st.markdown(
            f"""
            <div class="card">
                Fattore di scala: <b>{f:g}</b><br>
                <small>misura disegno = misura reale × {f:g}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )
        real = st.number_input(
            "Misura reale (mm)", min_value=0.0, value=100.0, step=1.0
        )
        st.markdown(
            f"Da tracciare sul foglio: **{real * f:g} mm**"
        )

    st.divider()

    tab_draw, tab_guide = st.tabs(["📐 Disegno completo", "🧭 Guida passo-passo"])

    with tab_draw:
        drawing_tab()

    with tab_guide:
        st.markdown("### 🧭 Guida passo-passo")

        steps = build_steps(st.session_state.scale)
        total = len(steps)
        # Protezione se il numero di passi cambiasse
        st.session_state.current_step = max(0, min(st.session_state.current_step, total - 1))
        idx = st.session_state.current_step
        step = steps[idx]

        left, right = st.columns([1, 1])

        with left:
            st.markdown("#### Riferimento: traccia caricata")
            path = st.session_state.trace_path
            if path and Path(path).exists():
                st.image(path, caption="Traccia di riferimento")
            else:
                st.info("Carica la foto della traccia per vederla qui come riferimento costante.")

        with right:
            st.progress((idx + 1) / total, text=f"Passo {idx + 1} di {total}")
            items_html = "".join(f"<li>{it}</li>" for it in step["items"])
            st.markdown(
                f"""
                <div class="card">
                    <span class="step-badge">PASSO {idx + 1} / {total}</span>
                    <h3>{step['title']}</h3>
                    <ul>{items_html}</ul>
                    <div class="tip">💡 {step['tip']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            b1, b2, _ = st.columns([1, 1, 2])
            with b1:
                st.button(
                    "⬅ Indietro",
                    key="btn_prev",
                    on_click=go_prev,
                    disabled=(idx == 0),
                )
            with b2:
                st.button(
                    "Avanti ➡",
                    key="btn_next",
                    on_click=go_next,
                    args=(total,),
                    disabled=(idx == total - 1),
                )
            if idx == total - 1:
                st.success("Hai completato tutti i passaggi. Ottimo lavoro!")

    save_session_state()


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main():
    init_db()
    init_state()
    inject_css()

    restore_login()
    user = st.session_state.user
    if not user:
        login_page()
        return

    with st.sidebar:
        st.markdown("## 📐 CAD Assistant")
        st.markdown(f"**Utente:** {user['username']}")
        st.caption(f"Ruolo: {user['role']}")
        st.divider()

        pages = ["Assistente CAD"]
        if user["role"] == ROLE_DEV:
            pages.append("Gestione Utenti")
        page = st.radio("Navigazione", pages, label_visibility="collapsed")

        st.divider()
        if st.button("Esci"):
            logout()
            st.rerun()
        st.caption("Creato da: ENRICO BOTTONE")

    if page == "Gestione Utenti" and user["role"] == ROLE_DEV:
        user_management_page()
    else:
        assistant_page()


main()
