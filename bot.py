import os
import sqlite3
import logging
from datetime import datetime, timedelta
import pytz
import asyncio
import aiohttp
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)

from dotenv import load_dotenv
load_dotenv()

# ========== CONFIG ==========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID", 0))
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_TOKEN = os.getenv("EVOLUTION_API_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== TIMEZONE ==========
TZ = pytz.timezone('America/Sao_Paulo')


def agora():
    return datetime.now(TZ)


# ========== DATABASE ==========
class DB:
    def __init__(self):
        self.conn = sqlite3.connect("clientes.db", check_same_thread=False)
        self.criar_tabelas()

    def criar_tabelas(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT, telefone TEXT, pacote TEXT,
            valor REAL, vencimento TEXT
        )""")
        self.conn.commit()

    def add_cliente(self, nome, telefone, pacote, valor, vencimento):
        self.conn.execute("INSERT INTO clientes (nome, telefone, pacote, valor, vencimento) VALUES (?, ?, ?, ?, ?)",
                          (nome, telefone, pacote, valor, vencimento))
        self.conn.commit()

    def listar(self):
        c = self.conn.cursor()
        c.execute("SELECT id, nome, telefone, pacote, valor, vencimento FROM clientes")
        return c.fetchall()


db = DB()

# ========== WHATSAPP ==========
async def enviar_whatsapp(numero: str, mensagem: str) -> bool:
    payload = {
        "number": numero,
        "message": mensagem
    }
    headers = {
        "Authorization": f"Bearer {EVOLUTION_API_TOKEN}",
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(EVOLUTION_API_URL, headers=headers, json=payload) as resp:
            return resp.status == 200

# ========== TELEGRAM BOT ==========

# Conversação de cadastro
NOME, TELEFONE, PACOTE, VALOR, VENCIMENTO = range(5)


def teclado_cancelar():
    return ReplyKeyboardMarkup([["❌ Cancelar"]], resize_keyboard=True, one_time_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Acesso negado.")
        return
    await update.message.reply_text("👋 Bot iniciado. Use /add para adicionar cliente ou /listar para listar.")


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📛 Nome do cliente:", reply_markup=teclado_cancelar())
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
    await update.message.reply_text("💰 Valor (ex: 45.00):")
    return VALOR


async def get_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["valor"] = float(update.message.text.replace(",", "."))
    await update.message.reply_text("📅 Vencimento (AAAA-MM-DD):")
    return VENCIMENTO


async def get_vencimento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.text
    context.user_data["vencimento"] = data
    dados = context.user_data

    db.add_cliente(dados["nome"], dados["telefone"], dados["pacote"], dados["valor"], dados["vencimento"])
    await update.message.reply_text("✅ Cliente salvo com sucesso!")
    return ConversationHandler.END


async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clientes = db.listar()
    if not clientes:
        await update.message.reply_text("📭 Nenhum cliente cadastrado.")
        return

    mensagens = []
    for c in clientes:
        msg = (f"👤 {c[1]}\n📱 {c[2]}\n📦 {c[3]}\n💰 R$ {c[4]:.2f}\n📅 Venc: {c[5]}")
        mensagens.append(msg)

    for m in mensagens:
        await update.message.reply_text(m)


async def enviar_todos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clientes = db.listar()
    enviados = 0

    for c in clientes:
        msg = f"Olá {c[1]}, seu plano '{c[3]}' vence em {c[5]}. Valor: R$ {c[4]:.2f}."
        sucesso = await enviar_whatsapp(c[2], msg)
        if sucesso:
            enviados += 1

    await update.message.reply_text(f"📤 Mensagens enviadas para {enviados} clientes via WhatsApp.")


# ========== SCHEDULER ==========
async def agendar_envio():
    while True:
        agora_hora = agora().strftime('%H:%M')
        if agora_hora == "09:00":  # Exemplo: 9h
            fake_update = type("FakeUpdate", (), {"message": type("FakeMessage", (), {"reply_text": print})()})()
            await enviar_todos(fake_update, None)
        await asyncio.sleep(60)


# ========== MAIN ==========
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
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
    app.add_handler(conv_handler)

    # Roda bot e agendador juntos
    async def run():
        await asyncio.gather(app.run_polling(), agendar_envio())

    asyncio.run(run())


if __name__ == "__main__":
    main()
