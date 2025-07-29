# === BOT DE GESTÃO DE CLIENTES - COMPLETO ===
# Com melhorias:
# - Registro e uso da chave PIX
# - Confirmação de remoção de cliente
# - Envio de mensagens padrão conforme vencimento
# - Exportação de dados em CSV
#
import os
import re
import csv
import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    filters, ConversationHandler, CallbackQueryHandler
)

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "clientes.db"

ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO, ADD_SERVIDOR, ALTERAR_VENCIMENTO, RECEBER_PIX = range(7)

PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]
SERVIDORES = [
    ("fast play", "⚡"),
    ("genial tv", "🎯"),
    ("eitv", "📺"),
    ("gold play", "🏆"),
    ("slim tv", "🎬"),
    ("unitv", "🧩"),
    ("live21", "🌐"),
    ("ztech play", "🔧"),
    ("xserver play", "🚀")
]

mensagens_padrao = {
    "2": "⏰ Olá {nome}, seu plano vence em 2 dias ({vencimento}). Valor: R$ {plano:.2f}. PIX: {pix}",
    "1": "⚠️ Olá {nome}, seu plano vence amanhã ({vencimento}). Valor: R$ {plano:.2f}. PIX: {pix}",
    "0": "📆 Olá {nome}, seu plano vence hoje ({vencimento}). Valor: R$ {plano:.2f}. PIX: {pix}",
    "-1": "❌ Olá {nome}, seu plano venceu ontem ({vencimento}). Valor: R$ {plano:.2f}. PIX: {pix}"
}

def teclado_principal():
    teclado = [
        ["➕ Adicionar Cliente", "📋 Listar Clientes"],
        ["⏰ Filtrar Vencimentos", "📊 Relatório"],
        ["📤 Exportar Dados", "❌ Cancelar Operação"]
    ]
    return ReplyKeyboardMarkup(teclado, resize_keyboard=True)

def criar_tabela():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        telefone TEXT UNIQUE,
        pacote TEXT,
        plano REAL,
        vencimento TEXT,
        servidor TEXT,
        chat_id INTEGER
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS renovacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telefone TEXT,
        data_renovacao TEXT,
        novo_vencimento TEXT,
        pacote TEXT,
        plano REAL
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes (
        chat_id INTEGER PRIMARY KEY,
        chave_pix TEXT
    )''')
    conn.commit()
    conn.close()

def telefone_valido(telefone):
    return re.match(r'^\d{10,11}$', telefone)

def get_duracao_meses(pacote):
    return {"1 mês": 1, "3 meses": 3, "6 meses": 6, "1 ano": 12}.get(pacote, 1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT chave_pix FROM configuracoes WHERE chat_id = ?", (chat_id,))
    if not cursor.fetchone():
        await update.message.reply_text("🔐 Olá! Antes de começar, envie sua chave PIX:", reply_markup=ReplyKeyboardRemove())
        return RECEBER_PIX
    await update.message.reply_text("👋 Bem-vindo ao Bot de Gestão de Clientes!", reply_markup=teclado_principal())

async def receber_chave_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chave = update.message.text.strip()
    chat_id = update.effective_chat.id
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO configuracoes (chat_id, chave_pix) VALUES (?, ?)", (chat_id, chave))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Chave PIX salva com sucesso!\n{chave}", reply_markup=teclado_principal())
    return ConversationHandler.END

async def exportar_dados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, pacote, plano, vencimento, servidor FROM clientes")
    rows = cursor.fetchall()
    path = "/tmp/clientes_exportados.csv"
    with open(path, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Nome", "Telefone", "Pacote", "Plano", "Vencimento", "Servidor"])
        writer.writerows(rows)
    await update.message.reply_document(InputFile(path), caption="📤 Exportação concluída.", reply_markup=teclado_principal())

async def enviar_mensagens_vencimento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    dias = {
        "2 dias para vencer": 2,
        "1 dia para vencer": 1,
        "Vence hoje": 0,
        "Vencido há 1 dia": -1
    }.get(texto)
    if dias is None:
        return
    alvo = (datetime.now().date() + relativedelta(days=dias)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, plano, vencimento FROM clientes WHERE vencimento = ?", (alvo,))
    clientes = cursor.fetchall()
    cursor.execute("SELECT chave_pix FROM configuracoes WHERE chat_id = ?", (update.effective_chat.id,))
    chave_pix = cursor.fetchone()
    chave_pix = chave_pix[0] if chave_pix else ""
    for nome, tel, plano, venc in clientes:
        msg = mensagens_padrao[str(dias)].format(nome=nome, plano=plano, vencimento=venc, pix=chave_pix)
        texto_encoded = re.sub(r" ", "%20", msg)
        link = f"https://wa.me/55{tel}?text={texto_encoded}"
        await update.message.reply_text(f"📤 [{nome}](https://wa.me/55{tel}?text={texto_encoded})", parse_mode='Markdown')

async def confirmar_remocao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    telefone = query.data.split(":")[1]
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmar", callback_data=f"remover_confirmado:{telefone}"),
         InlineKeyboardButton("❌ Cancelar", callback_data=f"cliente:{telefone}")]
    ])
    await query.edit_message_text("Tem certeza que deseja remover este cliente?", reply_markup=teclado)

async def remover_confirmado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.callback_query.data.split(":")[1]
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clientes WHERE telefone = ?", (telefone,))
    conn.commit()
    conn.close()
    await update.callback_query.edit_message_text("🗑️ Cliente removido.")

# === Handlers adicionais ===
from main import (
    criar_tabela, add_cliente, add_name, add_phone, add_pacote, add_plano,
    add_servidor, listar_clientes, callback_cliente, renovar_plano,
    alterar_vencimento_start, alterar_vencimento_receber, processar_filtro,
    mensagem_handler, callback_query_handler
)

def main():
    criar_tabela()
    app = ApplicationBuilder().token(TOKEN).build()

    conv_add = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Adicionar Cliente$"), add_cliente)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ADD_PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pacote)],
            ADD_PLANO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plano)],
            ADD_SERVIDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_servidor)]
        },
        fallbacks=[]
    )

    conv_pix = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={RECEBER_PIX: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_chave_pix)]},
        fallbacks=[]
    )

    app.add_handler(conv_add)
    app.add_handler(conv_pix)
    app.add_handler(CommandHandler("exportar", exportar_dados))
    app.add_handler(MessageHandler(filters.Regex("^📤 Exportar Dados$"), exportar_dados))
    app.add_handler(MessageHandler(filters.Regex("^(2 dias|1 dia|Vence hoje|Vencido há 1 dia)$"), enviar_mensagens_vencimento))
    app.add_handler(CallbackQueryHandler(confirmar_remocao, pattern=r"^remover:"))
    app.add_handler(CallbackQueryHandler(remover_confirmado, pattern=r"^remover_confirmado:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
