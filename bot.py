import os
import re
import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta
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

ADMIN_CHAT_ID = 123456789  # <<< SUBSTITUA PELO SEU CHAT_ID REAL

ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO, ADD_SERVIDOR, ALTERAR_VENCIMENTO = range(6)
ESCOLHER_MENSAGEM = 6

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
    "promo": "📢 Olá {nome}, confira nossa promoção especial!",
    "lembrete": "⏰ Olá {nome}, só passando para lembrar do seu compromisso amanhã.",
    "vencimento_hoje": "⚠️ Olá {nome}, seu plano vence hoje!",
    "vencido": "❌ Olá {nome}, seu plano está vencido desde ontem."
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT UNIQUE,
            pacote TEXT,
            plano REAL,
            vencimento TEXT,
            servidor TEXT,
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

# === ADICIONAR CLIENTE ===

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
    context.user_data['plano'] = plano

    # Agora escolha o servidor
    buttons = [[KeyboardButton(f"{emoji} {nome}")] for nome, emoji in SERVIDORES]
    await update.message.reply_text(
        "🌐 Escolha o servidor para o cliente:",
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    )
    return ADD_SERVIDOR

async def add_servidor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    # texto esperado: "⚡ fast play" ou "fast play" ou "⚡ fast play" (vamos aceitar qualquer um que contenha o nome do servidor)
    escolhido = None
    for nome, emoji in SERVIDORES:
        if nome in texto.lower():
            escolhido = nome
            break
    if not escolhido:
        await update.message.reply_text("Servidor inválido. Tente novamente.")
        return ADD_SERVIDOR
    context.user_data['servidor'] = escolhido

    nome = context.user_data['nome']
    telefone = context.user_data['telefone']
    pacote = context.user_data['pacote']
    plano = context.user_data['plano']
    servidor = context.user_data['servidor']
    chat_id = update.effective_chat.id

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE telefone = ?", (telefone,))
    if cursor.fetchone():
        await update.message.reply_text("⚠️ Cliente com esse telefone já existe.", reply_markup=teclado_principal())
        conn.close()
        return ConversationHandler.END

    meses = get_duracao_meses(pacote)
    vencimento = (datetime.now().date() + relativedelta(months=meses)).strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO clientes (nome, telefone, pacote, plano, vencimento, servidor, chat_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nome, telefone, pacote, plano, vencimento, servidor, chat_id)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Cliente {nome} cadastrado com plano válido até {vencimento} no servidor {servidor}.",
        reply_markup=teclado_principal()
    )
    return ConversationHandler.END

# === LISTAR CLIENTES (exemplo simplificado para mostrar opções) ===
async def listar_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone FROM clientes ORDER BY nome")
    clientes = cursor.fetchall()
    conn.close()

    if not clientes:
        await update.message.reply_text("Nenhum cliente cadastrado.", reply_markup=teclado_principal())
        return

    buttons = []
    for nome, telefone in clientes:
        buttons.append([InlineKeyboardButton(f"{nome} ({telefone})", callback_data=f"cliente:{telefone}")])
    teclado = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Selecione um cliente:", reply_markup=teclado)

# === CALLBACK DOS CLIENTES (botões dentro do cliente) ===
async def callback_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telefone = query.data.split(":")[1]

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, pacote, plano, vencimento, servidor FROM clientes WHERE telefone = ?", (telefone,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        await query.edit_message_text("Cliente não encontrado.")
        return ConversationHandler.END

    nome, pacote, plano, vencimento, servidor = result

    teclado = [
        [InlineKeyboardButton("✉️ Enviar Mensagem", callback_data=f"enviar_msg:{telefone}")],
        [InlineKeyboardButton("🔄 Renovar Plano", callback_data=f"renovar:{telefone}")],
        [InlineKeyboardButton("🗓 Alterar Vencimento", callback_data=f"alterar_venc:{telefone}")],
        [InlineKeyboardButton("🗑 Remover Cliente", callback_data=f"remover:{telefone}")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="voltar_lista")]
    ]
    texto = (
        f"👤 {nome}\n"
        f"📞 {telefone}\n"
        f"📦 Pacote: {pacote}\n"
        f"💰 Plano: R$ {plano:.2f}\n"
        f"🗓 Vencimento: {vencimento}\n"
        f"🌐 Servidor: {servidor}"
    )
    await query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(teclado))

# === ENVIAR MENSAGEM (abre link WhatsApp) ===
async def enviar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telefone = query.data.split(":")[1]
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM clientes WHERE telefone = ?", (telefone,))
    res = cursor.fetchone()
    conn.close()

    if not res:
        await query.edit_message_text("Cliente não encontrado.")
        return

    nome = res[0]

    # Criar link WhatsApp
    texto_msg = f"Olá {nome}, tudo bem? Esta é uma mensagem automática do seu plano."
    texto_encoded = re.sub(r" ", "%20", texto_msg)
    link = f"https://wa.me/55{telefone}?text={texto_encoded}"

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Abrir WhatsApp", url=link)],
        [InlineKeyboardButton("🔙 Voltar", callback_data=f"cliente:{telefone}")]
    ])
    await query.edit_message_text(f"Clique no botão para enviar mensagem para {nome}:", reply_markup=teclado)

# === RENOVAR PLANO ===
async def renovar_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telefone = query.data.split(":")[1]
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, pacote, plano, vencimento FROM clientes WHERE telefone = ?", (telefone,))
    result = cursor.fetchone()
    if not result:
        await query.edit_message_text("Cliente não encontrado.")
        conn.close()
        return

    nome, pacote, plano, vencimento_str = result
    meses = get_duracao_meses(pacote)
    vencimento_atual = datetime.strptime(vencimento_str, "%Y-%m-%d").date()

    base_data = max(datetime.now().date(), vencimento_atual)
    novo_venc = (base_data + relativedelta(months=meses)).strftime("%Y-%m-%d")

    cursor.execute("UPDATE clientes SET vencimento = ? WHERE telefone = ?", (novo_venc, telefone))
    cursor.execute(
        "INSERT INTO renovacoes (telefone, data_renovacao, novo_vencimento, pacote, plano) VALUES (?, ?, ?, ?, ?)",
        (telefone, datetime.now().strftime("%Y-%m-%d"), novo_venc, pacote, plano)
    )
    conn.commit()
    conn.close()

    await query.edit_message_text(f"✅ {nome} renovado até {novo_venc}.")

# === ALTERAR VENCIMENTO MANUAL ===

async def alterar_vencimento_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telefone = query.data.split(":")[1]
    context.user_data['alterar_vencimento_telefone'] = telefone

    await query.edit_message_text("Digite a nova data de vencimento no formato AAAA-MM-DD:")
    return ALTERAR_VENCIMENTO

async def alterar_vencimento_receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    telefone = context.user_data.get('alterar_vencimento_telefone')
    try:
        nova_data = datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("Data inválida. Use o formato AAAA-MM-DD. Tente novamente.")
        return ALTERAR_VENCIMENTO

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE clientes SET vencimento = ? WHERE telefone = ?", (nova_data.strftime("%Y-%m-%d"), telefone))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Vencimento atualizado para {nova_data.strftime('%Y-%m-%d')}.", reply_markup=teclado_principal())
    return ConversationHandler.END

# === REMOVER CLIENTE ===
async def remover_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telefone = query.data.split(":")[1]
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clientes WHERE telefone = ?", (telefone,))
    conn.commit()
    conn.close()

    await query.edit_message_text("🗑️ Cliente removido.")

# === FILTRAR VENCIMENTOS ===
async def filtrar_vencimentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [KeyboardButton("2 dias para vencer")],
        [KeyboardButton("1 dia para vencer")],
        [KeyboardButton("Vence hoje")],
        [KeyboardButton("Vencido há 1 dia")],
        [KeyboardButton("Voltar")]
    ]
    await update.message.reply_text(
        "Escolha o filtro de vencimento:",
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    )

async def processar_filtro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    hoje = datetime.now().date()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    if texto == "2 dias para vencer":
        filtro = hoje + relativedelta(days=2)
        cursor.execute("SELECT nome, telefone, vencimento FROM clientes WHERE vencimento = ?", (filtro.strftime("%Y-%m-%d"),))
    elif texto == "1 dia para vencer":
        filtro = hoje + relativedelta(days=1)
        cursor.execute("SELECT nome, telefone, vencimento FROM clientes WHERE vencimento = ?", (filtro.strftime("%Y-%m-%d"),))
    elif texto == "Vence hoje":
        filtro = hoje
        cursor.execute("SELECT nome, telefone, vencimento FROM clientes WHERE vencimento = ?", (filtro.strftime("%Y-%m-%d"),))
    elif texto == "Vencido há 1 dia":
        filtro = hoje - relativedelta(days=1)
        cursor.execute("SELECT nome, telefone, vencimento FROM clientes WHERE vencimento = ?", (filtro.strftime("%Y-%m-%d"),))
    elif texto == "Voltar":
        await update.message.reply_text("Voltando ao menu principal.", reply_markup=teclado_principal())
        return
    else:
        await update.message.reply_text("Filtro inválido. Tente novamente.")
        return

    clientes = cursor.fetchall()
    conn.close()

    if not clientes:
        await update.message.reply_text("Nenhum cliente encontrado para esse filtro.", reply_markup=teclado_principal())
        return

    msg = "Clientes encontrados:\n\n"
    for nome, telefone, venc in clientes:
        msg += f"{nome} - {telefone} - vence em {venc}\n"
    await update.message.reply_text(msg, reply_markup=teclado_principal())

# === CONVERSATION HANDLERS ===

conv_handler_add = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^➕ Adicionar Cliente$"), add_cliente)],
    states={
        ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
        ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
        ADD_PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pacote)],
        ADD_PLANO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plano)],
        ADD_SERVIDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_servidor)],
    },
    fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)],
)

conv_handler_alterar_venc = ConversationHandler(
    entry_points=[CallbackQueryHandler(alterar_vencimento_start, pattern=r"alterar_venc:")],
    states={
        ALTERAR_VENCIMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, alterar_vencimento_receber)]
    },
    fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)],
)

# === MAIN ===

async def mensagem_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📋 Listar Clientes":
        await listar_clientes(update, context)
    elif text == "⏰ Filtrar Vencimentos":
        await filtrar_vencimentos(update, context)
    elif text in ["2 dias para vencer", "1 dia para vencer", "Vence hoje", "Vencido há 1 dia", "Voltar"]:
        await processar_filtro(update, context)
    elif text == "❌ Cancelar Operação":
        await update.message.reply_text("Operação cancelada.", reply_markup=teclado_principal())
    else:
        await update.message.reply_text("Opção inválida. Use o menu.", reply_markup=teclado_principal())

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("cliente:"):
        await callback_cliente(update, context)
    elif data.startswith("enviar_msg:"):
        await enviar_mensagem(update, context)
    elif data.startswith("renovar:"):
        await renovar_plano(update, context)
    elif data.startswith("alterar_venc:"):
        await alterar_vencimento_start(update, context)
    elif data.startswith("remover:"):
        await remover_cliente(update, context)
    elif data == "voltar_lista":
        # Voltar para listar clientes
        await listar_clientes(update, context)
    else:
        await query.answer("Ação desconhecida.")

def main():
    criar_tabela()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(conv_handler_add)
    app.add_handler(conv_handler_alterar_venc)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
