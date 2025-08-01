import os
import sqlite3
import logging
from datetime import datetime
import pytz
import aiohttp
import csv
from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)
from dotenv import load_dotenv

# ========== CONFIG ==========
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_TOKEN = os.getenv("EVOLUTION_API_TOKEN")
ALLOWED_USERS = set(map(int, os.getenv("ALLOWED_USERS", "").split(",")))
TZ = pytz.timezone("America/Sao_Paulo")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== DB ==========
class DB:
    def __init__(self):
        self.conn = sqlite3.connect("clientes.db", check_same_thread=False)
        self.create()

    def create(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT,
                telefone TEXT,
                pacote TEXT,
                valor REAL,
                vencimento TEXT
            )
        """)
        self.conn.commit()

    def add(self, nome, telefone, pacote, valor, vencimento):
        self.conn.execute("INSERT INTO clientes (nome, telefone, pacote, valor, vencimento) VALUES (?, ?, ?, ?, ?)",
                          (nome, telefone, pacote, valor, vencimento))
        self.conn.commit()

    def listar(self):
        return self.conn.execute("SELECT * FROM clientes").fetchall()

db = DB()

# ========== CONSTANTES ==========
NOME, TELEFONE, PACOTE, VALOR, VENCIMENTO = range(5)

TECLADO = ReplyKeyboardMarkup([
    ["📋 Listar clientes", "➕ Adicionar cliente"],
    ["📤 Enviar mensagens", "📁 Exportar CSV"],
    ["⚙️ Configurações"]
], resize_keyboard=True)

CANCELAR = ReplyKeyboardMarkup([["❌ Cancelar"]], resize_keyboard=True, one_time_keyboard=True)

def agora():
    return datetime.now(TZ)

def is_admin(user_id):
    return user_id in ALLOWED_USERS

# ========== WHATSAPP ==========
async def enviar_whatsapp(numero, mensagem):
    async with aiohttp.ClientSession() as session:
        async with session.post(EVOLUTION_API_URL, headers={
            "Authorization": f"Bearer {EVOLUTION_API_TOKEN}",
            "Content-Type": "application/json"
        }, json={"number": numero, "message": mensagem}) as resp:
            return resp.status == 200

# ========== COMANDOS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Acesso negado.")
        return
    await update.message.reply_text("✅ Bot iniciado com sucesso!", reply_markup=TECLADO)

async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    clientes = db.listar()
    if not clientes:
        await update.message.reply_text("📭 Nenhum cliente encontrado.")
        return
    for c in clientes:
        await update.message.reply_text(
            f"👤 {c[1]}\n📱 {c[2]}\n📦 {c[3]}\n💰 R$ {c[4]:.2f}\n📅 {c[5]}"
        )

async def enviar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    enviados = 0
    for c in db.listar():
        msg = f"🔔 Olá {c[1]}, seu plano '{c[3]}' vence em {c[5]}. Valor: R$ {c[4]:.2f}"
        if await enviar_whatsapp(c[2], msg): enviados += 1
    await update.message.reply_text(f"✅ Mensagens enviadas para {enviados} clientes.")

async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    clientes = db.listar()
    with open("clientes_export.csv", "w", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Nome", "Telefone", "Pacote", "Valor", "Vencimento"])
        writer.writerows(clientes)
    await update.message.reply_document(InputFile("clientes_export.csv"))

async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ Configurações futuras: backups, alertas, relatórios...")

# ========== CADASTRO ==========
async def iniciar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Nome do cliente:", reply_markup=CANCELAR)
    return NOME

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cadastro cancelado.", reply_markup=TECLADO)
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
    await update.message.reply_text("💰 Valor:")
    return VALOR

async def get_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["valor"] = float(update.message.text.replace(",", "."))
    await update.message.reply_text("📅 Vencimento (AAAA-MM-DD):")
    return VENCIMENTO

async def get_vencimento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data
    db.add(d["nome"], d["telefone"], d["pacote"], d["valor"], update.message.text)
    await update.message.reply_text("✅ Cliente cadastrado com sucesso!", reply_markup=TECLADO)
    return ConversationHandler.END

# ========== AGENDAMENTO ==========
async def agendar(context: ContextTypes.DEFAULT_TYPE):
    if agora().strftime("%H:%M") == "09:00":
        for c in db.listar():
            msg = f"📅 Bom dia, {c[1]}!\nSeu plano '{c[3]}' vence em {c[5]}.\n💰 Valor: R$ {c[4]:.2f}"
            await enviar_whatsapp(c[2], msg)
        print("✅ Envio automático realizado às 09:00")

# ========== MAIN ==========
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    cadastro = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Adicionar cliente$"), iniciar_cadastro)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nome)],
            TELEFONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_telefone)],
            PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pacote)],
            VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_valor)],
            VENCIMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vencimento)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(cadastro)
    app.add_handler(MessageHandler(filters.Regex("^📋 Listar clientes$"), listar))
    app.add_handler(MessageHandler(filters.Regex("^📤 Enviar mensagens$"), enviar))
    app.add_handler(MessageHandler(filters.Regex("^📁 Exportar CSV$"), exportar))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Configurações$"), config))

    app.job_queue.run_repeating(agendar, interval=60, first=5)
    app.run_polling()

if __name__ == "__main__":
    main()
