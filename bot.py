import os
import csv
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters
)

# --- Banco de Dados ---
DB_NAME = "clientes.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT NOT NULL UNIQUE,
            plano INTEGER NOT NULL,
            duracao INTEGER NOT NULL,
            vencimento TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def adicionar_cliente(nome, telefone, plano, duracao):
    vencimento = (datetime.now() + timedelta(days=30 * duracao)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        INSERT OR REPLACE INTO clientes (nome, telefone, plano, duracao, vencimento)
        VALUES (?, ?, ?, ?, ?)
    ''', (nome, telefone, plano, duracao, vencimento))
    conn.commit()
    conn.close()
    return vencimento

def listar_clientes():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT nome, telefone, plano, duracao, vencimento FROM clientes")
    rows = cur.fetchall()
    conn.close()
    return rows

def clientes_proximos_vencimento(dias=3):
    hoje = datetime.now()
    limite = hoje + timedelta(days=dias)
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT nome, telefone, vencimento FROM clientes")
    rows = cur.fetchall()
    conn.close()
    alertas = []
    for nome, telefone, vencimento in rows:
        venc = datetime.strptime(vencimento, "%Y-%m-%d")
        if hoje <= venc <= limite:
            alertas.append((nome, telefone, vencimento))
    return alertas

# --- Estados da conversa ---
ADD_NAME, ADD_PHONE, ADD_PLANO, ADD_DURACAO = range(4)

PLANOS_VALIDOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]
DURACOES_VALIDAS = {"1": 1, "3": 3, "6": 6, "12": 12}

clientes = {}

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bem-vindo ao Bot de Gestão de Clientes!\n"
        "Comandos:\n"
        "/addcliente - adicionar cliente\n"
        "/listclientes - listar clientes\n"
        "/relatorio - resumo geral\n"
        "/exportar - exportar clientes em CSV"
    )

async def add_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Digite o nome do cliente:")
    return ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nome'] = update.message.text
    await update.message.reply_text("Digite o telefone do cliente (com DDD):")
    return ADD_PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['telefone'] = update.message.text
    planos_texto = ", ".join([str(p) for p in PLANOS_VALIDOS])
    await update.message.reply_text(f"Qual o valor do plano? Escolha entre: {planos_texto}")
    return ADD_PLANO

async def add_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        plano = int(update.message.text)
        if plano not in PLANOS_VALIDOS:
            raise ValueError
        context.user_data['plano'] = plano
        await update.message.reply_text("Qual a duração do plano? (1, 3, 6 ou 12 meses)")
        return ADD_DURACAO
    except ValueError:
        await update.message.reply_text("Valor inválido. Digite um dos valores permitidos.")
        return ADD_PLANO

async def add_duracao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dur = update.message.text.strip()
    if dur not in DURACOES_VALIDAS:
        await update.message.reply_text("Duração inválida. Escolha entre: 1, 3, 6 ou 12.")
        return ADD_DURACAO

    meses = DURACOES_VALIDAS[dur]
    telefone = context.user_data['telefone']
    nome = context.user_data['nome']
    plano = context.user_data['plano']

    vencimento = adicionar_cliente(nome, telefone, plano, meses)

    await update.message.reply_text(
        f"✅ Cliente cadastrado!\n\n"
        f"👤 Nome: {nome}\n"
        f"📱 Telefone: {telefone}\n"
        f"💰 Plano: R$ {plano}\n"
        f"📅 Duração: {meses} meses\n"
        f"⏳ Vencimento: {vencimento}"
    )
    return ConversationHandler.END

async def list_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = listar_clientes()
    if not rows:
        await update.message.reply_text("Nenhum cliente cadastrado.")
        return

    msg = "📋 Clientes:\n"
    for nome, tel, plano, dur, venc in rows:
        msg += f"• {nome} ({tel})\n  R$ {plano} - {dur} meses\n  Vence: {venc}\n\n"
    await update.message.reply_text(msg)

async def relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = listar_clientes()
    total = len(rows)
    vencidos = 0
    ativos = 0
    hoje = datetime.now()
    for _, _, _, _, venc in rows:
        venc_date = datetime.strptime(venc, "%Y-%m-%d")
        if venc_date < hoje:
            vencidos += 1
        else:
            ativos += 1

    await update.message.reply_text(
        f"📊 Relatório:\n"
        f"Total de clientes: {total}\n"
        f"Planos ativos: {ativos}\n"
        f"Vencidos: {vencidos}"
    )

async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = listar_clientes()
    with open("clientes.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Nome", "Telefone", "Plano", "Duração", "Vencimento"])
        writer.writerows(rows)

    await update.message.reply_document(document=open("clientes.csv", "rb"), filename="clientes.csv")

async def alerta_vencimentos(context: ContextTypes.DEFAULT_TYPE):
    alertas = clientes_proximos_vencimento()
    if not alertas:
        return
    texto = "⚠️ Clientes com vencimento próximo:\n\n"
    for nome, tel, venc in alertas:
        texto += f"• {nome} ({tel}) - Vence em {venc}\n"
    await context.bot.send_message(chat_id=context.job.chat_id, text=texto)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

# --- Main ---
def main():
    init_db()
    token = os.getenv("BOT_TOKEN")
    chat_admin_id = os.getenv("ADMIN_CHAT_ID")

    if not token or not chat_admin_id:
        print("❌ BOT_TOKEN ou ADMIN_CHAT_ID não definido!")
        return

    application = ApplicationBuilder().token(token).build()

    application.job_queue.run_repeating(alerta_vencimentos, interval=86400, first=10, chat_id=int(chat_admin_id))

    conv_add_cliente = ConversationHandler(
        entry_points=[CommandHandler('addcliente', add_cliente)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ADD_PLANO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plano)],
            ADD_DURACAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_duracao)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_add_cliente)
    application.add_handler(CommandHandler('listclientes', list_clientes))
    application.add_handler(CommandHandler('relatorio', relatorio))
    application.add_handler(CommandHandler('exportar', exportar))
    application.add_handler(CommandHandler('cancel', cancel))

    application.run_polling()

if __name__ == '__main__':
    main()
