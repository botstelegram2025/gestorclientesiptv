import os
import sqlite3
import logging
import csv
from datetime import datetime, timedelta
import pytz
import aiohttp
from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)
from dotenv import load_dotenv

# ===== CONFIGURAÇÃO =====
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_TOKEN = os.getenv("EVOLUTION_API_TOKEN")
ALLOWED_USERS = set(map(int, filter(None, os.getenv("ALLOWED_USERS", "").split(","))))
TZ = pytz.timezone("America/Sao_Paulo")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== BANCO DE DADOS =====
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

# ===== CONSTANTES =====
NOME, TELEFONE, PACOTE, VALOR, VALOR_CUSTOM, VENCIMENTO, VENCIMENTO_PERSONALIZADO = range(7)

TECLADO = ReplyKeyboardMarkup([
    ["📋 Listar clientes", "➕ Adicionar cliente"],
    ["📤 Enviar mensagens", "📁 Exportar CSV"],
    ["⚙️ Configurações"]
], resize_keyboard=True)

CANCELAR = ReplyKeyboardMarkup([["❌ Cancelar"]], resize_keyboard=True, one_time_keyboard=True)

PACOTES = ReplyKeyboardMarkup([
    ["📦 1 mês", "📦 3 meses"],
    ["📦 6 meses", "📦 12 meses"],
    ["❌ Cancelar"]
], resize_keyboard=True, one_time_keyboard=True)

VALORES = ReplyKeyboardMarkup([
    ["💰 30", "💰 35", "💰 40"],
    ["💰 45", "💰 50", "💰 60"],
    ["💰 70", "💰 90", "💰 135"],
    ["💸 Valor personalizado", "❌ Cancelar"]
], resize_keyboard=True, one_time_keyboard=True)

VENCIMENTO_OPCOES = ReplyKeyboardMarkup([
    ["📆 Usar sugestão automática", "📆 Data personalizada"],
    ["❌ Cancelar"]
], resize_keyboard=True, one_time_keyboard=True)

# ===== UTIL =====
def agora():
    return datetime.now(TZ)

def is_admin(user_id):
    return user_id in ALLOWED_USERS

def calcular_vencimento(pacote_meses: int) -> str:
    dias = 30 * pacote_meses
    data = agora() + timedelta(days=dias)
    return data.strftime("%Y-%m-%d"), data.strftime("%d/%m/%Y")

async def enviar_whatsapp(numero, mensagem):
    async with aiohttp.ClientSession() as session:
        async with session.post(EVOLUTION_API_URL, headers={
            "Authorization": f"Bearer {EVOLUTION_API_TOKEN}",
            "Content-Type": "application/json"
        }, json={"number": numero, "message": mensagem}) as resp:
            return resp.status == 200

# ===== COMANDOS =====
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
        venc_br = datetime.strptime(c[5], "%Y-%m-%d").strftime("%d/%m/%Y")
        await update.message.reply_text(
            f"👤 {c[1]}\n📱 {c[2]}\n📦 {c[3]}\n💰 R$ {c[4]:.2f}\n📅 {venc_br}"
        )

async def enviar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    enviados = 0
    for c in db.listar():
        venc_br = datetime.strptime(c[5], "%Y-%m-%d").strftime("%d/%m/%Y")
        msg = f"🔔 Olá {c[1]}, seu plano '{c[3]}' vence em {venc_br}. Valor: R$ {c[4]:.2f}"
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

# ===== CADASTRO =====
async def iniciar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Nome do cliente:", reply_markup=CANCELAR)
    return NOME

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cadastro cancelado.", reply_markup=TECLADO)
    return ConversationHandler.END

async def get_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome"] = update.message.text
    await update.message.reply_text("📱 Telefone (com DDD):")
    return TELEFONE

async def get_telefone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["telefone"] = update.message.text
    await update.message.reply_text("📦 Escolha o pacote:", reply_markup=PACOTES)
    return PACOTE

async def get_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pacote = update.message.text.replace("📦", "").replace("meses", "").replace("mês", "").strip()
    context.user_data["pacote"] = f"{pacote} meses" if pacote != "1" else "1 mês"
    context.user_data["meses"] = int(pacote)
    await update.message.reply_text("💰 Escolha o valor:", reply_markup=VALORES)
    return VALOR

async def get_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    valor = update.message.text.replace("💰", "").strip()
    if "personalizado" in valor.lower():
        await update.message.reply_text("💸 Digite o valor personalizado:")
        return VALOR_CUSTOM
    context.user_data["valor"] = float(valor)
    return await sugerir_vencimento(update, context)

async def get_valor_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["valor"] = float(update.message.text.replace(",", "."))
    return await sugerir_vencimento(update, context)

async def sugerir_vencimento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meses = context.user_data["meses"]
    _, venc_br = calcular_vencimento(meses)
    context.user_data["vencimento_sugerido"] = venc_br
    await update.message.reply_text(
        f"📅 Sugestão de vencimento: *{venc_br}*\nDeseja usar essa data ou personalizar?",
        reply_markup=VENCIMENTO_OPCOES,
        parse_mode="Markdown"
    )
    return VENCIMENTO

async def get_vencimento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    escolha = update.message.text
    if "personalizada" in escolha.lower():
        await update.message.reply_text("📅 Digite a nova data no formato DD/MM/AAAA:")
        return VENCIMENTO_PERSONALIZADO
    else:
        data_sql = datetime.strptime(context.user_data["vencimento_sugerido"], "%d/%m/%Y").strftime("%Y-%m-%d")
        d = context.user_data
        db.add(d["nome"], d["telefone"], d["pacote"], d["valor"], data_sql)
        await update.message.reply_text("✅ Cliente cadastrado com sucesso!", reply_markup=TECLADO)
        return ConversationHandler.END

async def get_vencimento_personalizado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data_br = update.message.text.strip()
        data_obj = datetime.strptime(data_br, "%d/%m/%Y")
        data_sql = data_obj.strftime("%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("❌ Data inválida. Use o formato DD/MM/AAAA.")
        return VENCIMENTO_PERSONALIZADO

    d = context.user_data
    db.add(d["nome"], d["telefone"], d["pacote"], d["valor"], data_sql)
    await update.message.reply_text("✅ Cliente cadastrado com sucesso!", reply_markup=TECLADO)
    return ConversationHandler.END

# ===== AGENDAMENTO =====
async def agendar(context: ContextTypes.DEFAULT_TYPE):
    if agora().strftime("%H:%M") == "09:00":
        for c in db.listar():
            venc_br = datetime.strptime(c[5], "%Y-%m-%d").strftime("%d/%m/%Y")
            msg = f"📅 Bom dia, {c[1]}!\nSeu plano '{c[3]}' vence em {venc_br}.\n💰 R$ {c[4]:.2f}"
            await enviar_whatsapp(c[2], msg)
        print("✅ Envio automático realizado às 09:00")

# ===== MAIN =====
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    cadastro = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Adicionar cliente$"), iniciar_cadastro)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nome)],
            TELEFONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_telefone)],
            PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pacote)],
            VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_valor)],
            VALOR_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_valor_custom)],
            VENCIMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vencimento)],
            VENCIMENTO_PERSONALIZADO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vencimento_personalizado)],
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
