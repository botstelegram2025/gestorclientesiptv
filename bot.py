import os
import csv
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    filters, ConversationHandler, CallbackQueryHandler
)

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "clientes.db"

# Coloque aqui o chat_id do admin para receber os avisos
ADMIN_CHAT_ID = 123456789  # <<< SUBSTITUA PELO SEU CHAT_ID REAL

ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO = range(4)
ESCOLHER_MENSAGEM = 4

PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]

mensagens_padrao = {
    "promo": "📢 Olá {nome}, confira nossa promoção especial!",
    "lembrete": "⏰ Olá {nome}, só passando para lembrar do seu compromisso amanhã.",
    "vencimento_hoje": "⚠️ Olá {nome}, seu plano vence hoje!",
    "vencido": "❌ Olá {nome}, seu plano está vencido desde ontem."
}

def teclado_principal():
    teclado = [
        ["➕ Adicionar Cliente", "📋 Listar Clientes"],
        ["🔄 Renovar Plano", "📊 Relatório"],
        ["📤 Exportar Dados", "❌ Cancelar Operação"]
    ]
    return ReplyKeyboardMarkup(teclado, resize_keyboard=True)

def criar_tabela():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT UNIQUE,
            pacote TEXT,
            plano REAL,
            vencimento TEXT,
            chat_id INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS renovacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telefone TEXT,
            data_renovacao TEXT,
            novo_vencimento TEXT,
            pacote TEXT,
            plano REAL
        )
    ''')
    conn.commit()
    conn.close()

def telefone_valido(telefone):
    return re.match(r'^\d{10,11}$', telefone)

def get_duracao_meses(pacote):
    mapa = {"1 mês": 1, "3 meses": 3, "6 meses": 6, "1 ano": 12}
    return mapa.get(pacote, 1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bem-vindo ao Bot de Gestão de Clientes!\n\n"
        "Escolha uma opção no menu abaixo ou digite um comando.",
        reply_markup=teclado_principal()
    )

async def add_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Digite o nome do cliente:", reply_markup=ReplyKeyboardRemove())
    return ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nome'] = update.message.text.strip()
    await update.message.reply_text("Digite o telefone do cliente (com DDD, somente números):")
    return ADD_PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.message.text.strip()
    if not telefone_valido(telefone):
        await update.message.reply_text("📵 Telefone inválido. Use apenas números com DDD (ex: 11999998888).")
        return ADD_PHONE
    context.user_data['telefone'] = telefone
    buttons = [[KeyboardButton(f"📦 {p}")] for p in PACOTES]
    await update.message.reply_text("📦 Escolha o pacote do cliente (duração):", reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
    return ADD_PACOTE

async def add_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pacote = update.message.text.replace("📦 ", "")
    if pacote not in PACOTES:
        await update.message.reply_text("❗ Pacote inválido. Tente novamente.")
        return ADD_PACOTE
    context.user_data['pacote'] = pacote
    buttons = [[KeyboardButton(f"💰 {p}")] for p in PLANOS]
    await update.message.reply_text("💰 Escolha o valor do plano:", reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
    return ADD_PLANO

async def add_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        plano = float(update.message.text.replace("💰 ", ""))
        if plano not in PLANOS:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ Valor inválido. Tente novamente.")
        return ADD_PLANO

    nome = context.user_data['nome']
    telefone = context.user_data['telefone']
    pacote = context.user_data['pacote']
    chat_id = update.effective_chat.id  # capturando chat_id do usuário que está cadastrando

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE telefone = ?", (telefone,))
    if cursor.fetchone():
        await update.message.reply_text("⚠️ Cliente com esse telefone já existe.", reply_markup=teclado_principal())
        conn.close()
        return ConversationHandler.END

    meses = get_duracao_meses(pacote)
    vencimento = (datetime.now() + timedelta(days=30 * meses)).strftime("%Y-%m-%d")
    cursor.execute(
        "INSERT INTO clientes (nome, telefone, pacote, plano, vencimento, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
        (nome, telefone, pacote, plano, vencimento, chat_id)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Cliente {nome} cadastrado com plano válido até {vencimento}.",
        reply_markup=teclado_principal()
    )
    return ConversationHandler.END

async def list_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, pacote, plano, vencimento FROM clientes")
    lista = cursor.fetchall()
    conn.close()

    if not lista:
        await update.message.reply_text("Nenhum cliente cadastrado.")
        return

    for nome, telefone, pacote, plano, venc in lista:
        venc_formatado = datetime.strptime(venc, '%Y-%m-%d').strftime('%d/%m/%Y')
        texto = f"👤 {nome}\n📞 {telefone}\n💰 R$ {plano:.2f} ({pacote})\n📅 Vence em {venc_formatado}"

        msg_whatsapp = quote_plus(f"Olá {nome}, tudo bem?")
        link_whatsapp = f"https://wa.me/{telefone}?text={msg_whatsapp}"

        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 WhatsApp", url=link_whatsapp)]
        ])

        await update.message.reply_text(texto, reply_markup=teclado)

async def renovar_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, vencimento FROM clientes")
    lista = cursor.fetchall()
    conn.close()

    if not lista:
        await update.message.reply_text("Nenhum cliente cadastrado para renovação.")
        return

    keyboard = [
        [
            InlineKeyboardButton(f"🔁 {nome} - {vencimento}", callback_data=f"renovar:{telefone}"),
            InlineKeyboardButton("🗑️ Cancelar", callback_data=f"cancelar:{telefone}")
        ] for nome, telefone, vencimento in lista
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👥 Selecione um cliente:", reply_markup=reply_markup)

async def callback_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    if data.startswith("renovar:"):
        telefone = data.split(":")[1]
        cursor.execute("SELECT nome, pacote, plano FROM clientes WHERE telefone = ?", (telefone,))
        result = cursor.fetchone()
        if not result:
            await query.edit_message_text("Cliente não encontrado.")
            conn.close()
            return
        nome, pacote, plano = result
        meses = get_duracao_meses(pacote)
        novo_venc = (datetime.now() + timedelta(days=30 * meses)).strftime("%Y-%m-%d")
        cursor.execute("UPDATE clientes SET vencimento = ? WHERE telefone = ?", (novo_venc, telefone))
        cursor.execute(
            "INSERT INTO renovacoes (telefone, data_renovacao, novo_vencimento, pacote, plano) VALUES (?, ?, ?, ?, ?)",
            (telefone, datetime.now().strftime("%Y-%m-%d"), novo_venc, pacote, plano)
        )
        conn.commit()
        conn.close()

        await query.edit_message_text(f"✅ {nome} renovado até {novo_venc}.")

    elif data.startswith("cancelar:"):
        telefone = data.split(":")[1]
        cursor.execute("DELETE FROM clientes WHERE telefone = ?", (telefone,))
        conn.commit()
        conn.close()
        await query.edit_message_text("🗑️ Cliente removido.")

async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes")
    rows = cursor.fetchall()
    conn.close()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="") as tmpfile:
        writer = csv.writer(tmpfile)
        writer.writerow(["ID", "Nome", "Telefone", "Pacote", "Plano", "Vencimento", "Chat_ID"])
        writer.writerows(rows)
        tmpfile_path = tmpfile.name

    await update.message.reply_document(document=open(tmpfile_path, "rb"), filename="clientes_export.csv")
    os.remove(tmpfile_path)

async def relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM renovacoes")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Nenhuma renovação registrada.")
        return

    msg = "📋 Log de renovações:\n"
    for _, tel, data, venc, pacote, plano in rows:
        msg += f"{tel} - {data} -> {venc} ({pacote}, R$ {plano})\n"
    await update.message.reply_text(msg)

async def enviar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(f"📨 {k}")] for k in mensagens_padrao.keys()]
    await update.message.reply_text("Escolha uma mensagem para enviar:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ESCOLHER_MENSAGEM

async def escolher_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chave = update.message.text.replace("📨 ", "")
    if chave not in mensagens_padrao:
        await update.message.reply_text("Mensagem inválida. Tente novamente.")
        return ESCOLHER_MENSAGEM
    context.user_data['msg_escolhida'] = chave

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, chat_id FROM clientes")
    clientes = cursor.fetchall()
    conn.close()

    count = 0
    for nome, telefone, chat_id_cliente in clientes:
        texto = mensagens_padrao[chave].format(nome=nome)
        try:
            await context.bot.send_message(chat_id=chat_id_cliente or update.effective_chat.id, text=texto)
            count += 1
        except Exception:
            pass

    await update.message.reply_text(f"✅ Mensagem enviada para {count} clientes.", reply_markup=teclado_principal())
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.", reply_markup=teclado_principal())
    return ConversationHandler.END

# Função que lembra o admin dos vencimentos
async def lembrar_admin_vencimentos(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    hoje = datetime.now().date()
    datas_aviso = {
        "3 dias": hoje + timedelta(days=3),
        "1 dia": hoje + timedelta(days=1),
        "vencimento hoje": hoje,
        "1 dia após": hoje - timedelta(days=1),
    }

    resultados = {k: [] for k in datas_aviso.keys()}

    cursor.execute("SELECT nome, telefone, vencimento FROM clientes")
    for nome, telefone, vencimento_str in cursor.fetchall():
        vencimento = datetime.strptime(vencimento_str, "%Y-%m-%d").date()
        for label, data_alvo in datas_aviso.items():
            if vencimento == data_alvo:
                resultados[label].append(f"{nome} ({telefone}) - vence em {vencimento.strftime('%d/%m/%Y')}")
                break

    conn.close()

    msg = "📅 *Resumo de vencimentos de clientes*\n\n"
    tem_alerta = False
    for label in ["3 dias", "1 dia", "vencimento hoje", "1 dia após"]:
        clientes = resultados[label]
        if clientes:
            tem_alerta = True
            msg += f"*{label.upper()}*:\n" + "\n".join(clientes) + "\n\n"

    if tem_alerta:
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="Markdown")
        except Exception:
            pass

def main():
    criar_tabela()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listar", list_clientes))
    app.add_handler(CommandHandler("relatorio", relatorio))
    app.add_handler(CommandHandler("exportar", exportar))
    app.add_handler(CommandHandler("renovar", renovar_cliente))
    app.add_handler(CommandHandler("enviar", enviar_mensagem))

    app.add_handler(CallbackQueryHandler(callback_opcoes))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_cliente)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ADD_PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pacote)],
            ADD_PLANO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plano)],
            ESCOLHER_MENSAGEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_mensagem)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )
    app.add_handler(conv_handler)

    # Job para lembrar admin dos vencimentos diariamente (exemplo: 9h da manhã)
    app.job_queue.run_daily(lembrar_admin_vencimentos, time=datetime.strptime("09:00", "%H:%M").time())

    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()
