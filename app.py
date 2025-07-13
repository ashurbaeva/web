from flask import (
    Flask, render_template, request, send_from_directory,
    redirect, url_for, session
)
from werkzeug.utils import secure_filename
from translatepy import Translator
from PyPDF2 import PdfReader
from docx import Document
from functools import wraps
import os, logging

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key")  # ключ для сессий

# ──────────────────────────── пути к каталогам ──────────────────────────── #
BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, "static", "downloads")
ALLOWED_EXT = {"txt", "pdf", "docx"}

for folder in (UPLOAD_FOLDER, DOWNLOAD_FOLDER):
    os.makedirs(folder, exist_ok=True)

# ────────────────────────────── учётные данные ───────────────────────────── #
# админ читается из env (как и раньше)
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "password")

# тестовые аккаунты для проверки логина
TEST_ACCOUNTS = {
    "user1@example.com": "1",
    "user2@example.com": "2",
    "user3@example.com": "3",
    "user4@example.com": "4",
    "user5@example.com": "5",
}

# итоговый словарь логин→пароль (ключи уникальны)
USERS = {ADMIN_USER: ADMIN_PASS, **TEST_ACCOUNTS}

translator = Translator()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ────────────────────────────── вспомогательные ──────────────────────────── #

def allowed_file(fname: str) -> bool:
    """Проверка расширения."""
    return "." in fname and fname.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def extract_text(path: str, ext: str) -> str | None:
    """Извлекает текст из файла в зависимости от типа."""
    if ext == "txt":
        with open(path, encoding="utf-8") as f:
            return f.read()
    if ext == "pdf":
        with open(path, "rb") as f:
            return "".join(p.extract_text() or "" for p in PdfReader(f).pages)
    if ext == "docx":
        return "\n".join(p.text for p in Document(path).paragraphs if p.text)
    return None

# ────────────────────────────────── роуты ────────────────────────────────── #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if USERS.get(username) == password:
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("translator"))

        return render_template("login.html", error="Неверные данные")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/cabinet")  # кабинет после авторизации
@login_required
def translator():
    return render_template("translator.html", username=session.get("username"))


@app.route("/translate", methods=["POST"])
@login_required
def translate():
    if "file" not in request.files or request.files["file"].filename == "":
        return render_template(
            "translator.html", error="Файл не выбран", username=session.get("username")
        )

    file = request.files["file"]
    if not allowed_file(file.filename):
        return render_template(
            "translator.html",
            error="Допустимы только TXT, PDF, DOCX",
            username=session.get("username"),
        )

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        text = extract_text(filepath, filename.rsplit(".", 1)[1].lower())
        if not text:
            return render_template(
                "translator.html",
                error="Не удалось прочитать файл",
                username=session.get("username"),
            )

        lang = request.form.get("language", "en")
        trans = translator.translate(text, destination_language=lang).result

        out_name = f"translated_{filename}.txt"
        out_path = os.path.join(DOWNLOAD_FOLDER, out_name)
        with open(out_path, "w", encoding="utf-8") as out:
            out.write(trans)

        return render_template(
            "translator.html",
            success="Готово! Скачайте результат ниже:",
            download=url_for("download", filename=out_name),
            username=session.get("username"),
        )
    except Exception:
        logger.exception("Ошибка перевода")
        return render_template(
            "translator.html",
            error="Ошибка обработки файла",
            username=session.get("username"),
        )


@app.route("/download/<filename>")
@login_required
def download(filename: str):
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
