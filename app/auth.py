"""Senhas (PBKDF2) e tokens de sessão assinados (HMAC). Só biblioteca padrão."""
import base64, hashlib, hmac, json, os, secrets, time

ITER = 200_000


def hash_senha(s):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", s.encode(), bytes.fromhex(salt), ITER).hex()
    return f"pbkdf2${ITER}${salt}${h}"


def confere(s, guardado):
    try:
        _, it, salt, h = guardado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", s.encode(), bytes.fromhex(salt), int(it)).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


def _chave():
    k = os.getenv("SECRET_KEY")
    if not k:  # sem SECRET_KEY: deriva do segredo do banco (estável entre instâncias serverless)
        k = hashlib.sha256(("farol:" + (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "local")).encode()).hexdigest()
    return k.encode()


def _b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def emitir(uid, horas=12):
    corpo = _b64(json.dumps({"u": uid, "e": int(time.time()) + horas * 3600}).encode())
    return corpo + "." + _b64(hmac.new(_chave(), corpo.encode(), "sha256").digest())


def ler(token):
    try:
        corpo, sig = token.split(".")
        if not hmac.compare_digest(sig, _b64(hmac.new(_chave(), corpo.encode(), "sha256").digest())):
            return None
        d = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
        return d["u"] if d["e"] > time.time() else None
    except Exception:
        return None
