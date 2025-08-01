import os
import sqlite3
import logging
from datetime import datetime
import pytz
import aiohttp
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters, JobQueue
)
from dotenv import load_dotenv

# ======= CONFIGURAÇÕES =======
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_TOKEN = os.getenv("EVOLUTION_API_TOKEN")

# ======= LOGGING =======
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======= TIMEZONE BR =======
TZ = pytz.timezone('America/Sao_Paulo')


def agora():
    return datetime.now(TZ)


# ======= BANCO DE DADOS =======
class DB:
    def __init__(self):
        self.conn = sqlite3.connect("clientes.db", check_same_thread=False)
        self.criar()

    def criar(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT, telefone TEXT, pacote TEXT,
                valor REAL, vencimento TEXT
            )
        """)
        self.conn.commit()

    def add(self, nome, telefone, pacote, valor, vencimento):
        self.conn.execute(
            "INSERT INTO clientes (nome, telefone, pacote, valor, vencimento) VALUES (?, ?, ?, ?, ?)",
            (nome, telefone, pacote, valor, vencimento)
        )
        self.conn.commit()

    def listar(self):
        return self.conn.execute("SELECT * FROM clientes").fetchall()


db = DB()

# ======= EVOLUTION API WHATSAPP =======
async def enviar_whatsapp(numero: str, mensagem: str) -> bool:
    headers = {
        "Authorization": f"Bearer {EVOLUTION_API_TOKEN}",
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(EVOLUTION_API_URL, json={
            "number": numero,
            "message": mensagem
        }, headers=headers) as resp:
            return resp.status == 200


# ======= CONVERSAÇÃO DO BOT =======
NOME, TELEFONE, PACOTE, VALOR, VENCIMENTO = range(5)


def teclado_cancelar():
    return ReplyKeyboardMarkup([["❌ Cancelar"]], resize_keyboard=True, one_time_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Acesso negado.")
        return
    await update.message.reply_text("👋 Bot iniciado.\nComandos:\n/add\n/listar\n/enviar")


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Nome do cliente:", reply_markup=teclado_cancelar())
    return NOME


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cadastro cancelado.")
    return ConversationHandler.END


async def get_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome"] = update.message.text
    await update.message.reply_text("📱 Telefone:")
    return TELEFONE


async def get_telefone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["telefone"] = update.message.text
    await update.message.reply_text("📦 Pacote:")
    return PACOTE


async def get_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pacote"] = update.message.text
    await update.message.reply_text("💰 Valor (ex: 49.90):")
    return VALOR


async def get_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["valor"] = float(update.message.text.replace(",", "."))
    await update.message.reply_text("📅 Vencimento (AAAA-MM-DD):")
    return VENCIMENTO


async def get_vencimento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["vencimento"] = update.message.text
    d = context.user_data
    db.add(d["nome"], d["telefone"], d["pacote"], d["valor"], d["vencimento"])
    await update.message.reply_text("✅ Cliente cadastrado com sucesso!")
    return ConversationHandler.END


async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clientes = db.listar()
    if not clientes:
        await update.message.reply_text("📭 Nenhum cliente cadastrado.")
        return

    for c in clientes:
        await update.message.reply_text(
            f"👤 {c[1]}\n📱 {c[2]}\n📦 {c[3]}\n💰 R$ {c[4]:.2f}\n📅 {c[5]}"
        )


async def enviar_todos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clientes = db.listar()
    enviados = 0
    for c in clientes:
        msg = f"🔔 Olá {c[1]}, seu plano '{c[3]}' vence em {c[5]}.\n💰 Valor: R$ {c[4]:.2f}"
        if await enviar_whatsapp(c[2], msg):
            enviados += 1

    await update.message.reply_text(f"✅ Mensagens enviadas para {enviados} clientes.")


# ======= AGENDAMENTO PELO JOBQUEUE =======
async def agendar_envio(context: ContextTypes.DEFAULT_TYPE):
    hora = agora().strftime("%H:%M")
    if hora == "09:00":
        clientes = db.listar()
        for c in clientes:
            msg = f"📅 Bom dia, {c[1]}!\nSeu plano '{c[3]}' vence em {c[5]}.\n💰 Valor: R$ {c[4]:.2f}"
            await enviar_whatsapp(c[2], msg)
        print(f"🔔 Envio automático executado às {hora}")


# ======= MAIN =======
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("add", add)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nome)],
            TELEFONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_telefone)],
            PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pacote)],
            VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_valor)],
            VENCIMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vencimento)],
        },
        fallbacks=[MessageHandler(filters.Regex("^(❌ Cancelar)$"), cancelar)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("enviar", enviar_todos))
    app.add_handler(conv)

    # ✅ Agendador com intervalo de 60s
    app.job_queue.run_repeating(agendar_envio, interval=60, first=5)

    app.run_polling()


if __name__ == "__main__":
    main()
