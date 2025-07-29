
import os
import re
import sqlite3
import asyncio
import schedule
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    filters, ConversationHandler, CallbackQueryHandler
)
import requests
import threading

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "clientes.db"

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# Estados da conversa
ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO, ADD_SERVIDOR, ALTERAR_VENCIMENTO = range(6)
CONFIG_PIX, CONFIG_EMPRESA, CONFIG_CONTATO = range(6, 9)

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

def teclado_principal():
    teclado = [
        ["➕ Adicionar Cliente", "📋 Listar Clientes"],
        ["⏰ Filtrar Vencimentos", "📊 Relatório"],
        ["📤 Exportar Dados", "⚙️ Configurações"],
        ["📲 Envio Manual WhatsApp", "❌ Cancelar Operação"]
    ]
    return ReplyKeyboardMarkup(teclado, resize_keyboard=True)

def criar_tabela():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    # Tabela de clientes
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
    
    # Tabela de renovações
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
    
    # Tabela de configurações do admin
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY,
            pix_key TEXT,
            empresa_nome TEXT,
            contato_suporte TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabela de log de mensagens enviadas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mensagens_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telefone TEXT,
            nome_cliente TEXT,
            tipo_mensagem TEXT,
            data_envio TEXT,
            status TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def telefone_valido(telefone):
    return re.match(r'^\d{10,11}$', telefone)

def get_duracao_meses(pacote):
    mapa = {"1 mês": 1, "3 meses": 3, "6 meses": 6, "1 ano": 12}
    return mapa.get(pacote, 1)

def get_configuracoes():
    """Busca as configurações do admin"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT pix_key, empresa_nome, contato_suporte FROM configuracoes WHERE id = 1")
    config = cursor.fetchone()
    conn.close()
    return config

def salvar_configuracoes(pix_key, empresa_nome, contato_suporte):
    """Salva as configurações do admin"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO configuracoes (id, pix_key, empresa_nome, contato_suporte) 
        VALUES (1, ?, ?, ?)
    """, (pix_key, empresa_nome, contato_suporte))
    conn.commit()
    conn.close()

def gerar_mensagem_whatsapp(nome, tipo, plano_info=None):
    """Gera mensagens personalizadas baseadas no tipo de notificação"""
    config = get_configuracoes()
    
    if not config:
        empresa = "Sua Empresa"
        pix = "Não configurado"
        contato = "Não configurado"
    else:
        pix, empresa, contato = config
    
    mensagens = {
        "2_dias": f"""🔔 *{empresa}*
        
Olá *{nome}*! 

⚠️ Seu plano vence em *2 dias* ({plano_info['vencimento']})

📦 *Detalhes do seu plano:*
• Servidor: {plano_info['servidor']}
• Valor: R$ {plano_info['plano']:.2f}
• Pacote: {plano_info['pacote']}

💳 *Para renovar, utilize o PIX:*
`{pix}`

📞 Dúvidas? Entre em contato: {contato}

_Renove já e continue aproveitando nossos serviços!_ ✨""",

        "1_dia": f"""⏰ *{empresa}*

Olá *{nome}*!

🚨 *ATENÇÃO!* Seu plano vence *AMANHÃ* ({plano_info['vencimento']})

📦 *Detalhes do seu plano:*
• Servidor: {plano_info['servidor']}
• Valor: R$ {plano_info['plano']:.2f}
• Pacote: {plano_info['pacote']}

💳 *PIX para renovação:*
`{pix}`

⚡ *Renove hoje e evite a interrupção do serviço!*

📞 Suporte: {contato}""",

        "hoje": f"""🚨 *{empresa}*

Olá *{nome}*!

⛔ Seu plano *VENCE HOJE* ({plano_info['vencimento']})

📦 *Detalhes do seu plano:*
• Servidor: {plano_info['servidor']}
• Valor: R$ {plano_info['plano']:.2f}
• Pacote: {plano_info['pacote']}

💳 *PIX para renovação imediata:*
`{pix}`

🆘 *ÚLTIMA CHANCE!* Renove agora para não perder o acesso!

📞 Suporte urgente: {contato}""",

        "vencido": f"""❌ *{empresa}*

Olá *{nome}*,

💔 Seu plano *VENCEU ONTEM* ({plano_info['vencimento']})

📦 *Plano expirado:*
• Servidor: {plano_info['servidor']}
• Valor: R$ {plano_info['plano']:.2f}
• Pacote: {plano_info['pacote']}

🔄 *Para reativar, efetue o pagamento via PIX:*
`{pix}`

💬 Após o pagamento, envie o comprovante para: {contato}

_Estamos aguardando sua renovação!_ 💙"""
    }
    
    return mensagens.get(tipo, "Mensagem não encontrada")

def log_mensagem_enviada(telefone, nome, tipo, status="enviado"):
    """Registra o envio de mensagem no log"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO mensagens_log (telefone, nome_cliente, tipo_mensagem, data_envio, status)
        VALUES (?, ?, ?, ?, ?)
    """, (telefone, nome, tipo, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status))
    conn.commit()
    conn.close()

def enviar_whatsapp_automatico():
    """Função que verifica vencimentos e envia mensagens automaticamente"""
    hoje = datetime.now().date()
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    # Buscar clientes que vencem em 2 dias
    data_2_dias = hoje + timedelta(days=2)
    cursor.execute("""
        SELECT nome, telefone, pacote, plano, vencimento, servidor 
        FROM clientes WHERE vencimento = ?
    """, (data_2_dias.strftime("%Y-%m-%d"),))
    clientes_2_dias = cursor.fetchall()
    
    # Buscar clientes que vencem em 1 dia
    data_1_dia = hoje + timedelta(days=1)
    cursor.execute("""
        SELECT nome, telefone, pacote, plano, vencimento, servidor 
        FROM clientes WHERE vencimento = ?
    """, (data_1_dia.strftime("%Y-%m-%d"),))
    clientes_1_dia = cursor.fetchall()
    
    # Buscar clientes que vencem hoje
    cursor.execute("""
        SELECT nome, telefone, pacote, plano, vencimento, servidor 
        FROM clientes WHERE vencimento = ?
    """, (hoje.strftime("%Y-%m-%d"),))
    clientes_hoje = cursor.fetchall()
    
    # Buscar clientes que venceram ontem
    data_vencido = hoje - timedelta(days=1)
    cursor.execute("""
        SELECT nome, telefone, pacote, plano, vencimento, servidor 
        FROM clientes WHERE vencimento = ?
    """, (data_vencido.strftime("%Y-%m-%d"),))
    clientes_vencidos = cursor.fetchall()
    
    conn.close()
    
    # Processar cada grupo de clientes
    for nome, telefone, pacote, plano, vencimento, servidor in clientes_2_dias:
        plano_info = {
            'pacote': pacote,
            'plano': plano,
            'vencimento': vencimento,
            'servidor': servidor
        }
        mensagem = gerar_mensagem_whatsapp(nome, "2_dias", plano_info)
        enviar_whatsapp_link(telefone, mensagem)
        log_mensagem_enviada(telefone, nome, "2_dias_vencimento")
    
    for nome, telefone, pacote, plano, vencimento, servidor in clientes_1_dia:
        plano_info = {
            'pacote': pacote,
            'plano': plano,
            'vencimento': vencimento,
            'servidor': servidor
        }
        mensagem = gerar_mensagem_whatsapp(nome, "1_dia", plano_info)
        enviar_whatsapp_link(telefone, mensagem)
        log_mensagem_enviada(telefone, nome, "1_dia_vencimento")
    
    for nome, telefone, pacote, plano, vencimento, servidor in clientes_hoje:
        plano_info = {
            'pacote': pacote,
            'plano': plano,
            'vencimento': vencimento,
            'servidor': servidor
        }
        mensagem = gerar_mensagem_whatsapp(nome, "hoje", plano_info)
        enviar_whatsapp_link(telefone, mensagem)
        log_mensagem_enviada(telefone, nome, "vence_hoje")
    
    for nome, telefone, pacote, plano, vencimento, servidor in clientes_vencidos:
        plano_info = {
            'pacote': pacote,
            'plano': plano,
            'vencimento': vencimento,
            'servidor': servidor
        }
        mensagem = gerar_mensagem_whatsapp(nome, "vencido", plano_info)
        enviar_whatsapp_link(telefone, mensagem)
        log_mensagem_enviada(telefone, nome, "vencido_1_dia")

def enviar_whatsapp_link(telefone, mensagem):
    """Simula envio de WhatsApp (aqui você pode integrar com uma API real)"""
    # Esta função pode ser expandida para usar APIs como Twilio, WhatsApp Business API, etc.
    print(f"Enviando WhatsApp para {telefone}: {mensagem[:50]}...")
    return True

def executar_scheduler():
    """Executa o scheduler em uma thread separada"""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Verifica a cada minuto

# Configurar o scheduler para executar diariamente às 9h
schedule.every().day.at("09:00").do(enviar_whatsapp_automatico)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verificar se é o primeiro acesso (configurações não existem)
    config = get_configuracoes()
    
    if not config:
        await update.message.reply_text(
            "🎉 *Bem-vindo ao Bot de Gestão de Clientes!*\n\n"
            "⚙️ Este é seu primeiro acesso. Vamos configurar os dados essenciais para o funcionamento do sistema.\n\n"
            "📝 Digite a chave PIX para pagamentos:",
            reply_markup=ReplyKeyboardRemove()
        )
        return CONFIG_PIX
    else:
        await update.message.reply_text(
            "👋 Bem-vindo ao Bot de Gestão de Clientes!\n\n"
            "Escolha uma opção no menu abaixo ou digite um comando.",
            reply_markup=teclado_principal()
        )

# === CONFIGURAÇÃO INICIAL DO ADMIN ===

async def config_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['pix_key'] = update.message.text.strip()
    await update.message.reply_text("🏢 Agora digite o nome da sua empresa:")
    return CONFIG_EMPRESA

async def config_empresa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['empresa_nome'] = update.message.text.strip()
    await update.message.reply_text("📞 Por fim, digite o contato para suporte (telefone ou @usuario):")
    return CONFIG_CONTATO

async def config_contato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contato = update.message.text.strip()
    
    pix_key = context.user_data['pix_key']
    empresa_nome = context.user_data['empresa_nome']
    
    salvar_configuracoes(pix_key, empresa_nome, contato)
    
    await update.message.reply_text(
        f"✅ *Configuração concluída!*\n\n"
        f"🏢 Empresa: {empresa_nome}\n"
        f"💳 PIX: {pix_key}\n"
        f"📞 Suporte: {contato}\n\n"
        f"🤖 O sistema está pronto! As notificações automáticas serão enviadas diariamente às 9h.\n\n"
        f"📲 Você pode alterar essas configurações a qualquer momento no menu 'Configurações'.",
        reply_markup=teclado_principal()
    )
    return ConversationHandler.END

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

    buttons = [[KeyboardButton(f"{emoji} {nome}")] for nome, emoji in SERVIDORES]
    await update.message.reply_text(
        "🌐 Escolha o servidor para o cliente:",
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    )
    return ADD_SERVIDOR

async def add_servidor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
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

# === LISTAR CLIENTES ===
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

# === CALLBACK DOS CLIENTES ===
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
        [InlineKeyboardButton("📲 Enviar WhatsApp", callback_data=f"whatsapp:{telefone}")],
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

# === ENVIAR WHATSAPP ===
async def enviar_whatsapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telefone = query.data.split(":")[1]
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, pacote, plano, vencimento, servidor FROM clientes WHERE telefone = ?", (telefone,))
    res = cursor.fetchone()
    conn.close()

    if not res:
        await query.edit_message_text("Cliente não encontrado.")
        return

    nome, pacote, plano, vencimento, servidor = res
    
    plano_info = {
        'pacote': pacote,
        'plano': plano,
        'vencimento': vencimento,
        'servidor': servidor
    }

    # Escolher tipo de mensagem
    teclado = [
        [InlineKeyboardButton("⚠️ 2 dias p/ vencer", callback_data=f"msg_2_dias:{telefone}")],
        [InlineKeyboardButton("🚨 1 dia p/ vencer", callback_data=f"msg_1_dia:{telefone}")],
        [InlineKeyboardButton("🔴 Vence hoje", callback_data=f"msg_hoje:{telefone}")],
        [InlineKeyboardButton("❌ Vencido", callback_data=f"msg_vencido:{telefone}")],
        [InlineKeyboardButton("🔙 Voltar", callback_data=f"cliente:{telefone}")]
    ]
    
    await query.edit_message_text(
        f"📲 Escolha o tipo de mensagem para *{nome}*:",
        reply_markup=InlineKeyboardMarkup(teclado)
    )

async def processar_envio_whatsapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, telefone = query.data.split(":")
    tipo_msg = action.replace("msg_", "")
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, pacote, plano, vencimento, servidor FROM clientes WHERE telefone = ?", (telefone,))
    res = cursor.fetchone()
    conn.close()

    if not res:
        await query.edit_message_text("Cliente não encontrado.")
        return

    nome, pacote, plano, vencimento, servidor = res
    
    plano_info = {
        'pacote': pacote,
        'plano': plano,
        'vencimento': vencimento,
        'servidor': servidor
    }

    mensagem = gerar_mensagem_whatsapp(nome, tipo_msg, plano_info)
    texto_encoded = requests.utils.quote(mensagem)
    link = f"https://wa.me/55{telefone}?text={texto_encoded}"

    log_mensagem_enviada(telefone, nome, f"manual_{tipo_msg}")

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Abrir WhatsApp", url=link)],
        [InlineKeyboardButton("🔙 Voltar", callback_data=f"cliente:{telefone}")]
    ])
    
    await query.edit_message_text(
        f"✅ Mensagem preparada para *{nome}*!\n\n"
        f"📝 *Preview:*\n{mensagem[:200]}...\n\n"
        f"👆 Clique no botão para abrir o WhatsApp e enviar.",
        reply_markup=teclado
    )

# === CONFIGURAÇÕES ===
async def configuracoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = get_configuracoes()
    
    if config:
        pix, empresa, contato = config
        texto = (
            f"⚙️ *Configurações Atuais:*\n\n"
            f"🏢 Empresa: {empresa}\n"
            f"💳 PIX: {pix}\n"
            f"📞 Suporte: {contato}\n"
        )
    else:
        texto = "❌ Nenhuma configuração encontrada."
    
    teclado = [
        [KeyboardButton("✏️ Editar Configurações")],
        [KeyboardButton("📊 Ver Log de Mensagens")],
        [KeyboardButton("🔙 Voltar ao Menu")]
    ]
    
    await update.message.reply_text(
        texto,
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True)
    )

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

conv_handler_config = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        CONFIG_PIX: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_pix)],
        CONFIG_EMPRESA: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_empresa)],
        CONFIG_CONTATO: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_contato)],
    },
    fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)],
)

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

# === MAIN HANDLER ===

async def mensagem_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📋 Listar Clientes":
        await listar_clientes(update, context)
    elif text == "⏰ Filtrar Vencimentos":
        await filtrar_vencimentos(update, context)
    elif text == "⚙️ Configurações":
        await configuracoes(update, context)
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
    elif data.startswith("whatsapp:"):
        await enviar_whatsapp(update, context)
    elif data.startswith("msg_"):
        await processar_envio_whatsapp(update, context)
    elif data.startswith("renovar:"):
        await renovar_plano(update, context)
    elif data.startswith("alterar_venc:"):
        await alterar_vencimento_start(update, context)
    elif data.startswith("remover:"):
        await remover_cliente(update, context)
    elif data == "voltar_lista":
        await listar_clientes(update, context)
    else:
        await query.answer("Ação desconhecida.")

def main():
    criar_tabela()

    # Iniciar scheduler em thread separada
    scheduler_thread = threading.Thread(target=executar_scheduler, daemon=True)
    scheduler_thread.start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(conv_handler_config)
    app.add_handler(conv_handler_add)
    app.add_handler(conv_handler_alterar_venc)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    print("🤖 Bot iniciado! Notificações automáticas configuradas para 9h diariamente.")
    app.run_polling()

if __name__ == "__main__":
    main()
