import os
import sqlite3
from datetime import datetime, timedelta
import pytz
import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

# === CONFIG ===
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_TOKEN = os.getenv("EVOLUTION_API_TOKEN")
ALLOWED_USERS = set(map(int, os.getenv("ALLOWED_USERS", "123456789").split(",")))
TZ = pytz.timezone("America/Sao_Paulo")

logging.basicConfig(level=logging.INFO)

# === DB ===
class DB:
    def __init__(self):
        self.conn = sqlite3.connect("clientes.db", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._criar()

    def _criar(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT, telefone TEXT, pacote TEXT,
                valor REAL, vencimento TEXT
            )
        """)
        self.conn.commit()

    def listar(self):
        return self.conn.execute("SELECT * FROM clientes").fetchall()

    def buscar(self, id):
        return self.conn.execute("SELECT * FROM clientes WHERE id = ?", (id,)).fetchone()

    def atualizar(self, id, campo, valor):
        self.conn.execute(f"UPDATE clientes SET {campo} = ? WHERE id = ?", (valor, id))
        self.conn.commit()

    def excluir(self, id):
        self.conn.execute("DELETE FROM clientes WHERE id = ?", (id,))
        self.conn.commit()

db = DB()

# === WHATSAPP ===
async def enviar_whatsapp(numero, mensagem):
    async with aiohttp.ClientSession() as session:
        async with session.post(EVOLUTION_API_URL, headers={
            "Authorization": f"Bearer {EVOLUTION_API_TOKEN}",
            "Content-Type": "application/json"
        }, json={"number": numero, "message": mensagem}) as resp:
            return resp.status == 200

# === COMANDO /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Acesso negado.")
        return
    await update.message.reply_text("👋 Bem-vindo!\nUse /listar para ver os clientes.")

# === /listar CLIENTES ===
async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clientes = db.listar()
    if not clientes:
        await update.message.reply_text("📭 Nenhum cliente encontrado.")
        return

    hoje = datetime.now(TZ)
    clientes_ordenados = []

    for c in clientes:
        venc = datetime.strptime(c["vencimento"], "%Y-%m-%d")
        dias = (venc - hoje).days
        clientes_ordenados.append((c, dias))

    clientes_ordenados.sort(key=lambda x: x[0]["vencimento"])

    keyboard = []
    for cliente, dias in clientes_ordenados:
        status = "🟢"
        if dias < 0: status = "🔴"
        elif dias == 0: status = "⚠️"
        elif dias <= 3: status = "🟡"

        label = f"{status} {cliente['nome']} - {cliente['vencimento']}"
        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"cliente_{cliente['id']}")
        ])

    await update.message.reply_text(
        "📋 *Clientes por vencimento:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# === CALLBACK INTERAÇÃO ===
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("cliente_"):
        id = int(data.split("_")[1])
        c = db.buscar(id)
        venc_br = datetime.strptime(c["vencimento"], "%Y-%m-%d").strftime("%d/%m/%Y")

        texto = (
            f"👤 *{c['nome']}*\n"
            f"📱 {c['telefone']}\n"
            f"📦 {c['pacote']}\n"
            f"💰 R$ {c['valor']:.2f}\n"
            f"📅 Venc: {venc_br}"
        )

        botoes = [
            [InlineKeyboardButton("📧 Enviar lembrete", callback_data=f"lembrete_{id}")],
            [InlineKeyboardButton("🔄 Renovar", callback_data=f"renovar_{id}")],
            [InlineKeyboardButton("📦 Alterar pacote", callback_data=f"alterar_pacote_{id}")],
            [InlineKeyboardButton("📅 Alterar vencimento", callback_data=f"alterar_venc_{id}")],
            [InlineKeyboardButton("✏️ Editar", callback_data=f"editar_{id}")],
            [InlineKeyboardButton("🗑️ Excluir", callback_data=f"confirmar_excluir_{id}")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="voltar")]
        ]
        await query.edit_message_text(text=texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))

    elif data.startswith("lembrete_"):
        id = int(data.split("_")[1])
        c = db.buscar(id)
        venc_br = datetime.strptime(c["vencimento"], "%Y-%m-%d").strftime("%d/%m/%Y")
        msg = f"🔔 Olá {c['nome']}, lembramos que seu plano '{c['pacote']}' vence em {venc_br}. Valor: R$ {c['valor']:.2f}"
        sucesso = await enviar_whatsapp(c["telefone"], msg)
        await query.edit_message_text("✅ Lembrete enviado." if sucesso else "❌ Falha ao enviar.")

    elif data.startswith("renovar_"):
        id = int(data.split("_")[1])
        c = db.buscar(id)
        dias = {
            "1 mês": 30, "3 meses": 90, "6 meses": 180, "12 meses": 365
        }.get(c["pacote"], 30)
        nova = datetime.strptime(c["vencimento"], "%Y-%m-%d") + timedelta(days=dias)
        db.atualizar(id, "vencimento", nova.strftime("%Y-%m-%d"))
        await query.edit_message_text(f"✅ Renovado até {nova.strftime('%d/%m/%Y')}")

    elif data.startswith("confirmar_excluir_"):
        id = int(data.split("_")[2])
        keyboard = [
            [InlineKeyboardButton("✅ Sim", callback_data=f"excluir_{id}"),
             InlineKeyboardButton("❌ Não", callback_data="voltar")]
        ]
        await query.edit_message_text("⚠️ Confirmar exclusão?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("excluir_"):
        id = int(data.split("_")[1])
        db.excluir(id)
        await query.edit_message_text("🗑️ Cliente excluído com sucesso.")

    elif data == "voltar":
        await listar(update, context)

# === MAIN ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CallbackQueryHandler(callback))

    app.run_polling()

if __name__ == "__main__":
    main()
